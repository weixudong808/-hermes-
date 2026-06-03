# GitHub Backup & Deployment Workflow

## Overview

The fitness-coach Hermes setup is version-controlled in a **private GitHub repo** for disaster recovery, local testing, and safe iteration.

**Repo:** `https://github.com/weixudong808/fitness-coach--Hermes` (private)

## Deployment Flow

```
Cloud (production) ←→ GitHub (private repo) ←→ Local (testing)
```

1. Cloud: make changes, test, `git push` to GitHub
2. Local: `git pull`, test changes in local Hermes
3. Local: fix bugs, `git push` back to GitHub
4. Cloud: `git pull`, apply updated files to `~/.hermes/`
5. Restart Hermes gateway to apply

**Rule: GitHub is the single source of truth. Never copy files directly between machines.**

## SSH Deploy Key Setup (per machine)

Each machine needs its own SSH key pair added to the GitHub repo's Deploy Keys.

```bash
# 1. Generate a new ED25519 key (per machine, with a unique label)
ssh-keygen -t ed25519 -C "hermes-server" -f ~/.ssh/github_deploy_key -N ""

# 2. Configure SSH to use this key for GitHub
cat >> ~/.ssh/config << 'EOF'
Host github.com
    HostName github.com
    User git
    IdentityFile ~/.ssh/github_deploy_key
    StrictHostKeyChecking accept-new
EOF
chmod 600 ~/.ssh/github_deploy_key ~/.ssh/config

# 3. Display the public key — copy this to GitHub
cat ~/.ssh/github_deploy_key.pub

# 4. Add to GitHub: Repo → Settings → Deploy keys → Add deploy key
#    - Title: descriptive (e.g. "hermes-cloud" or "hermes-local-mac")
#    - Key: paste the full public key line
#    - ⚠️ CHECK "Allow write access" (required for push)
```

**Verify connection:** `ssh -T git@github.com` should print auth success message.

**Local Hermes also needs its own key** — generate a separate one with a different label and add it as another Deploy Key.

## Files That Go Into Git

```
fitness-coach-hermes/
├── .gitignore
├── .env.example              # Template with placeholders (NO real secrets)
├── SOUL.md                   # Robot personality & rules (clean real IDs)
├── config.yaml               # Hermes config (clean API keys)
├── group_map.json            # ⚠️ Real data (private repo, no sanitization needed)
├── members/                  # ⚠️ All member profiles (private repo, synced daily by health_check.py)
│
├── skills/fitness-coach/
│   ├── SKILL.md
│   ├── scripts/
│   │   ├── onboard_member.py
│   │   ├── record_weight.py
│   │   ├── health_check.py
│   │   └── weekly-report-collect.py
│   ├── templates/
│   │   └── profile.json
│   └── references/
│       └── (all .md docs)
│
└── docs/
    └── README.md
```

## Files That NEVER Go Into Git

| File/Dir | Reason |
|----------|--------|
| `.env` | API secrets (FEISHU_APP_SECRET, GLM_API_KEY, etc.) |
| `sessions/` | Conversation history (too large, not useful) |
| `cron/jobs.json` | Cron IDs are machine-bound, can be rebuilt from config |
| `auth.json` | OAuth tokens |
| `logs/` | Runtime logs |
| `__pycache__/` | Compiled cache |

### ⚠️ 2026-05-06 Breaking Change: `members/` now tracked in Git

Previously `members/` was gitignored (PII concern). Since the repo is **private**, we now sync `members/` and `group_map.json` daily via `health_check.py --github-sync`. The `.gitignore` has been updated to remove the `members/` exclusion. **Sanitization is NOT required** for commits to this private repo.

## .gitignore

```
.env
sessions/
logs/
auth.json
__pycache__/
*.pyc
cron/jobs.json
```

## Manual Sync with Review (Coach Workflow)

When making bulk changes (SKILL.md, SOUL.md, scripts, group_map, members), the coach wants to **review all diffs before pushing**. Follow this pattern:

```bash
# 1. Diff key files against repo
diff /tmp/fitness-coach-hermes/SOUL.md /root/.hermes/SOUL.md
diff /tmp/fitness-coach-hermes/skills/fitness-coach/SKILL.md /root/.hermes/skills/fitness-coach/SKILL.md
diff /tmp/fitness-coach-hermes/group_map.json /root/.hermes/group_map.json
diff /tmp/fitness-coach-hermes/scripts/onboard_member.py /root/.hermes/skills/fitness-coach/scripts/onboard_member.py

# 2. Check for new/missing files in references/ and scripts/
for f in /root/.hermes/skills/fitness-coach/references/*.md; do
  fname=$(basename "$f")
  [ ! -f "/tmp/fitness-coach-hermes/skills/fitness-coach/references/$fname" ] && echo "新增: $fname"
done
for f in /root/.hermes/skills/fitness-coach/scripts/*.py; do
  fname=$(basename "$f")
  [ ! -f "/tmp/fitness-coach-hermes/skills/fitness-coach/scripts/$fname" ] && echo "新增: $fname"
done

# 3. Check members/ directory differences
ls /tmp/fitness-coach-hermes/members/  # repo version
ls /root/.hermes/members/               # local version
```

**Present diffs as a numbered checklist** grouped by file, with clear before→after descriptions. Wait for coach approval before proceeding with sync and push.

### Sync & Push (after approval)

```bash
REPO=/tmp/fitness-coach-hermes

# Copy updated files to repo staging
cp /root/.hermes/SOUL.md $REPO/
cp /root/.hermes/group_map.json $REPO/
cp -r /root/.hermes/skills/fitness-coach/ $REPO/skills/fitness-coach/

# Sync members/ (rsync not available on cloud — use cp -r)
cp -r /root/.hermes/members/ $REPO/

# Clean artifacts
find $REPO -name ".DS_Store" -delete
find $REPO -name "__pycache__" -type d -exec rm -rf {} +

# Commit and push
cd $REPO
git add -A
git diff --cached --stat  # final confirmation
git commit -m "sync: <brief description of changes>"
git push
```

## Automated Daily Backup (2026-05-06)

The `health_check.py --github-sync` script handles daily backup automatically:
1. Pulls latest from GitHub
2. Copies `members/` and `group_map.json` to repo staging dir
3. Removes `members/` from `.gitignore` if present
4. `git add -A && git commit && git push` (only if changes detected)

**No manual intervention needed.** This runs via the "系统健康检查" cron job at 03:00 daily.

## Sensitive Data Sanitization

**⚠️ Mostly obsolete for this private repo.** Kept for reference if repo ever becomes public.

### Manual replacement rules (only if repo goes public)

| Pattern | Replace with | Example |
|---------|-------------|---------|
| `ou_[a-f0-9]{20,}` | `{OPENID}` | `ou_c76485c09fb788c48c...` |
| `oc_[a-f0-9]{20,}` | `{CHAT_ID}` | `oc_52a2021d7da67e...` |
| `cli_[a-f0-9]{10,}` | `{APP_ID}` | `cli_a97e37774db8dcd2` |
| `recv[a-zA-Z0-9]{10,}` | `{RECORD_ID}` | `recvilqKEQFctK` |
| `tbl[a-zA-Z0-9]{8,}` | `{TABLE_ID}` | `tbl8qEBvezIs7FVx` |
| `fld[a-zA-Z0-9]{8,}` | `{FIELD_ID}` | `fldJ2eNvFY` |
| Real bitable tokens | `{BITABLE_TOKEN}` | `TGixbmcoEaiZ43sfX...` |
| Member real names | `会员示例` | `王小明` → `会员示例` |

### Automated scan (Python, run before every push)

```python
import os, re
work_dir = "/tmp/fitness-coach-hermes"
patterns = [
    (r'ou_[a-f0-9]{20,}', 'OpenID'),
    (r'oc_[a-f0-9]{20,}', 'Chat ID'),
    (r'cli_[a-f0-9]{10,}', 'App ID'),
    (r'recv[a-zA-Z0-9]{10,}', 'Record ID'),
    (r'tbl[a-zA-Z0-9]{8,}', 'Table ID'),
]
for root, dirs, files in os.walk(work_dir):
    dirs[:] = [d for d in dirs if not d.startswith('.')]
    for fname in files:
        if not fname.endswith(('.md', '.json', '.yaml', '.py')):
            continue
        fpath = os.path.join(root, fname)
        with open(fpath) as f:
            for i, line in enumerate(f.readlines(), 1):
                for pat, label in patterns:
                    for m in re.findall(pat, line):
                        print(f"⚠️ {os.path.relpath(fpath, work_dir)}:{i} [{label}] {m.strip()}")
```

