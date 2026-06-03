#!/usr/bin/env python3
"""Record training sessions and exercises to Feishu bitable.

Usage:
    # Write session + exercises
    python3 record_training.py <token> <session_tbl> <exercise_tbl> \
        "<member_name>" "<date>" "<theme>" '<exercises_json>' [--coach-notes "..."]

    # Delete session (cascade delete linked exercises)
    python3 record_training.py <token> <session_tbl> <exercise_tbl> \
        --delete --session-id <recvXXX>

    # Delete single exercise
    python3 record_training.py <token> <session_tbl> <exercise_tbl> \
        --delete-exercise --record-id <recvXXX>

    # Query session exercises
    python3 record_training.py <token> <session_tbl> <exercise_tbl> \
        --query --session-id <recvXXX>

Output (JSON to stdout on success):
    Write:   {"ok":true,"session_id":"recvAAA","theme":"胸","date":"2026-05-24",
              "exercises_written":3,"exercises_failed":0,
              "results":[{"name":"卧推","record_id":"recvBBB","ok":true},...]}
    Delete session:  {"ok":true,"deleted_session":"recvAAA","deleted_exercises":3,
              "deleted_exercise_ids":["recvBBB",...]}
    Delete exercise: {"ok":true,"deleted_exercise":"recvBBB"}
    Query:   {"ok":true,"session_id":"recvAAA","exercise_count":2,
              "exercises":[{"name":"卧推","weight":100,...},...]}

Output (JSON to stderr on failure):
    {"ok":false,"error":"..."}
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timezone, timedelta

LARK_CLI = os.environ.get("LARK_CLI_PATH", "/usr/local/bin/lark-cli")
CST = timezone(timedelta(hours=8))

# ── Bitable field names ──────────────────────────────────────────────────
THEME_FIELD = "训练主题"
EXERCISE_NAME_FIELD = "动作名称"
COACH_NOTES_FIELD = "教练备注"
SESSION_DATE_FIELD = "训练日期"
MEMBER_NAME_FIELD = "会员姓名"
LINK_FIELD = "关联课次"


def fail(error):
    """Print JSON error to stderr and exit."""
    json.dump({"ok": False, "error": error}, sys.stderr, ensure_ascii=False)
    sys.stderr.write("\n")
    sys.exit(1)


def _run_lark(args):
    """Run a lark-cli command; exit on any failure."""
    try:
        result = subprocess.run(
            [LARK_CLI] + args, capture_output=True, text=True, timeout=30
        )
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


def _run_lark_safe(args):
    """Run a lark-cli command; return (data, error_str) instead of exiting."""
    try:
        result = subprocess.run(
            [LARK_CLI] + args, capture_output=True, text=True, timeout=30
        )
    except subprocess.TimeoutExpired:
        return None, "lark-cli timed out after 30 seconds"
    if result.returncode != 0:
        return None, f"lark-cli error: {result.stderr.strip()}"
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None, f"lark-cli returned invalid JSON: {result.stdout.strip()[:200]}"
    if not data.get("ok"):
        return None, f"lark-cli returned error: {data}"
    return data, None


# ── Date helpers ─────────────────────────────────────────────────────────

def _date_to_ts(date_str):
    """YYYY-MM-DD -> (millisecond_timestamp, date_str) at 00:00 CST."""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        dt.date()  # validate day exists
    except ValueError:
        fail(f"Invalid date: {date_str}")
    dt = dt.replace(tzinfo=CST)
    return int(dt.timestamp() * 1000), date_str


def _is_future_date(date_str):
    """Return True if date_str is strictly after today (CST)."""
    target = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=CST).date()
    return target > datetime.now(CST).date()


# ── Arg parsing (manual, no argparse — see testing guide) ───────────────

def _parse_args(argv):
    args = argv[1:]
    positional = []
    flags = {}
    i = 0
    while i < len(args):
        if args[i].startswith("--"):
            key = args[i]
            if i + 1 < len(args) and not args[i + 1].startswith("--"):
                flags[key] = args[i + 1]
                i += 2
            else:
                flags[key] = True
                i += 1
        else:
            positional.append(args[i])
            i += 1

    if len(positional) < 3:
        fail("需要至少 3 个参数: <bitable_token> <课次表> <动作表>")

    mode = "write"
    if "--delete" in flags and "--delete-exercise" in flags:
        fail("--delete 和 --delete-exercise 不能同时使用，请二选一")
    elif "--delete-exercise" in flags:
        mode = "delete-exercise"
    elif "--delete" in flags:
        mode = "delete"
    elif "--query" in flags:
        mode = "query"

    return {
        "mode": mode,
        "token": positional[0],
        "session_table": positional[1],
        "exercise_table": positional[2],
        "positional": positional,
        "flags": flags,
    }


# ── Select option helpers ────────────────────────────────────────────────

def _get_field_options(base_token, table_id, field_name):
    """Get (field_id, options_list) for a select field via +field-list."""
    resp = _run_lark([
        "base", "+field-list",
        "--base-token", base_token,
        "--table-id", table_id,
    ])
    fields = resp.get("data", {}).get("fields", [])
    if not isinstance(fields, list):
        fail(f"+field-list returned unexpected format: {json.dumps(resp)[:200]}")
    for field in fields:
        if field.get("name") == field_name:
            return field.get("id", ""), field.get("options", [])
    return "", []


def _ensure_options(base_token, table_id, field_name, needed_values):
    """Add any missing values to a select field's options list."""
    field_id, existing = _get_field_options(base_token, table_id, field_name)
    existing_names = {opt.get("name", "") for opt in existing}
    new_values = [v for v in needed_values if v and v not in existing_names]
    if not new_values:
        return
    all_options = list(existing)
    for val in new_values:
        all_options.append({"name": val, "hue": "Blue"})
    payload = json.dumps(
        {"name": field_name, "type": "select", "options": all_options},
        ensure_ascii=False,
    )
    _run_lark([
        "base", "+field-update",
        "--base-token", base_token,
        "--table-id", table_id,
        "--field-id", field_id,
        "--json", payload,
        "--yes",
    ])


