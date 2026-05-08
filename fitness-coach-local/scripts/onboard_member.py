#!/usr/bin/env python3
"""Onboard a new member: create profile, copy bitable, update group_map.

Called by the AI assistant after parsing a new member's questionnaire response.
Performs all file and API operations in one shot to avoid LLM step-skipping.

Usage:
    python3 onboard_member.py '{
        "name": "张三",
        "chat_id": "oc_xxxxx",
        "member_feishu_id": "ou_xxxxx",
        "goal": "减脂",
        "style": "energetic",
        "meals": {"breakfast": "07:30", "lunch": "12:00", "dinner": "18:30"},
        "reminder_freq": "每顿都提醒",
        "report_enabled": true,
        "weight_reminder": "none",
        "notes": "特别喜欢五月天"
    }'

Output (JSON to stdout):
    {"ok": true, "member_id": "zhang_san", "profile_path": "...", "bitable_token": "...", "table_ids": {...}}

Output (JSON to stderr) on failure:
    {"ok": false, "error": "...", "step": "base-copy|table-list|profile|group_map"}
"""

import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime

# ── Paths ────────────────────────────────────────────────────────────────
HERMES_HOME = os.path.expanduser("~/.hermes")
MEMBERS_DIR = os.path.join(HERMES_HOME, "members")
GROUP_MAP_PATH = os.path.join(HERMES_HOME, "group_map.json")

# ── lark-cli config ──────────────────────────────────────────────────────
LARK_CLI = os.path.expanduser("~/.nvm/versions/node/v20.20.0/bin/lark-cli")
# If lark-cli is elsewhere, set env var LARK_CLI_PATH
LARK_CLI = os.environ.get("LARK_CLI_PATH", LARK_CLI)

# Template bitable token (source to copy from)
TEMPLATE_BASE_TOKEN = os.environ.get("BITABLE_TEMPLATE_TOKEN", "TGixbmcoEaiZ43sfXvQcZ513nnf")

# Network retry config
MAX_RETRIES = 3
RETRY_DELAY = 3  # seconds


def fail(step, error):
    """Print structured error to stderr and exit."""
    json.dump({"ok": False, "error": error, "step": step}, sys.stderr)
    sys.stderr.write("\n")
    sys.exit(1)


def run_lark(args, retries=MAX_RETRIES):
    """Run a lark-cli command with retries on network errors."""
    cmd = [LARK_CLI] + args
    for attempt in range(1, retries + 1):
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=60
            )
            if result.returncode != 0:
                stderr = result.stderr.strip()
                if attempt < retries and _is_network_error(stderr):
                    time.sleep(RETRY_DELAY * attempt)
                    continue
                return None, stderr
            return result.stdout.strip(), None
        except subprocess.TimeoutExpired:
            if attempt < retries:
                time.sleep(RETRY_DELAY * attempt)
                continue
            return None, f"lark-cli timeout after {60}s"
        except FileNotFoundError:
            return None, f"lark-cli not found at {LARK_CLI}. Set LARK_CLI_PATH env var."
    return None, "Max retries exceeded"


def _is_network_error(msg):
    """Check if error message suggests a network issue."""
    if not msg:
        return False
    keywords = ["ECONNREFUSED", "ETIMEDOUT", "ENOTFOUND", "socket hang up",
                "network", "fetch failed", "timeout", "connect"]
    return any(k in msg.lower() for k in keywords)


def name_to_member_id(name):
    """Convert Chinese name to member_id (pinyin-ish, lowercase + underscores)."""
    # Simple approach: use raw name if it looks like pinyin/english already
    # For Chinese names, just use a sanitized version
    # In production, this could use pypinyin for proper pinyin conversion
    safe = re.sub(r'[^a-zA-Z0-9\u4e00-\u9fff]', '', name)
    # For now, if it contains Chinese characters, use a transliteration-friendly format
    if re.search(r'[\u4e00-\u9fff]', safe):
        # Fallback: use hex hash of the name for Chinese characters
        # This avoids dependency on pypinyin library
        h = hex(hash(name) & 0xFFFFFFFF)[2:]
        return f"member_{h}"
    return safe.lower().replace(" ", "_")


def load_group_map():
    """Load group_map.json, return (data, file_exists)."""
    if os.path.exists(GROUP_MAP_PATH):
        with open(GROUP_MAP_PATH, "r", encoding="utf-8") as f:
            return json.load(f), True
    return {"_config": {}}, False


def save_group_map(data):
    """Save group_map.json atomically."""
    tmp = GROUP_MAP_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, GROUP_MAP_PATH)


