#!/usr/bin/env python3
"""Fitness Coach System Health Check & Cron Recovery.

Runs daily (via cron) to:
1. Scan all member profiles and compare cron job IDs against jobs.json
2. Report lost/valid jobs
3. Output rebuild commands for the AI assistant to execute

When called with --github-sync, also syncs member data to GitHub backup repo.

Usage:
    python3 health_check.py                    # Check only, output JSON report
    python3 health_check.py --github-sync      # Check + sync to GitHub
    python3 health_check.py --verify-system    # Verify the health-check cron itself exists

Exit codes:
    0 = all healthy (or --fix rebuilt everything)
    1 = lost jobs detected (needs attention)
    2 = error
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timezone, timedelta

# ── Paths ────────────────────────────────────────────────────────────────
HERMES_HOME = os.path.expanduser("~/.hermes")
MEMBERS_DIR = os.path.join(HERMES_HOME, "members")
GROUP_MAP_PATH = os.path.join(HERMES_HOME, "group_map.json")
JOBS_JSON_PATH = os.path.join(HERMES_HOME, "cron", "jobs.json")
MEMORY_STORE_PATH = os.path.join(HERMES_HOME, "memory_store.db")
SKILLS_DIR = os.path.join(HERMES_HOME, "skills", "fitness-coach")
MCP_DB_PATH = os.path.join(HERMES_HOME, "mcp-server", "fitness_data.db")
REPO_DIR = os.path.join("/tmp", "fitness-coach-hermes")
LOG_DIR = os.path.join(HERMES_HOME, "logs")
LOG_FILE = os.path.join(LOG_DIR, "health_check.log")

# ── Health check cron job identifier ─────────────────────────────────────
HEALTH_CHECK_CRON_NAME = "系统健康检查"

# ── Meal type mapping ────────────────────────────────────────────────────
MEAL_TYPE_MAP = {
    "meal_breakfast": ("早餐", "breakfast"),
    "meal_lunch": ("午餐", "lunch"),
    "meal_dinner": ("晚餐", "dinner"),
    "weight": ("体重", None),
}

STYLE_PROMPTS = {
    "energetic": {
        "meal": '{name}，{meal_type}时间到啦~ 记得拍张照片发群里哦 📸',
        "weight": '{name}，新的一天开始啦~ 记得称一下体重哦 ⚖️',
    },
    "professional": {
        "meal": '{name}，{meal_type}时间，记得饮食打卡。',
        "weight": '{name}，请记录今日体重。',
    },
    "gentle": {
        "meal": '{name}，{meal_type}时间到啦~ 慢慢享受 🍽️',
        "weight": '{name}，新的一天开始啦~ 记得称一下体重哦 ⚖️',
    },
    "strict": {
        "meal": '{name}，该吃{meal_type}了，拍个照发群里。',
        "weight": '{name}，称一下体重，记一下。',
    },
}

STYLE_DESC = {
    "energetic": "活泼鼓励，多用表情",
    "professional": "简洁专业",
    "gentle": "温和关怀，耐心引导",
    "strict": "直接",
}


# ── Utilities ────────────────────────────────────────────────────────────

def load_json(path):
    if not os.path.exists(path):
        return None
    with open(path, "r") as f:
        return json.load(f)


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, ensure_newline=True)


def log(msg):
    """Append to health check log file."""
    os.makedirs(LOG_DIR, exist_ok=True)
    tz = timezone(timedelta(hours=8))
    ts = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")
    print(line, file=sys.stderr)


def run_cmd(cmd, timeout=30):
    """Run a shell command, return (exit_code, stdout, stderr)."""
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=timeout
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "timeout"


def run_cmd_in(cmd, workdir, timeout=30):
    """Run a shell command in a specific directory."""
    return run_cmd(f"cd {workdir} && {cmd}", timeout=timeout)


# ── Core Logic ───────────────────────────────────────────────────────────

def get_existing_job_ids():
    """Get set of job IDs currently in jobs.json."""
    data = load_json(JOBS_JSON_PATH)
    if not data or "jobs" not in data:
        return set()
    return {job["id"] for job in data["jobs"]}


def get_existing_job_names():
    """Get set of job names currently in jobs.json."""
    data = load_json(JOBS_JSON_PATH)
    if not data or "jobs" not in data:
        return set()
    return {job["name"] for job in data["jobs"]}


def get_chat_ids_for_member(member_id):
    """Find all chat_ids mapped to a member_id in group_map.json."""
    group_map = load_json(GROUP_MAP_PATH)
    if not group_map:
        return []
    chat_ids = []
    for chat_id, info in group_map.items():
        if chat_id == "_config":
            continue
        if info.get("member_id") == member_id:
            chat_ids.append(chat_id)
    return chat_ids


def get_coach_home_channel():
    """Get coach's home chat_id from group_map _config or first entry."""
    group_map = load_json(GROUP_MAP_PATH)
    if not group_map:
        return "feishu"
    # Return "feishu" which maps to the default home channel
    return "feishu"


