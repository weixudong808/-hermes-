# Pitfalls & Architecture Notes

> Consolidated from `fitness-coaching-assistant` skill (draft v0.1) and Phase 0-2 testing.
> These are hard-won lessons that must travel with the operational skill.

## Two Feishu Apps, Two Identities

- **Hermes bot** (`cli_a9789ef1a0b85cd5`): handles group messaging via Gateway
- **lark-cli** (`cli_a961e26f03b85cb5`): handles API operations (bitable, contacts, docs) from terminal
- They are separate apps with separate permissions — resources created by one may not be accessible to the other
- **Cross-app bitable access**: A bitable created by Hermes bot is NOT accessible by lark-cli without explicit permission. Recommendation: create bitable via lark-cli, or grant cross-app permissions via Feishu admin console
- **Adding app as doc collaborator**: Do NOT use the "分享" (Share) dialog — bots are not searchable there. Correct path: **「...」→「...更多」→「添加文档应用」**

## lark-cli Gotchas

- **`--json` not `--data`**: The flag is `--json`, passing a flat JSON object
- **No `{\"fields\":{...}}` wrapping**: Pass the record object directly, returns error 800010701 otherwise
- **`api DELETE` is broken**: Returns empty output with exit code 1. Delete fields via Feishu UI instead
- **`hermes mcp add` CLI bug with `-y` flag**: Misinterprets `-y` as its own flag. Workaround: edit `~/.hermes/config.yaml` directly
- **Must specify `--folder-token`**: Without it, bitable gets auto-deleted by Feishu shortly after creation
- **Dashboard creation requires scope**: `base:dashboard:create` must be enabled in Feishu app permissions (returns HTTP 400 code 99991672 without it)
- **Table IDs are RANDOM on copy**: When copying a template, new table IDs differ. Always `+table-list` after copy

## lark-cli Token & Auth

- User identity: "卫" (feishu_id `ou_cbea6d5fcf1a240cdfd2e765dd97b00b`)
- Has refresh_token + offline_access scope — auto-refreshes as long as there's been ≥1 API call within 7 days
- Cron jobs will work (they count as activity). Only breaks after 7 consecutive days of zero activity
- lark-cli does NOT need to be added to groups — it's a backend terminal tool, members never see it

## Bitable Field Operations

- **Field update requires `type`**: PUT endpoint requires `type` parameter even when only renaming. Always include `{\"field_name\":\"新名\",\"type\":<original_type>}` or get error 99992402
- **Field rename order**: When renaming fields where target name exists as another field, rename in dependency order to avoid name conflicts
- **Date field format**: Millisecond timestamps (e.g., `1746057600000`) — verified Phase 0
- **Linked record fields**: Pass record_id as plain string (e.g., `\"关联课次\":\"recXXXXXX\"`)
- **Sequential write for linked records**: Must write course first → get record_id → then write exercises. 1 course + N exercises = 1+N serial lark-cli calls

## Dashboard Limitations

- Feishu Bitable API only supports GET dashboards (list) and POST copy. No endpoint for creating/configuring widgets
- Widgets can only be added through Feishu web/app UI
- If automated widget management is needed, only workaround is browser automation

## Z.AI MCP Servers

- **Vision is MCP-only**: Z.AI Coding Plan does NOT have a standalone vision model API. Must use `zai-vision` MCP (GLM-4.6V). Do NOT configure `auxiliary.vision` with a Z.AI model — GLM-5V-Turbo returns "当前订阅套餐暂未开放GLM-5V-Turbo权限"
- **MCP image input**: Works best with local file paths, not raw URLs. Download Feishu image to temp file first
- **MCP Python dependency**: Fresh installs may lack `mcp` package. If `hermes mcp test` fails, run: `pip install "mcp[cli]>=1.6.0"` in Hermes venv (`/Users/quhongfei/Hermes-Agent/.venv/`)
- **MCP tool naming**: Tools prefixed as `mcp_{server}_{tool}` — hyphens become underscores