def main():
    # ── 1. Parse input ───────────────────────────────────────────────────
    if len(sys.argv) < 2:
        fail("parse", "Usage: onboard_member.py '<json_input>'")

    try:
        params = json.loads(sys.argv[1])
    except json.JSONDecodeError as e:
        fail("parse", f"Invalid JSON input: {e}")

    # Required fields
    name = params.get("name", "").strip()
    chat_id = params.get("chat_id", "").strip()
    member_feishu_id = params.get("member_feishu_id", "").strip()

    if not name:
        fail("parse", "Missing required field: name")
    if not chat_id:
        fail("parse", "Missing required field: chat_id")
    if not member_feishu_id:
        fail("parse", "Missing required field: member_feishu_id")

    # Optional fields with defaults
    goal = params.get("goal", "减脂")
    style = params.get("style", "energetic")
    meals = params.get("meals", {"breakfast": None, "lunch": None, "dinner": None})
    reminder_freq = params.get("reminder_freq", "每顿都提醒")
    report_enabled = params.get("report_enabled", True)
    weight_reminder = params.get("weight_reminder", "none")
    notes = params.get("notes", "")
    gender = params.get("gender", "")
    age = params.get("age")
    height = params.get("height")

    member_id = name_to_member_id(name)
    member_dir = os.path.join(MEMBERS_DIR, member_id)
    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

    # ── 2. Create profile.json ───────────────────────────────────────────
    profile = {
        "basic_info": {
            "name": name,
            "gender": gender,
            "age": age,
            "height": height,
            "health_conditions": []
        },
        "goal": goal,
        "fitness_level": "beginner",
        "style": style,
        "meals": meals,
        "reminder_freq": reminder_freq,
        "report_enabled": report_enabled,
        "training_days_per_week": 3,
        "diet_preference": "normal",
        "weight_reminder": weight_reminder,
        "notes": notes,
        "joined_at": now.split("T")[0]
    }

    os.makedirs(member_dir, exist_ok=True)
    profile_path = os.path.join(member_dir, "profile.json")
    with open(profile_path, "w", encoding="utf-8") as f:
        json.dump(profile, f, ensure_ascii=False, indent=2)

    # ── 3. Create summaries directory ────────────────────────────────────
    summaries_dir = os.path.join(member_dir, "summaries")
    os.makedirs(summaries_dir, exist_ok=True)

    # ── 4. Copy bitable from template ────────────────────────────────────
    stdout, stderr = run_lark([
        "base", "+base-copy",
        "--base-token", TEMPLATE_BASE_TOKEN,
        "--name", f"{name}的健身档案",
        "--time-zone", "Asia/Shanghai",
        "--as", "user"
    ])

    if stderr:
        fail("base-copy", f"Failed to copy bitable: {stderr}")

    try:
        copy_result = json.loads(stdout)
        base_data = copy_result.get("data", {}).get("base", {})
        new_token = base_data.get("base_token") or base_data.get("token") or ""
        if not new_token:
            new_token = copy_result.get("data", {}).get("token", "")
        if not new_token:
            fail("base-copy", f"Cannot find token in response: {stdout[:200]}")
    except json.JSONDecodeError:
        fail("base-copy", f"Cannot parse base-copy response: {stdout[:200]}")

    # ── 5. Get table IDs (retry — base copy may still be in progress) ────
    table_ids = {}
    table_err = None
    for attempt in range(1, MAX_RETRIES + 1):
        stdout, stderr = run_lark([
            "base", "+table-list",
            "--base-token", new_token,
            "--as", "user"
        ])
        table_err = stderr
        if not stderr:
            break
        if "is copying" in (stderr or "") or "is copying" in (stdout or ""):
            time.sleep(RETRY_DELAY * attempt)
            continue
        break

    if table_err:
        fail("table-list", f"Failed to list tables: {table_err}")

    try:
        tables_result = json.loads(stdout)
        tables = tables_result.get("data", {}).get("tables") or tables_result.get("data", {}).get("items", [])
        for table in tables:
            t_name = table.get("name") or table.get("table_name", "")
            t_id = table.get("id") or table.get("table_id", "")
            if t_name and t_id:
                table_ids[t_name] = t_id
    except json.JSONDecodeError:
        fail("table-list", f"Cannot parse table-list response: {stdout[:200]}")

    if not table_ids:
        fail("table-list", "No tables found in copied bitable")

    # ── 6. Update group_map.json ─────────────────────────────────────────
    group_map, _ = load_group_map()

    group_map[chat_id] = {
        "member_id": member_id,
        "member_name": name,
        "member_feishu_id": member_feishu_id,
        "bitable_token": new_token,
        "table_ids": table_ids,
        "style": style,
        "report_enabled": report_enabled,
        "weight_reminder": weight_reminder,
        "reminder_freq": reminder_freq,
        "auto_record": True,
        "created_at": now
    }

    save_group_map(group_map)

    # ── 7. Output result ─────────────────────────────────────────────────
    result = {
        "ok": True,
        "member_id": member_id,
        "member_name": name,
        "profile_path": profile_path,
        "bitable_token": new_token,
        "table_ids": table_ids,
        "chat_id": chat_id,
        "style": style,
        "meals": meals,
        "reminder_freq": reminder_freq,
        "weight_reminder": weight_reminder
    }
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    print()


if __name__ == "__main__":
    main()
