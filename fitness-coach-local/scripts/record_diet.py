#!/usr/bin/env python3
"""Record a member's diet to the bitable diet table with deduplication.

Usage:
    # Basic: write a diet record (auto-dedup against today's records)
    python3 record_diet.py <bitable_token> <table_id> <meal_type> <content>

    # Append mode: append content to an existing record of the same meal today
    python3 record_diet.py <bitable_token> <table_id> <meal_type> <content> --append

    # Custom date (YYYY-MM-DD)
    python3 record_diet.py <bitable_token> <table_id> <meal_type> <content> --date 2026-05-10

    # Delete a record by record_id
    python3 record_diet.py <bitable_token> <table_id> --delete <record_id>

    # Query today's records (dry run, no write)
    python3 record_diet.py <bitable_token> <table_id> --query

    # Query a specific date's records
    python3 record_diet.py <bitable_token> <table_id> --query --date 2026-05-10

Examples:
    python3 record_diet.py "B1gmbRGMGaXicIs6Vhmc1PyFnsc" "tblRwzDFZP4JeWKe" "午餐" "米饭小碗，红烧排骨一份"
    python3 record_diet.py "B1gmbRGMGaXicIs6Vhmc1PyFnsc" "tblRwzDFZP4JeWKe" "午餐" "鸡蛋1个" --append

Output (JSON to stdout):
    {"ok": true, "action": "created", "record_id": "recvxxx", "meal": "午餐", "content": "..."}
    {"ok": true, "action": "dedup_skipped", "reason": "相同记录已存在"}
    {"ok": true, "action": "appended", "record_id": "recvxxx", "meal": "午餐", "old_content": "...", "new_content": "..."}

Output (JSON to stderr) on failure:
    {"ok": false, "error": "..."}
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import date, datetime, timezone, timedelta

LARK_CLI = os.environ.get("LARK_CLI_PATH", "/usr/local/bin/lark-cli")
CST = timezone(timedelta(hours=8))

# Date field and content field names in the diet table
DATE_FIELD = "记录日期"
CONTENT_FIELD = "饮食内容"


def fail(error):
    json.dump({"ok": False, "error": error}, sys.stderr, ensure_ascii=False)
    sys.stderr.write("\n")
    sys.exit(1)


def run_lark(args, timeout=30):
    """Run a lark-cli command and return parsed JSON."""
    result = subprocess.run(
        [LARK_CLI] + args,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        fail(f"lark-cli error: {result.stderr.strip()}")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        fail(f"lark-cli returned invalid JSON: {result.stdout.strip()[:200]}")


def date_to_timestamp_ms(d):
    """Convert a date object to CST 00:00:00 milliseconds timestamp."""
    dt = datetime.combine(d, datetime.min.time(), tzinfo=CST)
    return int(dt.timestamp() * 1000)


def parse_date(date_str):
    """Parse date string (YYYY-MM-DD) to date object."""
    try:
        return date.fromisoformat(date_str)
    except ValueError:
        fail(f"Invalid date format: {date_str}. Use YYYY-MM-DD.")


def normalize_content(content):
    """Normalize content for comparison: strip whitespace, unify separators."""
    return content.strip().replace("，", ",").replace("、", ",")


def query_records(base_token, table_id, target_date):
    """Query all records for a given date, return list of (record_id, content).

    lark-cli +record-list --format json returns:
      data.data: list of [col1, col2, col3, ...] rows (ordered by field_id_list)
      data.fields: list of field names corresponding to column positions
      data.record_id_list: list of record_ids parallel to data.data rows
    """
    resp = run_lark([
        "base", "+record-list",
        "--base-token", base_token,
        "--table-id", table_id,
        "--format", "json",
    ])

    inner = resp.get("data", {})
    rows = inner.get("data", [])
    field_names = inner.get("fields", [])
    record_ids = inner.get("record_id_list", [])

    # Find column indices for our target fields
    try:
        date_idx = field_names.index(DATE_FIELD)
        content_idx = field_names.index(CONTENT_FIELD)
    except ValueError:
        fail(f"Field names not found. Expected '{DATE_FIELD}' and '{CONTENT_FIELD}', got: {field_names}")

    records = []
    for i, row in enumerate(rows):
        if i >= len(record_ids):
            break
        rec_id = record_ids[i]
        date_str = row[date_idx] if date_idx < len(row) else ""
        content = row[content_idx] if content_idx < len(row) else ""

        # Parse date string like "2026-05-12 00:00:00"
        try:
            record_date = datetime.strptime(date_str.strip(), "%Y-%m-%d %H:%M:%S").date()
        except (ValueError, AttributeError):
            continue

        if record_date == target_date:
            records.append((rec_id, content))

    return records


def check_duplicate(records, meal_type, content):
    """Check if the same meal + content already exists in records.

    Returns (is_duplicate, matching_record_id).
    """
    normalized = normalize_content(content)
    for record_id, existing_content in records:
        # Check if meal type prefix matches and content matches
        # Content format: "午餐：米饭小碗，鸡块一份"
        if f"{meal_type}" in existing_content:
            existing_body = existing_content.split("：", 1)[-1] if "：" in existing_content else existing_content
            if normalize_content(existing_body) == normalized:
                return True, record_id
    return False, None


def find_meal_record(records, meal_type):
    """Find an existing record for the same meal type today.

    Returns (found, record_id, existing_content) or (False, None, None).
    """
    for record_id, content in records:
        if content.startswith(f"{meal_type}：") or content.startswith(f"{meal_type}:"):
            return True, record_id, content
    return False, None, None


def cmd_write(base_token, table_id, meal_type, content, target_date, append_mode):
    """Main write logic with dedup and append support."""
    records = query_records(base_token, table_id, target_date)

    # 1. Check for exact duplicate
    is_dup, dup_id = check_duplicate(records, meal_type, content)
    if is_dup:
        output = {
            "ok": True,
            "action": "dedup_skipped",
            "reason": f"今天已有相同的{meal_type}记录",
            "record_id": dup_id,
            "meal": meal_type,
            "content": content,
        }
        json.dump(output, sys.stdout, ensure_ascii=False)
        print()
        return

    # 2. Append mode: find existing record for same meal and merge
    if append_mode:
        found, rec_id, existing = find_meal_record(records, meal_type)
        if found:
            # Extract existing body (after "午餐：")
            existing_body = existing.split("：", 1)[-1] if "：" in existing else existing
            # Merge: append new content with separator
            merged_body = f"{existing_body}、{content}"
            new_content = f"{meal_type}：{merged_body}"

            # Update existing record
            payload = json.dumps({
                "record_id_list": [rec_id],
                "patch": {CONTENT_FIELD: new_content},
            }, ensure_ascii=False)

            resp = run_lark([
                "base", "+record-batch-update",
                "--base-token", base_token,
                "--table-id", table_id,
                "--json", payload,
            ])

            output = {
                "ok": True,
                "action": "appended",
                "record_id": rec_id,
                "meal": meal_type,
                "old_content": existing,
                "new_content": new_content,
            }
            json.dump(output, sys.stdout, ensure_ascii=False)
            print()
            return
        # No existing record found, fall through to create new

    # 3. Create new record
    timestamp_ms = date_to_timestamp_ms(target_date)
    formatted_content = f"{meal_type}：{content}"
    payload = json.dumps({
        DATE_FIELD: timestamp_ms,
        CONTENT_FIELD: formatted_content,
    }, ensure_ascii=False)

    resp = run_lark([
        "base", "+record-upsert",
        "--base-token", base_token,
        "--table-id", table_id,
        "--json", payload,
    ])

    record_id = resp.get("data", {}).get("record", {}).get("record_id_list", [""])[0]
    output = {
        "ok": True,
        "action": "created",
        "record_id": record_id,
        "meal": meal_type,
        "content": formatted_content,
        "date": target_date.isoformat(),
    }
    json.dump(output, sys.stdout, ensure_ascii=False)
    print()


def cmd_delete(base_token, table_id, record_id):
    """Delete a record by record_id."""
    resp = run_lark([
        "base", "+record-delete",
        "--base-token", base_token,
        "--table-id", table_id,
        "--record-id", record_id,
        "--yes",
    ])
    output = {
        "ok": True,
        "action": "deleted",
        "record_id": record_id,
    }
    json.dump(output, sys.stdout, ensure_ascii=False)
    print()


def cmd_query(base_token, table_id, target_date):
    """Query today's records and output them."""
    records = query_records(base_token, table_id, target_date)
    output = {
        "ok": True,
        "action": "query",
        "date": target_date.isoformat(),
        "count": len(records),
        "records": [
            {"record_id": rid, CONTENT_FIELD: content}
            for rid, content in records
        ],
    }
    json.dump(output, sys.stdout, ensure_ascii=False, indent=2)
    print()


