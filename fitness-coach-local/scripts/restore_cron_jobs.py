#!/usr/bin/env python3
"""Restore all cron jobs from member profiles.

When jobs.json gets lost/corrupted, this script reads all member profiles,
validates their cron job IDs against the scheduler, and prints a rebuild plan.

Usage:
    python3 restore_cron_jobs.py          # Dry-run: show what needs rebuilding
    python3 restore_cron_jobs.py --fix    # Actually print Hermes cronjob commands

Output (JSON to stdout):
    {"ok": true, "total_members": N, "lost_jobs": [...], "valid_jobs": [...]}

This script does NOT call Hermes cronjob tool directly (it's a Python script).
It outputs the commands/params that the AI assistant should execute.
"""

import json
import os
import subprocess
import sys

# ── Paths ────────────────────────────────────────────────────────────────
HERMES_HOME = os.path.expanduser("~/.hermes")
MEMBERS_DIR = os.path.join(HERMES_HOME, "members")
GROUP_MAP_PATH = os.path.join(HERMES_HOME, "group_map.json")
JOBS_JSON_PATH = os.path.join(HERMES_HOME, "cron", "jobs.json")


def load_json(path):
    """Load JSON file, return dict or None."""
    if not os.path.exists(path):
        return None
    with open(path, "r") as f:
        return json.load(f)


def get_existing_job_ids():
    """Get set of job IDs currently in jobs.json."""
    data = load_json(JOBS_JSON_PATH)
    if not data or "jobs" not in data:
        return set()
    return {job["id"] for job in data["jobs"]}


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


def build_cron_command(member_name, style, chat_id, cron_key, meal_type_zh, time_str, is_weight=False):
    """Build the Hermes cronjob create parameters as a dict."""
    style_desc = {
        "energetic": "活泼鼓励，多用表情",
        "professional": "简洁专业",
        "gentle": "温和关怀，耐心引导",
        "strict": "直接",
    }

    if is_weight:
        prompt = (
            f"你是健身教练小卫的助手。提醒会员\"{member_name}\"称一下体重。\n"
            f"风格：{style}（{style_desc.get(style, '')}）。\n"
            f"请发送提醒消息到当前群，内容类似：\"{STYLE_PROMPTS.get(style, STYLE_PROMPTS['gentle'])['weight'].format(name=member_name)}\"。\n"
            f"用 send_message 工具发送，target 用 \"origin\"。不要加载任何 skill。"
        )
        name = f"{member_name}-体重提醒"
        schedule = "0 8 * * *"  # daily 08:00
    else:
        prompt = (
            f"你是健身教练小卫的助手。提醒会员\"{member_name}\"该吃{meal_type_zh}了。\n"
            f"风格：{style}（{style_desc.get(style, '')}）。\n"
            f"请发送提醒消息到当前群，内容类似：\"{STYLE_PROMPTS.get(style, STYLE_PROMPTS['gentle'])['meal'].format(name=member_name, meal_type=meal_type_zh)}\"。\n"
            f"用 send_message 工具发送，target 用 \"origin\"。不要加载任何 skill。"
        )
        name = f"{member_name}-{meal_type_zh}提醒"
        # Parse HH:MM to cron
        parts = time_str.split(":")
        if len(parts) == 2:
            h, m = parts
            schedule = f"{m} {h} * * *"
        else:
            schedule = "0 8 * * *"  # fallback

    return {
        "action": "create",
        "name": name,
        "schedule": schedule,
        "deliver": f"feishu:{chat_id}",
        "enabled_toolsets": ["terminal"],
        "prompt": prompt,
        "profile_cron_key": cron_key,  # for reference: which field to update in profile
    }


def main():
    fix_mode = "--fix" in sys.argv

    existing_ids = get_existing_job_ids()

    # Scan all members
    members = []
    if os.path.isdir(MEMBERS_DIR):
        for dirname in sorted(os.listdir(MEMBERS_DIR)):
            profile_path = os.path.join(MEMBERS_DIR, dirname, "profile.json")
            profile = load_json(profile_path)
            if profile:
                members.append((dirname, profile))

    lost_jobs = []
    valid_jobs = []
    all_commands = []

    for member_id, profile in members:
        name = profile.get("name", member_id)
        style = profile.get("style", "energetic")
        meals = profile.get("meals", {})
        cron_jobs = profile.get("cron_jobs", {})
        weight_reminder = profile.get("weight_reminder", "none")
        reminder_freq = profile.get("reminder_freq", "每顿都提醒")

        chat_ids = get_chat_ids_for_member(member_id)
        if not chat_ids:
            # Try to use the first chat_id we can find
            lost_jobs.append({
                "member_id": member_id,
                "name": name,
                "issue": "no_chat_id",
                "detail": f"在 group_map.json 中找不到 {member_id} 的 chat_id，跳过"
            })
            continue

        # Use the first chat_id (primary group)
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
                    "status": "valid"
                })
            else:
                # Job is lost, build rebuild command
                is_weight = (cron_key == "weight")
                meal_type_zh = "体重"
                time_str = "08:00"

                if not is_weight:
                    # Extract meal type
                    meal_key = MEAL_TYPE_MAP.get(cron_key, ("", ""))
                    meal_type_zh = meal_key[0]
                    meal_eng = meal_key[1]  # breakfast/lunch/dinner
                    time_str = meals.get(meal_eng, "08:00")

                    # Check if this meal should have a reminder
                    if reminder_freq == "只提醒午餐和晚餐" and meal_eng == "breakfast":
                        continue
                    if reminder_freq == "无" or reminder_freq == "其他":
                        continue

                cmd = build_cron_command(name, style, chat_id, cron_key, meal_type_zh, time_str, is_weight)
                all_commands.append(cmd)

                lost_jobs.append({
                    "member_id": member_id,
                    "name": name,
                    "cron_key": cron_key,
                    "lost_job_id": job_id,
                    "rebuild": cmd,
                    "status": "lost"
                })

    # Output
    result = {
        "ok": True,
        "total_members": len(members),
        "valid_jobs": len(valid_jobs),
        "lost_jobs": len(lost_jobs),
        "rebuild_commands": all_commands,
    }

    print(json.dumps(result, ensure_ascii=False, indent=2))

    if not fix_mode:
        print("\n⚠️  DRY RUN — 以上为检查结果，未执行任何操作。", file=sys.stderr)
        print("   运行 python3 restore_cron_jobs.py --fix 可输出重建指令。", file=sys.stderr)
    else:
        if all_commands:
            print(f"\n📋 需要重建 {len(all_commands)} 个 cron job，请用 Hermes cronjob 工具逐个执行。", file=sys.stderr)
        else:
            print("\n✅ 所有 cron job 状态正常，无需重建。", file=sys.stderr)


if __name__ == "__main__":
    main()