def build_cron_command(member_name, style, chat_id, cron_key, meal_type_zh, time_str, is_weight=False):
    """Build the Hermes cronjob create parameters as a dict."""
    if is_weight:
        prompt = (
            f'你是健身教练小卫的助手。提醒会员"{member_name}"称一下体重。\n'
            f'风格：{style}（{STYLE_DESC.get(style, "")}）。\n'
            f'直接输出提醒消息内容即可，内容类似：'
            f'"{STYLE_PROMPTS.get(style, STYLE_PROMPTS["gentle"])["weight"].format(name=member_name)}"。\n'
            f'系统会自动投递。不要加载任何 skill。'
        )
        name = f"{member_name}-体重提醒"
        schedule = "0 8 * * *"
    else:
        prompt = (
            f'你是健身教练小卫的助手。提醒会员"{member_name}"该吃{meal_type_zh}了。\n'
            f'风格：{style}（{STYLE_DESC.get(style, "")}）。\n'
            f'直接输出提醒消息内容即可，内容类似：'
            f'"{STYLE_PROMPTS.get(style, STYLE_PROMPTS["gentle"])["meal"].format(name=member_name, meal_type=meal_type_zh)}"。\n'
            f'系统会自动投递。不要加载任何 skill。'
        )
        name = f"{member_name}-{meal_type_zh}提醒"
        parts = time_str.split(":")
        if len(parts) == 2:
            h, m = parts
            schedule = f"{m} {h} * * *"
        else:
            schedule = "0 8 * * *"

    return {
        "action": "create",
        "name": name,
        "schedule": schedule,
        "deliver": f"feishu:{chat_id}",
        "enabled_toolsets": ["terminal"],
        "prompt": prompt,
        "profile_cron_key": cron_key,
        "member_name": member_name,
    }


