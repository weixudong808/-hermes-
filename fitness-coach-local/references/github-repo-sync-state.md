# GitHub 仓库同步状态

## 仓库信息

- **URL:** https://github.com/weixudong808/fitness-coach--Hermes
- **可见性:** 公开（public）— `git clone` 无需认证即可读取
- **默认分支:** main
- **⚠️ 本地 push 需要 GitHub 认证**（当前 macOS 未配置：无 SSH key、无 `gh auth login`、无 credential helper）。需先 `gh auth login` 或配置 Personal Access Token 才能推送到此仓库

## 仓库内容清单

```
.
├── README.md
├── SOUL.md                          # 系统提示词（云端版，144行）
├── config.example.yaml              # 配置示例
├── .env.example                     # 环境变量示例
├── group_map.example.json           # 群映射示例
├── group_map.json                   # 线上群映射（含会员数据）
├── members/                         # 7 个会员档案
│   ├── maomao/profile.json
│   └── member_*/profile.json
├── skills/fitness-coach/
│   ├── SKILL.md                     # 核心工作流（云端版，721行）
│   ├── templates/profile.json       # 会员档案模板
│   ├── scripts/
│   │   ├── onboard_member.py        # 建档脚本
│   │   ├── record_weight.py         # 体重记录脚本
│   │   ├── health_check.py          # 健康检查脚本
│   │   ├── restore_cron_jobs.py     # Cron 恢复脚本
│   │   └── weekly-report-collect.py # 周报数据收集脚本
│   └── references/                  # 15 个参考文档
└── .gitignore
```

## 版本差异（截至 2026-05-05）

**仓库 v2.1.0 vs 线上 v2.0.0**

### 仓库领先于线上的改动

| 类别 | 变更内容 |
|------|---------|
| **strict_mode** | 云端 strict_mode 为 bot-only，去掉所有 `--as user`（线上仍带 `--as user`） |
| **lark-cli 路径** | 默认 `~/.nvm/.../lark-cli`，云端用 `LARK_CLI_PATH` 环境变量覆盖（线上硬编码本地路径） |
| **+base-copy 参数** | 去掉 `--folder-token`（bot 缺文件夹权限）和 `--time-zone`（导致 800004006 错误） |
| **防重复建档** | 新增 `ls ~/.hermes/members/` 检查，避免已有会员在新群回答问卷时创建重复档案 |
| **自动分享给教练** | onboard_member.py 新增 drive API 自动把教练加为多维表格协作者（full_access） |
| **手动降级流程** | 脚本失败时 5 步 fallback（手动建档 + 手动写 group_map + 手动建 cron） |
| **体重日期字段** | 日期不会自动填充，必须传毫秒时间戳（线上写的"自动填充"是错误的） |
| **模板表格** | 标记为 ✅已修复（4 张表齐全），线上还标记为"已知问题" |
| **execute_code 注意** | `read_file` 返回格式不含 `content` 键，需用 `terminal(cat ...)` 替代 |

### 线上有、仓库缺少

| 文件 | 说明 |
|------|------|
| `references/cloud-deployment-pitfalls.md` | 云端部署踩坑记录（lark-cli default-as、session.py 补丁、版本差异、PATH、gateway 运维） |

### 新增文件（仓库独有）

| 文件 | 说明 |
|------|------|
| `references/github-backup-workflow.md` | GitHub 备份与部署流程 |

## 本地作为云端测试环境

**用途：** 在本地 Hermes 修改 SKILL.md / SOUL.md → 测试通过 → push 到 GitHub → 云端 pull 或 scp 更新。

### 同步步骤

1. 从 GitHub clone 仓库到本地临时目录
2. **备份**本地现有 skill 和 SOUL.md（`cp -r` 到备份目录）
3. 用仓库内容覆盖 `~/.hermes/skills/fitness-coach/` 和 `~/.hermes/SOUL.md`
4. 复制 `members/` 到 `~/.hermes/members/`（脚本读取此路径）
5. 复制 `group_map.json` 到 `~/.hermes/group_map.json`
6. 本地测试核心功能（建档、训练记录、周报等）
7. 测试通过后，改好的文件 push 回 GitHub
8. 云端 pull 或 scp 覆盖更新

### 本地独有的文件（覆盖前需备份）

| 文件 | 说明 |
|------|------|
| `references/cloud-deployment-pitfalls.md` | 云端部署踩坑记录 |
| `references/github-repo-sync-state.md` | 本同步状态文档 |
| `references/cron-configuration.md` | Cron 配置记录 |
| `references/design-decisions.md` | 设计决策 |
| `references/github-backup-workflow.md` | 备份流程 |
| `references/onboarding.md` | 入群流程 |

### 无法从仓库还原的部分

- **Hermes 版本差异**：本地 v0.11.0，云端 v0.12.0
- **lark-cli 认证**：本地是个人飞书账号，云端是企业应用
- **group_map.json**：映射的 chat_id 是线上的，本地群 chat_id 不同

## 同步方向

**正确方向：仓库 ↔ 云端**（仓库是同步桥梁，本地作为测试环境）

同步前需确认：
1. 本地独有文件应先备份，避免覆盖丢失
2. 同步后需验证 cron job、多维表格写入等核心功能正常
3. ⚠️ 不要用 git clone 直接覆盖 `~/.hermes/skills/`，应逐文件对比后手动同步