## Quota (Z.AI Max Plan)

| Resource | Limit | Notes |
|----------|-------|-------|
| GLM-5.1 | ~1600 prompts/5h | 60 groups × 5 interactions = 300/day, sufficient |
| Vision MCP | Shared prompt pool | 60 × 3 photos = 180/day, sufficient |
| Search MCP | 4000/month | ~50/month occasional lookups, sufficient |

## Memory Constraints

- Hermes memory: 2,200 char limit; user profile: 1,375 char limit
- Member data (diet logs, training logs, profiles) MUST go in files under `~/.hermes/members/`, NOT in Hermes memory
- Memory is only for coach preferences and session-level facts

## Cron Job Notes

- **croniter package**: Required for cron expressions, installed in Hermes venv (`/Users/quhongfei/Hermes-Agent/.venv/`)
- **Script paths**: Must be relative to `~/.hermes/scripts/`, not absolute or `~/` prefixed
- **repeat: 0** means permanent loop
- **enabled_toolsets**: Limit to `[\"terminal\",\"file\",\"session_search\"]` to reduce token overhead
- **Cron scheduler is Python code, not model**: `cron/scheduler.py` reads `jobs.json`, checks timing in pure Python. The model never sees `jobs.json` — it only receives its own single prompt when triggered. Context overflow from too many jobs is impossible.
- **Two-step relay for per-member cron**: `onboard_member.py` (script) creates files → Agent (tool call) creates cron jobs. Scripts CANNOT call the `cronjob` tool.
- **Per-member deliver format**: `deliver: "feishu:{chat_id}"`, NOT `"feishu"`. Global jobs (reports) use `"feishu"`.
- **No script needed for meal/weight reminders**: Prompt is self-contained (member name + style + chat_id baked in). Only reports need scripts for data collection.
- **Member offboard order**: Delete cron jobs FIRST (read from `cron_jobs`), then delete profile.json. Reversing this order loses the job IDs.

## Skill Trigger Architecture (CRITICAL)

### 未映射群问卷入口必须在 SOUL.md，不能在 skill 内

**Bug discovered 2026-05-03:** fitness-coach skill 的触发条件是"群已在 group_map.json 中映射"，但入群问卷的触发逻辑又写在这个 skill 的第七节里。这形成逻辑死循环：未映射群 → skill 不加载 → 问卷逻辑永远不会执行 → 新群永远收不到问卷。

**Fix:** 问卷发送入口移到 SOUL.md（"群聊入口判断"章节），每次对话必加载，不受 skill 触发条件限制。fitness-coach skill 第七节保留问卷回答解析和建档流程，但删除发送触发。

**教训：** 当某个 skill 的触发条件是"A 类场景"，但规则中又包含"非 A 类场景的处理"时，非 A 部分必须放在 SOUL.md 或更高层级的配置中。

### chat_id 必须从 Source 行获取

**Bug discovered 2026-05-03:** 模型在新群中错误使用了 Home Channels 中的 chat_id（DM/Home 的 ID），而非当前群聊的实际 ID。

**正确做法:** chat_id 从 Hermes 会话上下文的 Source 行读取，格式为 `Feishu (Group chat oc_xxxxx)`，其中 `oc_xxxxx` 才是当前群的真实 chat_id。**不要**使用 Home Channels 中的 ID。

**Fix:** 在 SOUL.md 中加了明确指引："从 Source 行读取 chat_id，不要用 Home Channels 的 ID"。

## Data Discipline

- All project files must live under `~/.hermes/` — never ~/Documents, ~/Desktop, etc.
- Do not filter messages by sender (coach vs member) — too error-prone. Respond to all messages in the group
- Cross-group isolation is framework-level: Hermes gives each group an independent session via chat_id

## Feishu Gateway Connection Mode