def check_all_crons():
    """Scan all profiles, compare with jobs.json, return report."""
    existing_ids = get_existing_job_ids()
    members = []
    if os.path.isdir(MEMBERS_DIR):
        for dirname in sorted(os.listdir(MEMBERS_DIR)):
            profile_path = os.path.join(MEMBERS_DIR, dirname, "profile.json")
            profile = load_json(profile_path)
            if profile:
                members.append((dirname, profile))

    lost_jobs = []
    valid_jobs = []
    rebuild_commands = []

    for member_id, profile in members:
        name = profile.get("name", member_id)
        style = profile.get("style", "energetic")
        meals = profile.get("meals", {})
        cron_jobs = profile.get("cron_jobs", {})
        reminder_freq = profile.get("reminder_freq", "每顿都提醒")

        chat_ids = get_chat_ids_for_member(member_id)
        if not chat_ids:
            lost_jobs.append({
                "member_id": member_id,
                "name": name,
                "issue": "no_chat_id",
                "detail": f"在 group_map.json 中找不到 {member_id} 的 chat_id，跳过",
                "severity": "warning",
            })
            continue

        chat_id = chat_ids[0]

        for cron_key, job_id in cron_jobs.items():
            if not job_id:
                continue

            if job_id in existing_ids:
                valid_jobs.append({
                    "member_id": member_id,
                    "name": name,
                    "cron_key": cron_key,
                    "job_id": job_id,
                })
            else:
                is_weight = (cron_key == "weight")
                meal_type_zh = "体重"
                time_str = "08:00"

                if not is_weight:
                    meal_info = MEAL_TYPE_MAP.get(cron_key, ("", ""))
                    meal_type_zh = meal_info[0]
                    meal_eng = meal_info[1]
                    time_str = meals.get(meal_eng, "08:00")

                    if reminder_freq == "只提醒午餐和晚餐" and meal_eng == "breakfast":
                        continue
                    if reminder_freq in ("无", "其他"):
                        continue

                cmd = build_cron_command(name, style, chat_id, cron_key, meal_type_zh, time_str, is_weight)
                rebuild_commands.append(cmd)

                lost_jobs.append({
                    "member_id": member_id,
                    "name": name,
                    "cron_key": cron_key,
                    "lost_job_id": job_id,
                    "rebuild_name": cmd["name"],
                    "rebuild_schedule": cmd["schedule"],
                })

    return {
        "ok": True,
        "total_members": len(members),
        "valid_jobs": len(valid_jobs),
        "lost_count": len(rebuild_commands),
        "warnings": [j for j in lost_jobs if j.get("severity") == "warning"],
        "lost_jobs": [j for j in lost_jobs if j.get("severity") != "warning"],
        "rebuild_commands": rebuild_commands,
        "has_issues": len(rebuild_commands) > 0,
    }


def check_health_cron_exists():
    """Check if the system health-check cron job exists."""
    names = get_existing_job_names()
    return HEALTH_CHECK_CRON_NAME in names