def main():
    parser = argparse.ArgumentParser(description="Record diet with deduplication")
    parser.add_argument("base_token", help="Bitable base token")
    parser.add_argument("table_id", help="Diet record table ID")
    parser.add_argument("--delete", metavar="RECORD_ID", help="Delete a record by ID")
    parser.add_argument("--query", action="store_true", help="Query today's records")
    parser.add_argument("--date", default=None, help="Target date (YYYY-MM-DD), default today")
    parser.add_argument("--append", action="store_true", help="Append to existing meal record")
    # Positional args for write mode (optional, only when not --delete/--query)
    parser.add_argument("meal_type", nargs="?", default=None, help="Meal type (早餐/午餐/晚餐)")
    parser.add_argument("content", nargs="?", default=None, help="Diet content description")

    args = parser.parse_args()

    target_date = parse_date(args.date) if args.date else datetime.now(CST).date()

    if args.query:
        cmd_query(args.base_token, args.table_id, target_date)
    elif args.delete:
        cmd_delete(args.base_token, args.table_id, args.delete)
    else:
        if not args.meal_type or not args.content:
            parser.error("meal_type and content are required for write mode")
        cmd_write(args.base_token, args.table_id, args.meal_type, args.content, target_date, args.append)


if __name__ == "__main__":
    main()
