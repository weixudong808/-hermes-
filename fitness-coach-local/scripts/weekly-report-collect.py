#!/usr/bin/env python3
"""Cron job pre-script: collect weekly training data for all summary_freq=weekly members.

Output: JSON with period, member list, sessions + actions per member.
Used by the weekly report cron job to feed data into the prompt.

Usage:
    python3 ~/.hermes/scripts/weekly-report-collect.py

Note: This script is referenced from the fitness-coach cron job (ID: b211038fb7af).
      It must live at ~/.hermes/scripts/ for the cron scheduler to find it.
"""
import json, subprocess, sys, os
from datetime import datetime, timedelta

LARK_CLI = os.path.expanduser("~/.nvm/versions/node/v20.20.0/bin/lark-cli")
GROUP_MAP_PATH = os.path.expanduser("~/.hermes/group_map.json")

def run_lark(args):
    result = subprocess.run(
        [LARK_CLI] + args,
        capture_output=True, text=True, timeout=30
    )
    if result.returncode != 0:
        return None, result.stderr
    return result.stdout, None

def main():
    today = datetime.now()
    monday = today - timedelta(days=today.weekday())
    start_str = monday.strftime("%Y-%m-%d")
    end_str = today.strftime("%Y-%m-%d")

    with open(GROUP_MAP_PATH) as f:
        group_map = json.load(f)

    results = []
    for chat_id, info in group_map.items():
        freq = info.get("summary_freq", "weekly")
        if freq != "weekly":
            continue

        bitable_token = info["bitable_token"]
        member_name = info["member_name"]
        member_id = info["member_id"]
        table_ids = info["table_ids"]

        out, err = run_lark([
            "base", "+record-list",
            "--base-token", bitable_token,
            "--table-id", table_ids["训练课次表"],
            "--as", "user"
        ])
        if err:
            results.append({"member_name": member_name, "member_id": member_id, "chat_id": chat_id, "error": err})
            continue

        sessions = json.loads(out)

        out2, err2 = run_lark([
            "base", "+record-list",
            "--base-token", bitable_token,
            "--table-id", table_ids["动作记录表"],
            "--as", "user"
        ])
        if err2:
            results.append({"member_name": member_name, "member_id": member_id, "chat_id": chat_id, "error": err2})
            continue

        actions = json.loads(out2)

        results.append({
            "member_name": member_name,
            "member_id": member_id,
            "chat_id": chat_id,
            "style": info.get("style", "energetic"),
            "period": f"{start_str} ~ {end_str}",
            "sessions": sessions,
            "actions": actions
        })

    print(json.dumps({"period": f"{start_str} ~ {end_str}", "members": results}, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
