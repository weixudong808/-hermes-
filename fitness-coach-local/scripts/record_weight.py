#!/usr/bin/env python3
"""Record a member's weight to the bitable weight table.

Usage:
    python3 record_weight.py <bitable_token> <table_id> <weight>

Example:
    python3 record_weight.py "FhZVbkcYEaK95us0Dd1cqtbdneg" "tblrWZHI1fNHjCQi" 66.5

Output (JSON to stdout):
    {"ok": true, "weight": 66.5, "date": "2026-05-04"}

Output (JSON to stderr) on failure:
    {"ok": false, "error": "..."}
"""

import json
import os
import subprocess
import sys
from datetime import date, datetime, timezone, timedelta

LARK_CLI = os.environ.get(
    "LARK_CLI_PATH",
    os.path.expanduser("~/.nvm/versions/node/v20.20.0/bin/lark-cli"),
)

CST = timezone(timedelta(hours=8))


def fail(error):
    json.dump({"ok": False, "error": error}, sys.stderr)
    sys.stderr.write("\n")
    sys.exit(1)


def main():
    if len(sys.argv) != 4:
        fail("Usage: record_weight.py <bitable_token> <table_id> <weight>")

    base_token = sys.argv[1]
    table_id = sys.argv[2]

    try:
        weight = float(sys.argv[3])
    except ValueError:
        fail(f"Invalid weight value: {sys.argv[3]}")

    # Today 00:00 CST in milliseconds
    today_cst = datetime.now(CST).date()
    timestamp_ms = int(
        datetime.combine(today_cst, datetime.min.time(), tzinfo=CST).timestamp() * 1000
    )

    payload = json.dumps({"日期": timestamp_ms, "体重": weight}, ensure_ascii=False)

    result = subprocess.run(
        [
            LARK_CLI, "base", "+record-upsert",
            "--base-token", base_token,
            "--table-id", table_id,
            "--as", "user",
            "--json", payload,
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )

    if result.returncode != 0:
        fail(f"lark-cli error: {result.stderr.strip()}")

    output = {
        "ok": True,
        "weight": weight,
        "date": today_cst.isoformat(),
        "raw": result.stdout.strip()[:200],
    }
    json.dump(output, sys.stdout, ensure_ascii=False)
    print()


if __name__ == "__main__":
    main()
