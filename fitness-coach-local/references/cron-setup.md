# Cron Job Setup Reference

## Hermes Cron System Internals

### Storage & limits
- Jobs stored in `~/.hermes/cron/jobs.json` (plain JSON array)
- **No job quantity limit** — confirmed in source `cron/jobs.py`, no `MAX_JOBS` constant
- `~/.hermes/cron/output/` — output directory for `deliver: "local"` jobs (we don't use this; our jobs use `deliver: "feishu:{chat_id}"`)

### How scheduling works (important misconception to avoid)
- **Scheduler is Python code** (`cron/scheduler.py`), NOT model-driven
- Scheduler reads entire `jobs.json` into memory, checks every few seconds if any job is due
- When a job triggers → spawns new session → feeds that ONE job's prompt to the model
- **The model never reads `jobs.json`** — it only sees its own single prompt per trigger
- Context window overflow from too many jobs is impossible

### Two-step relay pattern (script → Agent)
`onboard_member.py` (Python script) **cannot** call Hermes's `cronjob` tool. This creates a mandatory two-step relay:
1. **Script** (terminal): creates profile.json, copies bitable, updates group_map.json, returns JSON with meals/style/reminder_freq/weight_reminder
2. **Agent** (current conversation): reads script output → calls `cronjob` tool to create jobs → writes job_ids back to profile.json's `cron_jobs` field

All info needed for cron creation comes from the script return value + current context. No need to re-read group_map.json.

### Cron reminder ≠ data recording
Cron only sends a reminder message. When the member responds (e.g. sends a food photo), that triggers normal group message processing via fitness-coach skill. Two completely independent flows.

## Architecture Decision (2026-05-04)

### Two-tier strategy: per-member + global

| Service | Strategy | Why |
|---------|----------|-----|
| Meal reminders (S5) | **Per-member** cron | Each member has unique meal times, needs minute-level precision |
| Weight reminders (S6) | **Per-member** cron | Each member chooses daily/weekly/none independently |
| Weekly report (S3) | **Global** 1 cron | Unified time (Sun 22:00), unified data-collect logic |
| Monthly report (S4) | **Global** 1 cron | Unified time (1st of month), unified data-collect logic |

### Why not global polling for meals/weight?

Global cron (e.g. one job per meal type) can't handle diverse schedules: member A eats at 7:30, member B at 8:30 — a single 8:00 trigger either misses A or is too early for B. Per-member cron solves this with exact timing. Creation/deletion is fully automated via scripts.

### cron_jobs field in profile.json

Each member's cron job IDs are tracked in `profile.json` under `cron_jobs`:

```json
{
  "cron_jobs": {
    "meal_breakfast": "abc123",   // null if no breakfast cron
    "meal_lunch": "def456",
    "meal_dinner": "ghi789",
    "weight": "jkl012"           // null if none
  }
}
```

### Lifecycle

**Onboard:** `onboard_member.py` creates cron jobs based on meals/reminder_freq/weight_reminder, writes job_ids to profile.

**Update (e.g. coach changes meal time):** Agent reads old job_id from profile → deletes old job → updates profile → creates new job → writes new job_id. No separate script needed; Agent uses `cronjob` tool directly.

**Offboard:** Iterate all cron_jobs values → delete each → remove profile + group_map entry.

### Meal reminder prompt template (self-contained, no skill loading)

```
你是健身教练小卫的助手。
提醒会员"{member_name}"该吃{meal_type}了。
风格：{style}
发送到群：feishu:{chat_id}
请发送提醒消息。不要加载任何 skill。
```

### Weight reminder prompt template

```
你是健身教练小卫的助手。
提醒会员"{member_name}"称体重。
风格：{style}
发送到群：feishu:{chat_id}
请发送提醒消息。不要加载任何 skill。
```

## Weekly Report Cron Job

**Job ID:** `b211038fb7af`
**Schedule:** Every 7 days, forever
**Script:** `~/.hermes/scripts/weekly-report-collect.py`
**Skills loaded:** `fitness-coach`
**Delivery:** `feishu`

### How it works

1. `weekly-report-collect.py` runs first — reads `group_map.json`, filters members with `report_enabled=true`, queries each member's bitable via lark-cli, outputs JSON
2. The cron prompt instructs the agent to parse the JSON, generate per-member reports, send to each group, save summaries

### Creating similar cron jobs

```python
# Per-member meal reminder:
cronjob(
    action="create",
    name="饮食提醒-{member_name}-{meal_type}",
    schedule="07:30",         # cron expression or HH:MM (needs croniter)
    skills=[],                # no skill needed for simple reminder
    deliver=f"feishu:{chat_id}",
    enabled_toolsets=["terminal"],
    prompt=f"提醒会员{member_name}该吃{meal_type}了，风格{style}...",
    repeat=0                  # forever
)
```

### Where cron times are defined (change schedule → update ALL of these)

When changing a cron trigger time (e.g. weight reminder from 21:00 to 08:00), these locations must ALL be updated:

| # | File | What to change |
|---|------|---------------|
| 1 | `~/.hermes/SOUL.md` | Questionnaire text (第9项选项文案) |
| 2 | `SKILL.md` §7.1 | Judgment logic (创建 cron 的判断规则) |
| 3 | `SKILL.md` §6 S14 | Description text (提醒服务说明) |
| 4 | `SKILL.md` §10.4 | Spec table (weight_reminder 触发时间表) |
| 5 | `SKILL.md` §10.6.1 | Coach instruction table (教练指令→Agent操作) |
| 6 | `~/.hermes/cron/jobs.json` | Actual cron job (via `cronjob(action="update")`) |
| 7 | `~/.hermes/plans/skill-gap-analysis.md` | Legacy plan doc |
| 8 | `~/.hermes/plans/services-and-permissions.md` | Legacy plan doc (2 places) |
| 9 | Memory | AI's own reference for next session |

**⚠️ The actual cron job (#6) is the live system — don't forget to update it!** Use `cronjob(action="update", job_id=..., schedule=...)`, no need to delete+recreate.

After updating, also sync any existing member's `profile.json` if needed (usually not required for time-only changes).

### Key pitfalls

- `croniter` must be in Hermes venv, not system Python
- `script` path must be bare filename (relative to `~/.hermes/scripts/`)
- `repeat` defaults to 1 (one-shot); set to 0 for recurring
- Cron expression format (`0 9 * * 1`) may fail without croniter; use `7d` as fallback
- For per-member jobs: `deliver` must be `feishu:{chat_id}`, not just `feishu`
- When deleting a member, must delete ALL cron jobs listed in `cron_jobs` field first
- **No job quantity limit** in Hermes — jobs stored in `~/.hermes/cron/jobs.json` (plain JSON array), confirmed in source `cron/jobs.py`
- **Cron reminder ≠ data recording** — cron only sends a reminder message. When the member responds (e.g. sends a food photo), it triggers normal group message processing via fitness-coach skill. The two flows are completely independent.
- **Two-step relay required** — `onboard_member.py` (Python script) cannot call Hermes's `cronjob` tool. The script creates files (profile.json, group_map.json), then the Agent reads the script output and calls `cronjob` tool to create jobs, writing job_ids back to profile.json.
- **No need to read group_map.json during cron creation** — all info needed (name, chat_id, meals, style, etc.) comes from onboard script output + current context.
- **Model may skip 前置步骤** — Observed: when coach sends config commands like "给这个会员加体重提醒", model sometimes skips reading group_map.json and treats the group as unmapped (asking for member name/ID again). SKILL.md has been patched with stronger constraints, but if it recurs, the root cause is model not following the "read group_map first" instruction. Key signal: model says "还没配置过会员信息" when the member clearly exists.