def sync_to_github():
    """Sync members/ and group_map.json to GitHub backup repo."""
    result = {"ok": False, "steps": []}

    # 1. Ensure repo dir exists and is healthy
    needs_clone = False
    if not os.path.isdir(os.path.join(REPO_DIR, ".git")):
        needs_clone = True
    else:
        # Check if repo is corrupted (e.g. missing blobs after /tmp cleanup)
        code, out, err = run_cmd_in("git fsck --no-dangling 2>&1 | head -5", REPO_DIR, timeout=30)
        if code != 0:
            needs_clone = True
            result["steps"].append(f"git fsck: corrupted ({err.strip()[:80]})")

    if needs_clone:
        # Remove old repo from a safe CWD to avoid FileNotFoundError
        run_cmd(f"rm -rf {REPO_DIR}")
        result["steps"].append("removed corrupted repo")
        code, out, err = run_cmd(f"git clone git@github.com:weixudong808/fitness-coach--Hermes.git {REPO_DIR}")
        result["steps"].append(f"git clone: exit={code}")
        if code != 0:
            result["error"] = f"git clone failed: {err}"
            return result
        # Set git identity after fresh clone (new repo has no config)
        run_cmd_in('git config user.email "hermes-bot@users.noreply.github.com"', REPO_DIR)
        run_cmd_in('git config user.name "Hermes Bot"', REPO_DIR)

    # 2. Pull latest
    code, out, err = run_cmd_in("git pull --rebase", REPO_DIR)
    result["steps"].append(f"git pull: exit={code}")

    # 3. Copy members/ directory (excluding __pycache__)
    members_repo = os.path.join(REPO_DIR, "members")
    if os.path.isdir(MEMBERS_DIR):
        code, out, err = run_cmd(f"rm -rf {members_repo} && cp -r {MEMBERS_DIR} {members_repo}")
        result["steps"].append(f"cp members: exit={code}")
        # Clean __pycache__
        run_cmd(f"find {members_repo} -name '__pycache__' -type d -exec rm -rf {{}} + 2>/dev/null")

    # 4. Copy group_map.json (as group_map.json, not .example — it's a private repo)
    code, out, err = run_cmd(f"cp {GROUP_MAP_PATH} {os.path.join(REPO_DIR, 'group_map.json')}")
    result["steps"].append(f"cp group_map: exit={code}")

    # 4.5. Copy holographic memory_store.db (SQLite)
    if os.path.exists(MEMORY_STORE_PATH):
        # Use sqlite3 .backup to safely copy without corruption risk
        code, out, err = run_cmd(
            f"sqlite3 {MEMORY_STORE_PATH} '.backup {os.path.join(REPO_DIR, 'memory_store.db')}'",
            timeout=30
        )
        result["steps"].append(f"backup memory_store.db: exit={code}")

    # 4.6. Copy fitness-coach skill directory (SKILL.md, references/, scripts/)
    if os.path.isdir(SKILLS_DIR):
        skills_repo = os.path.join(REPO_DIR, "skills", "fitness-coach")
        code, out, err = run_cmd(f"rm -rf {skills_repo} && cp -r {SKILLS_DIR} {skills_repo}")
        result["steps"].append(f"cp skills/fitness-coach: exit={code}")
        run_cmd(f"find {skills_repo} -name '__pycache__' -type d -exec rm -rf {{}} + 2>/dev/null")

    # 4.7. Copy MCP SQLite database (fitness_data.db)
    if os.path.exists(MCP_DB_PATH):
        os.makedirs(os.path.join(REPO_DIR, "mcp-server"), exist_ok=True)
        code, out, err = run_cmd(
            f"sqlite3 {MCP_DB_PATH} '.backup {os.path.join(REPO_DIR, 'mcp-server', 'fitness_data.db')}'",
            timeout=30
        )
        result["steps"].append(f"backup fitness_data.db: exit={code}")

    # 5. Update .gitignore to NOT ignore members/ (it's currently gitignored)
    gitignore_path = os.path.join(REPO_DIR, ".gitignore")
    if os.path.exists(gitignore_path):
        with open(gitignore_path, "r") as f:
            content = f.read()
        # Remove "members/" line from .gitignore since we now want to track it
        lines = content.split("\n")
        new_lines = [l for l in lines if l.strip() != "members/"]
        if len(new_lines) != len(lines):
            with open(gitignore_path, "w") as f:
                f.write("\n".join(new_lines))
            result["steps"].append("updated .gitignore: removed members/ exclusion")

    # 6. Git add, commit, push
    code, out, err = run_cmd_in("git add -A && git diff --cached --quiet", REPO_DIR)
    if code == 0:
        result["steps"].append("git status: no changes, skip commit")
        result["ok"] = True
        result["committed"] = False
    else:
        tz = timezone(timedelta(hours=8))
        date_str = datetime.now(tz).strftime("%Y-%m-%d")
        msg = f"chore: daily backup — {date_str}"
        code, out, err = run_cmd_in(f'git commit -m "{msg}" && git push', REPO_DIR, timeout=60)
        result["steps"].append(f"git commit+push: exit={code}")
        if code == 0:
            result["ok"] = True
            result["committed"] = True
        else:
            result["error"] = f"git push failed: {err}"

    return result


def main():
    verify_system = "--verify-system" in sys.argv
    github_sync = "--github-sync" in sys.argv

    # ── Mode 1: Verify health-check cron itself ──
    if verify_system:
        exists = check_health_cron_exists()
        print(json.dumps({"exists": exists}, ensure_ascii=False))
        sys.exit(0 if exists else 1)

    # ── Mode 2: Full health check ──
    log("=== Health check started ===")
    report = check_all_crons()
    log(f"Members: {report['total_members']}, Valid jobs: {report['valid_jobs']}, Lost: {report['lost_count']}")

    # GitHub sync
    if github_sync:
        log("GitHub sync started")
        sync_result = sync_to_github()
        log(f"GitHub sync: ok={sync_result['ok']}, committed={sync_result.get('committed', False)}")
        report["github_sync"] = sync_result

    # Output report as JSON to stdout
    print(json.dumps(report, ensure_ascii=False, indent=2))

    if report["has_issues"]:
        log(f"ISSUES DETECTED: {report['lost_count']} lost jobs")
        sys.exit(1)
    else:
        log("All healthy")
        sys.exit(0)


if __name__ == "__main__":
    main()