# ── Linked-exercise lookup ──────────────────────────────────────────────

def _find_linked_exercises(base_token, exercise_table, session_id):
    """Find all exercise record_ids linked to a session via +record-list."""
    resp = _run_lark([
        "base", "+record-list",
        "--base-token", base_token,
        "--table-id", exercise_table,
        "--format", "json",
    ])
    inner = resp.get("data", {})
    rows = inner.get("data", [])
    field_names = inner.get("fields", [])
    record_ids = inner.get("record_id_list", [])
    try:
        link_idx = field_names.index(LINK_FIELD)
    except ValueError:
        fail(f"字段 '{LINK_FIELD}' 未在动作表中找到")
    linked = []
    for i, row in enumerate(rows):
        if i >= len(record_ids):
            break
        if link_idx < len(row) and row[link_idx] == session_id:
            linked.append(record_ids[i])
    return linked


# ── Exercise payload builder ────────────────────────────────────────────

def _build_exercise_payload(ex, session_id):
    """Build JSON payload for a single exercise record."""
    payload = {
        EXERCISE_NAME_FIELD: ex.get("name", ""),
        LINK_FIELD: session_id,
        "重量": ex.get("weight", 0),
        "组数": ex.get("sets", 1),
        "次数": ex.get("reps", 0),
    }
    notes = ex.get("notes")
    if notes:
        payload["备注"] = notes
    return payload


# ══════════════════════════════════════════════════════════════════════════
# Mode handlers
# ══════════════════════════════════════════════════════════════════════════

