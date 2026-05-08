# Cloud Migration: Environment Variables & File Inventory

> Created: 2026-05-04
> Purpose: Quick reference for migrating fitness-coach architecture to a new environment

## Environment Variables (set in ~/.hermes/.env or export)

| Variable | Used By | Default (local Mac) | Cloud Value |
|----------|---------|--------------------|--------------|
| `LARK_CLI_PATH` | `onboard_member.py`, `record_weight.py` | `~/.nvm/versions/node/v20.20.0/bin/lark-cli` | `/usr/local/bin/lark-cli` |
| `BITABLE_TEMPLATE_TOKEN` | `onboard_member.py` | `TGixbmcoEaiZ43sfXvQcZ513nnf` (test enterprise) | `EMy6bp9iLagx7CsOlxgcf1uSnSb` (formal enterprise, 4 tables) |

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

1. **Hermes source code**: `session.py` line 103-106 must be patched (Source format: `Group chat {chat_id} ({chat_name})`). **⚠️ 用 sed 修改 Python 多行代码会破坏缩进，必须用 Python 脚本替换**（见下方 sed 踩坑记录）
2. **`.env`**: `FEISHU_ALLOW_ALL_USERS=true` required
3. **Gateway restart**: must use `--system` flag on cloud
4. **lark-cli auth**: must complete `lark-cli auth login` (user identity)
5. **Cloud Hermes PATH**: 阿里云一键安装脚本将 Hermes 装在 `/usr/local/lib/hermes-agent/venv/bin/`，部署文档只加了 uv 的 PATH（`/root/.local/bin`），没加 hermes 的 PATH。需手动添加：
   ```bash
   echo 'export PATH="/usr/local/lib/hermes-agent/venv/bin:$PATH"' >> ~/.bashrc
   source ~/.bashrc
   ```
   否则 SSH 后 `hermes` 命令找不到。
6. **Full migration plan**: see `~/.hermes/plans/migration-plan-local-to-cloud.md`

## sed 替换 Python 代码踩坑记录 ⚠️

**问题：** 迁移手册步骤 4 用 `sed` 将 session.py 中一行 Python 替换为多行 if/else，导致 IndentationError（缩进丢失），gateway 无法启动。

**根因：** sed 处理 `\n` 换行时不会自动加缩进，替换后的 Python 代码 `if` 语句下面没有缩进。

**正确做法：用 Python 脚本修改 Python 源码：**
```python
python3 -c "
import pathlib
p = pathlib.Path('/usr/local/lib/hermes-agent/gateway/session.py')
src = p.read_text()
old = 'parts.append(f\"group: {self.chat_name or self.chat_id}\")'
new = '''if self.chat_name:
    parts.append(f\"Group chat {self.chat_id} ({self.chat_name})\")
else:
    parts.append(f\"Group chat {self.chat_id}\")'''
src = src.replace(old, new)
p.write_text(src)
"
```
**原则：永远不要用 sed 修改多行 Python 代码，用 Python 脚本。**
