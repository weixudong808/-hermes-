# Cloud Migration: Environment Variables & File Inventory

> Created: 2026-05-04
> Purpose: Quick reference for migrating fitness-coach architecture to a new environment

## Environment Variables (set in ~/.hermes/.env or export)

| Variable | Used By | Default (local Mac) | Cloud Value |
|----------|---------|--------------------|--------------|
| `LARK_CLI_PATH` | `onboard_member.py`, `record_weight.py` | `~/.nvm/versions/node/v20.20.0/bin/lark-cli` | `/usr/local/bin/lark-cli` |
| `BITABLE_TEMPLATE_TOKEN` | `onboard_member.py` | `TGixbmcoEaiZ43sfXvQcZ513nnf` (test enterprise) | Formal enterprise template token |

Both scripts use `os.environ.get("VAR", default)` — **no code changes needed**, just set the env vars.

## What to Copy (architecture only)

| File/Dir | Env-Dependent? | Notes |
|----------|:---:|-------|
| `SOUL.md` | ❌ | Pure rules |
| `fitness-coach/SKILL.md` | ❌ | Pure rules |
| `fitness-coach/templates/profile.json` | ❌ | Empty schema |
| `fitness-coach/references/` (10 files) | ❌ | Docs |
| `fitness-coach/scripts/onboard_member.py` | ⚠️ | Needs `LARK_CLI_PATH` + `BITABLE_TEMPLATE_TOKEN` |
| `fitness-coach/scripts/record_weight.py` | ⚠️ | Needs `LARK_CLI_PATH` |

## What NOT to Copy (environment-specific)

- `group_map.json` — test chat_ids/tokens don't transfer
- `members/` — test member data; real members auto-created via onboard flow
- `cron/jobs.json` — jobs auto-created per member
- **`~/.hermes/scripts/`** — contains **duplicate copies** of `onboard_member.py` (identical) and `weekly-report-collect.py` (**older version**). The canonical copies live in `skills/fitness-coach/scripts/`. Never copy the root `scripts/` dir — it will cause confusion about which is authoritative.
- **`profiles/prod/`** — `SOUL.md` inside is **outdated** (missing identity recognition + group chat entry rules), `config.yaml` is identical to root. Do not copy or use; the root `SOUL.md` is the only canonical version.
- **`所有必要文件的意思/`** — personal notes, not part of the runtime architecture.
- `plans/` — reference documents only; the migration plan itself may be useful to copy for reference but is not runtime-critical.

## Duplicate Files Trap ⚠️

```
~/.hermes/scripts/onboard_member.py          ← DUPLICATE of skill/scripts/ (identical, safe to ignore)
~/.hermes/scripts/weekly-report-collect.py   ← OLD VERSION (skill/scripts/ is newer with better docs)
~/.hermes/skills/fitness-coach/scripts/onboard_member.py   ← CANONICAL
~/.hermes/skills/fitness-coach/scripts/weekly-report-collect.py ← CANONICAL
```

**Rule: only migrate `skills/fitness-coach/scripts/`, never the root `scripts/`.**

## Other Cloud-Specific Steps

1. **Hermes source code**: `session.py` line 103-106 must be patched (Source format: `Group chat {chat_id} ({chat_name})`)
2. **`.env`**: `FEISHU_ALLOW_ALL_USERS=true` required
3. **Gateway restart**: must use `--system` flag on cloud
4. **lark-cli auth**: must complete `lark-cli auth login` (user identity)
5. **Full migration plan**: see `~/.hermes/plans/migration-plan-local-to-cloud.md`

## ⚠️ lark-cli Deployment Pitfalls (2026-05-04)

### lark-cli hermes workspace binding

On a fresh cloud server, lark-cli detects Hermes context but has no workspace config:
```
lark-cli config show → "hermes context detected but lark-cli not bound to hermes workspace"
```

**Fix:**
```bash
lark-cli config bind --source hermes
```
This creates `/root/.lark-cli/hermes/config.json` from the Hermes Agent config. Must be done once per deployment.

### strict_mode blocks user auth

After `config bind`, the workspace may be in `strict_mode: "bot-only"`. This blocks `lark-cli auth login`:
```
lark-cli auth login → "strict mode is bot-only, only bot identity is allowed"
```

**Impact:** `base:app:copy` (bitable copy) requires user identity. Bot-only mode causes onboard_member.py to fail at step "base-copy".

**Fix options:**
1. `lark-cli config strict-mode --value auto` (if administrator allows)
2. Or: grant `base:app:copy` permission to the bot app at [Feishu Open Platform](https://open.feishu.cn/app/cli_a97e37774db8dcd2/auth?q=base:app:copy) — **推荐此方案**（2026-05-04 已验证可行）

### Bot auto-shares bitable with coach (2026-05-04 added)

`onboard_member.py` now auto-shares the copied bitable with coach via **drive API** (not bitable API):
```
POST /drive/v1/permissions/{base_token}/members?type=bitable
{"member_type": "openid", "member_id": "{coach_openid}", "perm": "full_access"}
```
This uses `FEISHU_APP_ID` / `FEISHU_APP_SECRET` env vars to get `tenant_access_token`. Coach sees new tables in 「与我共享」automatically. If this step fails (e.g. missing env vars), the script logs a `[warn]` but does not abort.

### LARK_CLI_PATH env var

On cloud server, lark-cli is at `/usr/local/bin/lark-cli` (not the nvm path). Set in `~/.hermes/.env`:
```
LARK_CLI_PATH=/usr/local/bin/lark-cli
```
The `onboard_member.py` and `record_weight.py` scripts both check `LARK_CLI_PATH` as override.

## Manual Onboard Fallback (when script fails)

If `onboard_member.py` fails (e.g. lark-cli auth issue), the Agent must perform the steps manually:

1. **Create profile.json** with `write_file` tool at `~/.hermes/members/{member_id}/profile.json` (see templates/profile.json schema)
2. **Update group_map.json** with `write_file` tool — add new chat_id entry with `bitable_token: "PENDING"` and all table_ids as `"PENDING"`
3. **Create cron jobs** via `cronjob` tool (breakfast/lunch/dinner reminders + weight reminder)
4. **Update profile.json** again with cron job IDs
5. **Share bitable with coach** via drive API (see `references/lark-cli-base-commands.md` section "自动共享给教练")
6. **Notify coach** that bitable setup is pending (needs lark-cli user auth or bot permission grant)

**Key caveat:** `read_file` hermes_tool inside `execute_code` returns `{"status", "message", "path", "dedup", "content_returned"}` — NOT `{"content": "..."}`. If `execute_code` needs file contents, use `terminal(cat ...)` instead.