### Automated sanitize (Python, for bulk cleaning)

```python
import re
for old, new in replacements.items():
    content = content.replace(old, new)
# Then regex sweep for anything missed:
content = re.sub(r'ou_[a-f0-9]{20,}', '{OPENID}', content)
content = re.sub(r'oc_[a-f0-9]{20,}', '{CHAT_ID}', content)
content = re.sub(r'cli_[a-f0-9]{10,}', '{APP_ID}', content)
content = re.sub(r'recv[a-zA-Z0-9]{10,}', '{RECORD_ID}', content)
content = re.sub(r'tbl[a-zA-Z0-9]{8,}', '{TABLE_ID}', content)
```

**⚠️ Always run scan AFTER sanitize to confirm zero leaks.**

## Cloud Environment Notes

- No `gh` CLI installed on cloud server (2026-05-05)
- No `rsync` installed on cloud server — always use `cp -r` instead (2026-05-08)
- Git operations use SSH deploy keys (not `gh` CLI or PAT)
- Cloud server SSH config: `~/.ssh/config` with `IdentityFile ~/.ssh/github_deploy_key`
- Cloud server lark-cli path: `/usr/local/bin/lark-cli` (not nvm path)
- Working directory for repo operations: `/tmp/fitness-coach-hermes` (temporary staging)

## Init / Push a New Architecture Backup

When creating or resetting the backup repo from scratch:

```bash
# 1. Stage files to temp dir (never work directly in ~/.hermes)
cp -r ~/.hermes/SOUL.md ~/.hermes/config.yaml ~/.hermes/group_map.json /tmp/fitness-coach-hermes/
cp -r ~/.hermes/skills/fitness-coach/ /tmp/fitness-coach-hermes/skills/fitness-coach/

# 2. Remove .DS_Store and __pycache__
find /tmp/fitness-coach-hermes -name ".DS_Store" -delete
find /tmp/fitness-coach-hermes -name "__pycache__" -type d -exec rm -rf {} +

# 3. Replace config/group_map with .example versions (keep only templates)
#    See sanitization section above for automated approach

# 4. Git init, commit, push
cd /tmp/fitness-coach-hermes
git init && git branch -m main
git add -A && git commit -m "feat: initial backup"
git remote add origin git@github.com:weixudong808/fitness-coach--Hermes.git
git push -u origin main
```

## Deploy Script (optional)

After `git pull`, a deploy script can sync files to `~/.hermes/`:

```bash
#!/bin/bash
REPO=~/fitness-coach-hermes
HERMES=~/.hermes
cp -r $REPO/skills/fitness-coach/* $HERMES/skills/fitness-coach/
cp $REPO/SOUL.md $HERMES/SOUL.md
echo "Done. Restart gateway: hermes gateway restart"
```

**⚠️ Never auto-deploy `.env` — always keep it manual.** The `.env` must be maintained separately on each machine and never committed to Git.

## SOUL.md Location

SOUL.md lives at `~/.hermes/SOUL.md` (system-level, NOT inside any skill). It defines the bot's identity, personality, and core behavioral rules. It must be backed up alongside the skill files.

### ⚠️ SOUL.md 容易被遗漏（2026-06-03 确认）

**现状：** GitHub 仓库实际缺少 SOUL.md，尽管文档一直写着应该包含。原因是 `health_check.py --github-sync` 的自动备份只同步 `members/` 和 `group_map.json`，不包含 SOUL.md。

**影响：** 如果服务器完全重置且 GitHub 是唯一恢复源，SOUL.md（机器人人格、规则、身份识别逻辑）将丢失，需要手动重建。

**修复方案（二选一）：**
1. **推荐：手动推送一次 SOUL.md 到仓库**，后续手动同步流程中保持包含即可（文档中 Manual Sync 步骤已包含 `cp SOUL.md`，但自动备份未覆盖）
2. 在 `health_check.py --github-sync` 中加入 SOUL.md 的同步（注意 SOUL.md 包含 coach_user_id，云端/本地值不同，直接同步可能覆盖本地版本）

**验证命令：** `git ls-tree --name-only HEAD | grep SOUL` — 应该返回 `SOUL.md`，如果无输出说明仓库缺失。