- **Current mode: WebSocket** (`FEISHU_CONNECTION_MODE=websocket`)
- Hermes 主动连接飞书服务器，不需要公网 IP
- **Verification Token 和 Encrypt Key 在 WebSocket 模式下不需要** — 只有 HTTP 回调模式才需要
- 飞书 .env 中只需 `FEISHU_APP_ID` + `FEISHU_APP_SECRET`
- HTTP 回调模式需要公网地址 + 验证 Token + 加密 Key，WebSocket 模式更适合家庭网络部署

## Multi-Environment Profile Strategy

- **测试环境**: `default` profile，跑在本地 Mac
- **正式环境**: `prod` profile（`hermes profile create prod --clone` 创建，已克隆 config/.env/skills）
- 两个 profile 共享 skills，但 config / memory / sessions / group_map 完全隔离
- **不能同时跑两个 gateway**（端口冲突），切换流程：`hermes gateway stop` → `hermes --profile prod gateway start`
- **⚠️ gateway stop 必须用对应 profile 的命令停**：如果不确定哪个在跑，先 `hermes gateway status`
- prod profile 的 .env 需要手动更新新企业的 `FEISHU_APP_ID` + `FEISHU_APP_SECRET`
- Profile wrapper 命令：`prod chat`、`prod gateway start` 等（需 `$HOME/.local/bin` 在 PATH 中）

### lark-cli 跨 Profile 切换

- lark-cli 凭证在 `~/.lark-cli/config.json`，是**全局的**，不随 profile 隔离
- 每次切换企业环境需要 `lark-cli login` 重新登录（输入目标企业的 App ID + App Secret）
- 如果两边不频繁切换，手动重新登录即可
- 各企业的 lark-cli App ID 记录：测试企业 `cli_a961e26f03b85cb5`，正式企业待填写

## Cloud Deployment Plan (正式环境)

正式环境将部署到阿里云 ECS，与本地测试环境物理隔离，不再需要切换 Profile。

### 云服务器配置

| 配置项 | 规格 | 说明 |
|--------|------|------|
| vCPU | 2 核 | Hermes 实际用不到 1 核 |
| 内存 | 4 GB | Hermes 实际占 ~150MB |
| 系统盘 | 120 GB SSD | 充裕 |
| 公网带宽 | 200 Mbps | 飞书 WebSocket 不需要高带宽 |
| 系统 | Ubuntu 22.04 LTS | 推荐 |
| 预估月费 | ~50-80 元 | |

### Hermes 资源占用实测（2026-05-01）

- Gateway 进程：~100 MB 内存，3% CPU
- MCP Server (zai-vision)：~3 MB
- lark-cli：按需启动，用完释放
- **Hermes 不做模型推理**，所有 LLM 调用发到智谱云端 API，本地只做消息收发

### 部署后的架构

- 本地 Mac：`default` profile，用于测试
- 阿里云：独立 Hermes 实例，`prod` profile（或直接 default）
- 两边完全独立，不再需要 gateway stop/start 切换
- 云服务器上的 lark-cli 只需登录一次正式企业的凭证

### 部署指南

本地已创建切换参考文档：`/Users/quhongfei/Hermes-Agent/profile-switch-guide.md`
云服务器部署文档待创建（购买服务器后按需编写）。

## Feishu Mention Gating（硬编码，无配置项）

飞书平台 adapter 不像 Discord/WhatsApp 那样支持 `require_mention` / `free_response_channels` 配置。@门控逻辑硬编码在 `feishu.py` 的 `_should_accept_group_message()` 中：

```
群消息 → _allow_group_message()（group_policy 权限检查）
        → 检查 @_all
        → 检查 mentions（@机器人）
        → 都没有 → 丢弃（不进 agent）
```

**没有"看到但不回复"模式。** 不 @就完全不进 agent，不是"进了但不回复"。

如需实现"监听所有消息但不 @不发言"，需改 `feishu.py` 源码（每次 Hermes 升级可能被覆盖）。相关源码位置：
- `_should_accept_group_message()`: `gateway/platforms/feishu.py` ~L3631
- `_allow_group_message()`: `gateway/platforms/feishu.py` ~L3597

## group_map.json vs profile.json 职责边界

