#!/usr/bin/env python3
"""Record a member's weight to the bitable weight table.

Usage:
    # Write
    python3 record_weight.py <bitable_token> <table_id> <weight>
    python3 record_weight.py <bitable_token> <table_id> <weight> --date 2026-05-19

    # Delete
    python3 record_weight.py <bitable_token> <table_id> --delete --date 2026-05-20
    python3 record_weight.py <bitable_token> <table_id> --delete --record-id recvXXX

    # Query
    python3 record_weight.py <bitable_token> <table_id> --query --date 2026-05-20

    # Trend
    python3 record_weight.py <bitable_token> <table_id> --trend --days 7

Output (JSON to stdout on success):
    Write:   {"ok": true, "weight": 65.0, "date": "2026-05-19"}
    Delete:  {"ok": true, "deleted": ["recvAAA", "recvBBB"], "count": 2}
    Query:   {"ok": true, "records": [...], "count": 1}
    Trend:   {"ok": true, "trend": "down", "change": -2.2, "start_weight": 70.0, "end_weight": 67.8, "data": [...]}

Output (JSON to stderr on failure):
    {"ok": false, "error": "..."}
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timezone, timedelta

LARK_CLI = os.environ.get("LARK_CLI_PATH", "/usr/local/bin/lark-cli")
CST = timezone(timedelta(hours=8))


def fail(error):
    json.dump({"ok": False, "error": error}, sys.stderr)
    sys.stderr.write("\n")
    sys.exit(1)


def _run_lark(args):
    """Run a lark-cli command and return parsed JSON response."""
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired:
        fail("lark-cli timed out after 30 seconds")

    if result.returncode != 0:
        fail(f"lark-cli error: {result.stderr.strip()}")

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        fail(f"lark-cli returned invalid JSON: {result.stdout.strip()[:200]}")

    if not data.get("ok"):
        fail(f"lark-cli returned error: {data}")

    return data


def _date_to_ts(date_str):
    """Convert YYYY-MM-DD to (millisecond_timestamp, date_str) at 00:00 CST."""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        dt.date()  # validate date exists (e.g. reject 2026-13-45)
    except ValueError:
        fail(f"Invalid date: {date_str}")
    dt = dt.replace(tzinfo=CST)
    return int(dt.timestamp() * 1000), date_str


def _today_ts():
    """Return (millisecond_timestamp, YYYY-MM-DD) for today in CST."""
    today = datetime.now(CST).date()
    dt = datetime.combine(today, datetime.min.time(), tzinfo=CST)
    return int(dt.timestamp() * 1000), today.isoformat()


def _parse_args(argv):
    """Manual argument parsing. Returns dict with parsed values."""
    # argv[0] = script name, argv[1] = token, argv[2] = table_id
    if len(argv) < 3:
        fail("Usage: record_weight.py <bitable_token> <table_id> <weight> [--date DATE]")

    base_token = argv[1]
    table_id = argv[2]
    rest = argv[3:]

    result = {
        "base_token": base_token,
        "table_id": table_id,
        "weight": None,
        "date": None,
        "delete": False,
        "record_id": None,
        "query": False,
        "trend": False,
        "days": 7,
    }

    i = 0
    while i < len(rest):
        arg = rest[i]

        if arg == "--date":
            if i + 1 >= len(rest):
                fail("--date requires a value (YYYY-MM-DD)")
            result["date"] = rest[i + 1]
            i += 2

        elif arg == "--delete":
            result["delete"] = True
            i += 1

        elif arg == "--record-id":
            if i + 1 >= len(rest):
                fail("--record-id requires a value")
            result["record_id"] = rest[i + 1]
            i += 2

        elif arg == "--query":
            result["query"] = True
            i += 1

        elif arg == "--trend":
            result["trend"] = True
            i += 1

        elif arg == "--days":
            if i + 1 >= len(rest):
                fail("--days requires a value")
            try:
                result["days"] = int(rest[i + 1])
            except ValueError:
                fail("--days must be a positive integer")
            i += 2

        else:
            # Treat as weight value
            try:
                result["weight"] = float(arg)
            except ValueError:
                fail(f"Invalid weight value: {arg}")
            i += 1

    return result


def cmd_write(base_token, table_id, weight, date_str=None):
    """Write a weight record."""
    if date_str:
        ts, date_iso = _date_to_ts(date_str)
    else:
        ts, date_iso = _today_ts()

    weight = round(weight, 1)

    payload = json.dumps({"体重": weight, "日期": ts}, ensure_ascii=False)

    _run_lark([
        LARK_CLI, "base", "+record-upsert",
        "--base-token", base_token,
        "--table-id", table_id,
        "--json", payload,
    ])

    output = {"ok": True, "weight": weight, "date": date_iso}
    json.dump(output, sys.stdout, ensure_ascii=False)
    print()


def cmd_delete(base_token, table_id, del_date=None, record_id=None):
    """Delete weight record(s) by date or by record_id."""
    if del_date and record_id:
        fail("--delete: cannot use both --date and --record-id, pick one")
    if not del_date and not record_id:
        fail("--delete: must specify either --date or --record-id")

    if record_id:
        _run_lark([
            LARK_CLI, "base", "+record-delete",
            "--base-token", base_token,
            "--table-id", table_id,
            "--record-id", record_id,
            "--yes",
        ])
        output = {"ok": True, "deleted": [record_id], "count": 1}
    else:
        ts, _ = _date_to_ts(del_date)
        list_data = _run_lark([
            LARK_CLI, "base", "+record-list",
            "--base-token", base_token,
            "--table-id", table_id,
            "--filter", json.dumps([{"field_name": "日期", "op": "is", "value": [ts]}]),
        ])

        items = list_data.get("data", {}).get("items", [])
        deleted = []
        for item in items:
            rid = item.get("record_id")
            if rid:
                _run_lark([
                    LARK_CLI, "base", "+record-delete",
                    "--base-token", base_token,
                    "--table-id", table_id,
                    "--record-id", rid,
                    "--yes",
                ])
                deleted.append(rid)

        output = {"ok": True, "deleted": deleted, "count": len(deleted)}

    json.dump(output, sys.stdout, ensure_ascii=False)
    print()


def cmd_query(base_token, table_id, query_date):
    """Query weight records for a specific date."""
    ts, date_iso = _date_to_ts(query_date)

    list_data = _run_lark([
        LARK_CLI, "base", "+record-list",
        "--base-token", base_token,
        "--table-id", table_id,
        "--filter", json.dumps([{"field_name": "日期", "op": "is", "value": [ts]}]),
    ])

    items = list_data.get("data", {}).get("items", [])
    records = []
    for item in items:
        fields = item.get("fields", {})
        records.append({
            "weight": fields.get("体重"),
            "date": date_iso,
            "record_id": item.get("record_id"),
        })

    output = {"ok": True, "records": records, "count": len(records)}
    json.dump(output, sys.stdout, ensure_ascii=False)
    print()


def cmd_trend(base_token, table_id, days=7):
    """Calculate weight trend over the given number of days."""
    if days < 1:
        fail("--days must be >= 1")

    today = datetime.now(CST).date()
    start_date = today - timedelta(days=days)
    start_ts, _ = _date_to_ts(start_date.isoformat())
    end_ts, _ = _today_ts()

    list_data = _run_lark([
        LARK_CLI, "base", "+record-list",
        "--base-token", base_token,
        "--table-id", table_id,
        "--filter", json.dumps([
            {
                "conjunction": "and",
                "conditions": [
                    {"field_name": "日期", "op": "isGreaterThanOrEqualTo", "value": [start_ts]},
                    {"field_name": "日期", "op": "isLessThanOrEqualTo", "value": [end_ts]},
                ],
            }
        ]),
    ])

    items = list_data.get("data", {}).get("items", [])

    if not items:
        output = {"ok": True, "trend": "no_data", "data": []}
        json.dump(output, sys.stdout, ensure_ascii=False)
        print()
        return

    records = []
    for item in items:
        fields = item.get("fields", {})
        w = fields.get("体重")
        raw_date = fields.get("日期")
        if w is not None and raw_date is not None:
            # Convert millisecond timestamp back to YYYY-MM-DD
            actual_date = datetime.fromtimestamp(int(raw_date) / 1000, tz=CST).date().isoformat()
            records.append({"weight": float(w), "date": actual_date})

    records.sort(key=lambda r: r["date"])

    if len(records) < 2:
        output = {"ok": True, "trend": "insufficient_data", "data": records}
        json.dump(output, sys.stdout, ensure_ascii=False)
        print()
        return

    start_weight = records[0]["weight"]
    end_weight = records[-1]["weight"]
    change = round(end_weight - start_weight, 1)

    if abs(change) < 0.3:
        trend = "stable"
    elif change > 0:
        trend = "up"
    else:
        trend = "down"

    output = {
        "ok": True,
        "trend": trend,
        "change": change,
        "start_weight": start_weight,
        "end_weight": end_weight,
        "data": records,
    }
    json.dump(output, sys.stdout, ensure_ascii=False)
    print()


def main():
    args = _parse_args(sys.argv)

    if args["delete"]:
        cmd_delete(args["base_token"], args["table_id"],
                   del_date=args["date"], record_id=args["record_id"])
    elif args["query"]:
        if not args["date"]:
            fail("--query requires --date")
        cmd_query(args["base_token"], args["table_id"], args["date"])
    elif args["trend"]:
        cmd_trend(args["base_token"], args["table_id"], days=args["days"])
    else:
        if args["weight"] is None:
            fail("Usage: record_weight.py <bitable_token> <table_id> <weight> [--date DATE]")
        cmd_write(args["base_token"], args["table_id"], args["weight"], date_str=args["date"])


if __name__ == "__main__":
    main()