def cmd_write(p):
    """Create training session + exercise records."""
    flags = p["flags"]
    positional = p["positional"]

    if len(positional) < 7:
        fail("写入模式需要: <token> <课次表> <动作表> \"<name>\" \"<date>\" "
             "\"<theme>\" '<exercises>'")

    member_name = positional[3]
    date_str = positional[4]
    theme = positional[5]
    exercises_json = positional[6]

    coach_notes = flags.get("--coach-notes", "")
    if coach_notes is True:
        coach_notes = ""

    # Validate date
    try:
        ts, date_str = _date_to_ts(date_str)
    except SystemExit:
        raise
    if _is_future_date(date_str):
        fail(f"日期 {date_str} 是未来日期，不允许录入")

    # Parse exercises
    try:
        exercises = json.loads(exercises_json)
    except json.JSONDecodeError:
        fail(f"动作 JSON 格式错误: {exercises_json[:100]}")
    if not isinstance(exercises, list) or len(exercises) == 0:
        fail("动作列表不能为空")

    token = p["token"]
    stbl = p["session_table"]
    etbl = p["exercise_table"]

    # Step 1: ensure theme in select options
    if theme:
        themes = theme if isinstance(theme, list) else [theme]
        _ensure_options(token, stbl, THEME_FIELD, themes)

    # Step 2: upsert session
    session_payload = {
        MEMBER_NAME_FIELD: member_name,
        SESSION_DATE_FIELD: ts,
    }
    if theme:
        session_payload[THEME_FIELD] = theme if isinstance(theme, list) else [theme]
    if coach_notes:
        session_payload[COACH_NOTES_FIELD] = coach_notes

    session_resp = _run_lark([
        "base", "+record-upsert",
        "--base-token", token,
        "--table-id", stbl,
        "--json", json.dumps(session_payload, ensure_ascii=False),
    ])
    session_id = (
        session_resp
        .get("data", {})
        .get("record", {})
        .get("record_id_list", [""])[0]
    )

    # Step 3: ensure exercise names in select options
    ex_names = [ex.get("name", "") for ex in exercises if ex.get("name")]
    if ex_names:
        _ensure_options(token, etbl, EXERCISE_NAME_FIELD, ex_names)

    # Step 4: write each exercise (partial failure OK)
    results = []
    written = 0
    failed = 0
    for ex in exercises:
        name = ex.get("name", "")
        if not name:
            results.append({"name": name, "ok": False, "error": "动作名称为空"})
            failed += 1
            continue
        payload = _build_exercise_payload(ex, session_id)
        ex_data, ex_error = _run_lark_safe([
            "base", "+record-upsert",
            "--base-token", token,
            "--table-id", etbl,
            "--json", json.dumps(payload, ensure_ascii=False),
        ])
        if ex_error:
            results.append({"name": name, "ok": False, "error": ex_error})
            failed += 1
        else:
            ex_rid = (
                ex_data
                .get("data", {})
                .get("record", {})
                .get("record_id_list", [""])[0]
            )
            results.append({"name": name, "record_id": ex_rid, "ok": True})
            written += 1

    output = {
        "ok": True,
        "session_id": session_id,
        "theme": theme,
        "date": date_str,
        "exercises_written": written,
        "exercises_failed": failed,
        "results": results,
    }
    json.dump(output, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")


def cmd_delete(p):
    """Delete a session and all its linked exercises."""
    flags = p["flags"]
    session_id = flags.get("--session-id")
    if not session_id:
        fail("--delete 需要 --session-id 参数")

    token = p["token"]
    etbl = p["exercise_table"]
    stbl = p["session_table"]

    linked = _find_linked_exercises(token, etbl, session_id)

    deleted_ids = []
    for rid in linked:
        _run_lark([
            "base", "+record-delete",
            "--base-token", token,
            "--table-id", etbl,
            "--record-id", rid,
            "--yes",
        ])
        deleted_ids.append(rid)

    _run_lark([
        "base", "+record-delete",
        "--base-token", token,
        "--table-id", stbl,
        "--record-id", session_id,
        "--yes",
    ])

    output = {
        "ok": True,
        "deleted_session": session_id,
        "deleted_exercises": len(linked),
        "deleted_exercise_ids": deleted_ids,
    }
    json.dump(output, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")


def cmd_delete_exercise(p):
    """Delete a single exercise record."""
    flags = p["flags"]
    record_id = flags.get("--record-id")
    if not record_id:
        fail("--delete-exercise 需要 --record-id 参数")

    token = p["token"]
    etbl = p["exercise_table"]

    _run_lark([
        "base", "+record-delete",
        "--base-token", token,
        "--table-id", etbl,
        "--record-id", record_id,
        "--yes",
    ])

    output = {"ok": True, "deleted_exercise": record_id}
    json.dump(output, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")


def cmd_query(p):
    """Query all exercises linked to a session."""
    flags = p["flags"]
    session_id = flags.get("--session-id")
    if not session_id:
        fail("--query 需要 --session-id 参数")

    token = p["token"]
    etbl = p["exercise_table"]

    resp = _run_lark([
        "base", "+record-list",
        "--base-token", token,
        "--table-id", etbl,
        "--format", "json",
    ])
    inner = resp.get("data", {})
    rows = inner.get("data", [])
    field_names = inner.get("fields", [])
    record_ids = inner.get("record_id_list", [])

    field_map = {name: idx for idx, name in enumerate(field_names)}
    exercises = []
    for i, row in enumerate(rows):
        if i >= len(record_ids):
            break
        link_idx = field_map.get(LINK_FIELD)
        if link_idx is not None and link_idx < len(row) and row[link_idx] == session_id:
            ex = {"record_id": record_ids[i]}
            for fname, fidx in field_map.items():
                if fidx < len(row):
                    ex[fname] = row[fidx]
            # Extract standard fields
            exercises.append({
                "record_id": record_ids[i],
                "name": row[field_map["动作名称"]] if "动作名称" in field_map and field_map["动作名称"] < len(row) else "",
                "weight": row[field_map["重量"]] if "重量" in field_map and field_map["重量"] < len(row) else 0,
                "sets": row[field_map["组数"]] if "组数" in field_map and field_map["组数"] < len(row) else 0,
                "reps": row[field_map["次数"]] if "次数" in field_map and field_map["次数"] < len(row) else 0,
                "notes": row[field_map["备注"]] if "备注" in field_map and field_map["备注"] < len(row) else "",
            })

    output = {
        "ok": True,
        "session_id": session_id,
        "exercise_count": len(exercises),
        "exercises": exercises,
    }
    json.dump(output, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")


# ── Entry point ─────────────────────────────────────────────────────────

def main():
    p = _parse_args(sys.argv)
    mode = p["mode"]
    if mode == "write":
        cmd_write(p)
    elif mode == "delete":
        cmd_delete(p)
    elif mode == "delete-exercise":
        cmd_delete_exercise(p)
    elif mode == "query":
        cmd_query(p)


if __name__ == "__main__":
    main()