| | group_map.json | profile.json |
|--|----------------|--------------|
| **定位** | 运行时索引，每次消息/cron 必查 | 会员详细档案 |
| **触发者** | SOUL.md（每次加载） | fitness-coach skill |
| **存什么** | 身份判断、路由定位、表格地址、风格、提醒配置 | 身高、健康条件、健身水平、饮食偏好等详细信息 |
| **路径** | `~/.hermes/group_map.json` | `~/.hermes/members/{member_id}/profile.json` |
| **谁读** | SOUL.md 入口判断 + skill 取表格 ID/风格 | skill 建档/生成报告时读 |

**冗余字段**：`style` 和 `member_name` 两边都有。group_map 存是为了运行时立刻可用（不用多读一次 profile）；profile 存是为了建档完整性。

## 模型计算不可靠 → 用脚本代替（核心原则）

**现象：** 让 GLM 模型计算毫秒时间戳写入多维表格日期字段，模型要么跳过日期字段不传，要么算出错误的时间戳。同样的问题也出现在让模型拼复杂 JSON、多步串行操作时（容易漏步骤）。

**原则：** 涉及**精确数值计算**（时间戳、日期格式转换）或**多步串行原子操作**（创建文件 → 调 API → 更新索引）的场景，不要让模型直接做，写成 Python 脚本让模型调用。

**已有脚本：**
- `onboard_member.py` — 新会员建档（创建 profile + 复制 bitable + 更新 group_map，3 步原子化）
- `record_weight.py` — 体重记录（自动计算当天 CST 0 点时间戳 + 写入 bitable）
- `weekly-report-collect.py` — 周报数据收集（遍历会员 + 拉 API + 统计）

**判断标准：** 如果某个操作模型执行两次出错一次以上，就该写脚本了。

## 模型跳过"前置步骤"（实测 2026-05-04）

**现象：** 已映射群中，教练发送配置指令（如"给这个会员加体重提醒"），模型跳过读取 group_map.json 的前置步骤，将该群误判为"未映射群"，要求教练重新提供会员姓名和 ID。

**根因：** GLM 模型在处理教练指令时，可能跳过 SKILL.md 中定义的"前置步骤"（先读 group_map.json 匹配 chat_id），直接按指令关键词匹配到"新会员建档"流程。

**已修复：** SKILL.md "前置步骤"章节加了强约束："如果 chat_id 在 group_map.json 中找到了 → 绝对不要走未映射群流程"。

**如果复现：** 关键信号是模型回复"还没配置过会员信息"或要求提供 member_feishu_id，而该群实际上已在 group_map.json 中。

## GLM 模型 @ 检测不可靠（实测 2026-05-04）

**现象：** 会员在飞书群中 `@hermes 今日体重66`，模型推理过程中判定"没有 @机器人"。

**根因：** GLM-5-Turbo 在飞书群聊场景下，无法可靠识别消息中的 @ 机器人。这导致所有依赖 @ 触发的功能（体重记录、总结请求、查询请求等）都可能漏触发。

**已采取的设计决策：** 对"健身群只有3人（教练+机器人+会员）"这一场景，所有会员主动发起的意图明确操作，**尽量去掉 @ 要求**：
- 体重记录：已改为"体重关键词 + 数字"触发，不需要 @（v2.0.1）
- 饮食照片：本就不需要 @（包含图片自动触发）

**仍保留 @ 要求的功能：** 总结/周报/月报请求、训练查询、教练专属指令（改称呼/改风格/改时间等）。这些如果误触发影响较大，且出现频率低，可以接受偶尔漏触发。

**注意：** 如果后续换用更强大的模型（如 GPT-4o、Claude），@ 检测可能更可靠，届时可以重新评估是否恢复 @ 要求。

## Related Skills

- `fitness-coaching-assistant` (productivity/): earlier draft with full architecture docs, templates, and Feishu setup references. Superseded by `fitness-coach` for operational workflow, but still useful for onboarding/setup reference material.
