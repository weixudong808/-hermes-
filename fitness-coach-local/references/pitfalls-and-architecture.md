# Pitfalls & Architecture Notes

> Consolidated from `fitness-coaching-assistant` skill (draft v0.1) and Phase 0-2 testing.
> These are hard-won lessons that must travel with the operational skill.

## lark-cli 与 Hermes 统一凭证（2026-05-22 迁移完成）

**2026-05-22 起，lark-cli 已切换为使用 Hermes 应用凭证。不再有两个独立应用。**

- **Hermes bot** (`cli_a9789ef1a0b85cd5`): 同时负责群消息收发和 API 操作（bitable 读写、复制、删除等）
- **lark-cli** 现在配置的也是 `cli_a9789ef1a0b85cd5`，与 Hermes 共享同一身份
- **旧 lark-cli 应用** (`cli_a961e26f03b85cb5`) 已弃用，仅用于早期创建的多维表格的所有权

### lark-cli 配置方式

```bash
# 非交互式初始化（推荐）
echo "$FEISHU_APP_SECRET" | lark-cli config init \
  --app-id "cli_a9789ef1a0b85cd5" \
  --app-secret-stdin \
  --brand "feishu"

# 初始化后 config.json 存储在 ~/.lark-cli/config.json
# app_secret 通过 stdin 传入，存储在 macOS Keychain（service: lark-cli/appsecret:cli_a9789ef1a0b85cd5）
```

### 凭证一致性

- `onboard_member.py` 通过 lark-cli 调用 API → 使用 Hermes 凭证 → 新建的多维表格归 Hermes 所有
- Hermes 可以直接通过 drive API 删除自己创建的表格（需 `space:document:delete` 权限）
- 现有会员表格（旧 lark-cli 应用创建的）已把 Hermes 加为协作者，读写不受影响

### 旧表格所有权问题

2026-05-22 之前创建的多维表格归旧 lark-cli 应用（cli_a961e26f03b85cb5）所有。Hermes 虽然有协作者权限可以读写，但**无法通过 API 删除**。只能手动在飞书 UI 中删除。

### 添加应用为文档协作者

Do NOT use the "分享" (Share) dialog — bots are not searchable there. Correct path: **「...」→「...更多」→「添加文档应用」**. This is also **required for API access** (not just UI sharing) — see "三层权限模型" section below

### 模板表格复制的前置条件（2026-05-22 踩坑）

**即使 Hermes 有 `base:app:copy` scope，也需要把 Hermes 添加为模板表格的"文档应用"才能复制。** 否则报 `800004011 forbidden`。

**操作方法：** 模板表格 → 右上角「...」→「更多」→「添加文档应用」→ 搜索 Hermes 应用（`cli_a9789ef1a0b85cd5`）→ 添加

这一步只能手动完成，drive API 的 permission.members 接口无法添加应用为文档协作者（只能添加人/群）。

## Multi-Environment Bitable Ownership（2026-05-22 实测）

**核心事实：多维表格的所有权跟随创建者应用，不跟随飞书组织。**

**场景：** 本地环境从 GitHub 克隆了云端生产环境的代码和数据（group_map.json 中有所有 bitable_token），但本地 Hermes bot 和本地 lark-cli 都无法访问这些表格（403 Forbidden）。

**原因：** 多维表格由**云端生产环境的 Hermes bot** 创建。虽然 bitable_token 是全局唯一的（任何环境都能引用），但 API 访问权限绑定在创建者应用上。本地 bot（即使同一个飞书组织）如果没有被显式授予协作者权限，就无法读写。

**⚠️ lark-cli 配置了某个 app ≠ 该 app 拥有资源。** `lark-cli auth status` 显示 app_id 只是"当前用哪个身份调 API"，不代表该 app 拥有 group_map.json 里记录的多维表格。

**排查方法：**
1. `lark-cli base +base-get --base-token {token}` → 403 = 当前 app 无权访问
2. 用不同 app 的 tenant_access_token 直接调 `/open-apis/bot/v3/info/` 获取 open_id
3. 再调 `/open-apis/drive/v1/permissions/{token}/members?type=bitable` 检查权限列表

**解决方案（3 选 1）：**
1. **从有权限的环境加协作者**（推荐）：在拥有者应用所在的环境（云端）执行 `drive permission.members create`，给目标 bot 加 `full_access`
2. **手动在飞书 UI 加权限**：表格创建者账号登录 → 分享 → 搜索目标 bot
3. **重建所有表格**：用目标 bot 重新创建，迁移数据（工作量大，不推荐）

**教训：** 环境切换（本地↔云端）不能只同步配置文件和 bitable_token，还必须确保 API 访问权限。group_map.json 的 bitable_token 在跨环境场景下只是一个地址引用，不代表"我有权访问"。

## 飞书多维表格 API 访问的三层权限模型（2026-05-22 实测，已纠正）

**核心发现：飞书多维表格的 API 访问需要同时满足三个独立的权限层，缺一不可。**

### 第一层：API Scope（接口权限）

在飞书开放平台「权限管理」中开通的权限，控制应用能调用哪些 API 端点。

| Scope | 名称 | 控制范围 |
|-------|------|---------|
| `bitable:app` | 查看、评论、编辑和管理多维表格 | 创建/删除多维表格，读写表格的表、字段、记录 |

**⚠️ `bitable:bitable` scope 已废弃（2025年起），合并到 `bitable:app` 中。** 在飞书开放平台搜 `bitable:bitable` 会显示"没有找到结果"，这是正常的。只需开通 `bitable:app` 即可。

### 第二层：文档应用（Document App）—— 最容易被忽略！

**这是导致 91403 Forbidden 的最常见原因。** 即使应用有 API Scope + UI 协作者权限，如果该应用没有被添加为多维表格的"文档应用"，API 调用仍然 403。

**添加方法：** 打开多维表格 → 右上角 **「...」→「更多」→「添加文档应用」** → 搜索目标应用名称 → 添加

**⚠️ 注意区分两种 UI 入口：**
- 「分享」→「管理协作者」= 普通协作者权限（可阅读/可编辑/可管理）→ **不够！**
- 「...」→「更多」→「添加文档应用」= 文档应用授权 → **API 访问的关键！**

**实测证明：** Hermes bot 在 UI 中已被添加为「可管理」协作者，`bitable:app` scope 也已开通，但仍然 91403。加上"文档应用"后才能正常访问。

### 第三层：UI 协作者权限

在飞书 UI 的「分享」→「管理协作者」中添加的权限。这一层与 API Scope 和文档应用都是独立的。

### tenant_access_token 缓存注意事项

新增 API Scope 或文档应用后，已有的 tenant_access_token **不会立即生效**（缓存约 2 小时）。飞书不提供强制刷新 token 的 API。只能等 token 过期后自动刷新。

### 诊断清单

| 症状 | 原因 |
|------|------|
| 自己创建的表格能读写，别人的 403 | 未添加为"文档应用"（第二层） |
| 所有表格都 403（包括自己创建的） | 缺 `bitable:app` scope（第一层） |
| UI 有协作者权限但 API 403 | 未添加为"文档应用"（第二层） |
| lark-cli 403 但 curl + tenant_access_token 可以 | lark-cli 配置的 app 不是有权限的那个 |
| 新增权限后仍然 403 | tenant_access_token 缓存未过期，等 ~2 小时 |

### 添加协作者 API（跨应用授权）

```bash
# lark-cli 方式（需要有权限的 app 登录）
lark-cli drive permission.members create \
  --params '{"token":"{bitable_token}","type":"bitable","need_notification":false}' \
  --data '{"member_id":"{目标bot的open_id}","member_type":"openid","perm":"full_access","type":"user"}'
```

**⚠️ member_id 必须是 open_id（ou_ 开头），不能是 app_id（cli_ 开头）。** app_id 当 member_id 会报 1063001 Invalid parameter。

**获取 bot 的 open_id：**
```bash
curl -s -X GET "https://open.feishu.cn/open-apis/bot/v3/info/" \
  -H "Authorization: Bearer {tenant_access_token}"
# 返回 bot.open_id
```

**lark-cli 命令中多维表格用 `base` 不是 `bitable`：** `lark-cli base +base-get`，不是 `lark-cli bitable`。

## lark-cli Gotchas

- **`--json` not `--data`**: The flag is `--json`, passing a flat JSON object
- **`+field-update` 必须 `--yes`（2026-05-24）**: lark-cli 将 `+field-update` 归类为 `high-risk-write`，不加 `--yes` 报 `confirmation_required`。脚本中尤其危险（subprocess 无法交互确认，静默失败）。所有脚本和手动调用都必须加 `--yes`。
- **`+record-upsert` 不带 `--as user`**
- **No `{\"fields\":{...}}` wrapping**: Pass the record object directly, returns error 800010701 otherwise
- **`api DELETE` is broken**: Returns empty output with exit code 1. Delete fields via Feishu UI instead
- **`hermes mcp add` CLI bug with `-y` flag**: Misinterprets `-y` as its own flag. Workaround: edit `~/.hermes/config.yaml` directly
- **`--folder-token` works with permissions (2026-05-06 更新)**: 需要在飞书开放平台开通 `drive:drive` + `space:folder:create` 权限。开通后 `+base-copy --folder-token` 可正常工作，多维表格直接创建到指定文件夹。**未开通时返回 800004011 forbidden。**
- **Dashboard creation requires scope**: `base:dashboard:create` must be enabled in Feishu app permissions (returns HTTP 400 code 99991672 without it)
- **Table IDs are RANDOM on copy**: When copying a template, new table IDs differ. Always `+table-list` after copy

## lark-cli Token & Auth

- User identity: "卫" (feishu_id `ou_cbea6d5fcf1a240cdfd2e765dd97b00b`)
- Has refresh_token + offline_access scope — auto-refreshes as long as there's been ≥1 API call within 7 days
- Cron jobs will work (they count as activity). Only breaks after 7 consecutive days of zero activity
- lark-cli does NOT need to be added to groups — it's a backend terminal tool, members never see it

### ⚠️ User Token 过期导致 sync_to_sqlite.py 批量 91403（2026-05-29 踩坑）

**现象：** 本地跑 `sync_to_sqlite.py` 全量同步，14 位会员中只有 2 位成功（铮然、元宝），其余 12 位全部报 `91403 you don't have permission`，identity 为 `"user"`。

**根因：** lark-cli user token 过期（`lark-cli auth status` 显示 `"expiresAt"` 已过去，user status 为 `"needs_refresh"`）。sync 脚本对 user token 过期**不报明确错误**，而是直接用过期的 user 身份请求 → 91403。

**为什么只有 2 位成功：** 铮然和元宝的多维表格是 onboard 时模板复制的（Hermes bot 创建），bot 天然有权限，走 bot 身份成功。其余 12 位的表格是教练个人创建后分享给 bot 的，走 user 身份 → token 过期就 403。

**诊断命令：**
```bash
lark-cli auth status
# 看 "expiresAt" 日期 + user status
```

**修复（仅本地，不影响云端）：**
```bash
~/.nvm/versions/node/v20.20.0/bin/lark-cli auth login --recommend
```
刷新后重跑 `sync_to_sqlite.py` 即可。

**关键认知：** `sync_to_sqlite.py` 是纯只读操作（`+record-list`），不会写飞书、不影响云端生产环境。刷新 token 也只更新本机 `~/.lark-cli/` 下的凭证文件，与云端完全隔离。

**教练关注点：** 在执行任何本地同步操作前，教练会确认"是否影响云端/生产环境"。这是对的，但需要提前说清楚 sync 是只读的，打消顾虑。

## base-copy 重跑导致 800004011 forbidden（2026-05-23 踩坑）

**场景：** `onboard_member.py` 执行 `+base-copy` 成功（模板表格已复制），但后续 `+table-list` 因复制未完成报 `800004046 "is copying"`。Agent 重跑脚本，第二次 `+base-copy` 触发飞书频率限制/去重保护，返回 `800004011 forbidden`。

**根因：** 飞书对同一个模板的多次并发复制有限制。第一次复制已在进行中（或已完成），第二次请求被拒。

**正确处理：**
1. 脚本失败后**不要重跑**，检查失败步骤
2. 如果 `step: "table-list"` → base-copy 已成功，只需等 30-60 秒后手动 `+table-list`
3. 如果 `step: "base-copy"` → 可能是权限问题（800004011）或模板协作者问题，不要反复重试
4. 手动降级：创建 profile + group_map(PENDING) + cron jobs，稍后补 bitable

**⚠️ 脚本无"恢复模式"：** 当前 `onboard_member.py` 每次运行都会从头执行 `+base-copy`，不支持"跳过已完成的步骤"。重跑 = 重新复制 = 被拒绝。

## Bitable Field Operations

- **`+field-update` requires `--yes` for confirmation (2026-05-23 实测)**: Running `+field-update` without `--yes` returns exit code 10 with `confirmation_required` error. Always add `--yes` to auto-confirm.
- **`+field-list` does NOT support `--field-name` or `--format json` flags (2026-05-23 实测)**: Both flags return "unknown flag" errors. Call `+field-list` without extra flags and filter client-side with jq or python.
- **jq filter for `+field-list` output**: The raw JSON has a wrapper `{ok, identity, data: {fields: [...]}}`. Correct jq filter: `jq '.data.fields[] | select(.field_name == "训练主题")'` — NOT `jq '.[] | ...'` (which fails because top level is an object, not array).
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

## GLM-5-Turbo 推理过程泄露到群聊（2026-05-06 实测）

**现象：** 模型在处理群聊消息时，将内部推理过程（身份判断、逻辑分析、"让我先检查系统自愈"等）直接输出为正式回复，发送到群里。会员和教练能看到这些"自言自语"。

**根因：** GLM-5-Turbo 不使用 `<think` 标签或类似的推理隔离机制，推理过程混在输出正文中。Hermes gateway 无法区分"思考"和"正式回复"，原样发出。

**影响：** 暴露系统内部逻辑，用户体验差，可能泄露技术细节。

**缓解方案：** 
- 在 SOUL.md 中加硬性规则："回复内容只包含最终回复，不要输出推理过程"
- 换用支持推理隔离的模型（如 Claude 的 thinking 模式、DeepSeek-R1 的 `<think` 标签）
- 如果继续用 GLM-5-Turbo，在 skill 的回复规则中强调"直接回复，不要分析过程"

## Coach 双 ID 系统（2026-05-06 修复）

**现象：** 教练在会员群里发消息，机器人识别为"未知身份"，无法执行教练专属操作（改配置、取消提醒等）。

**根因：** `_config.coach_user_id` 配置的是飞书 open_id（`ou_` 开头），但 Hermes 消息中的发送者标识是另一个格式的 user_id（如 `f754274g`）。两个 ID 系统不一致导致身份匹配失败。

**修复：** `_config` 现在存两个 ID：
- `coach_user_id`: Hermes user_id（如 `f754274g`），用于身份识别
- `coach_openid`: 飞书 open_id（如 `ou_c76485c...`），用于 drive API 分享操作

`onboard_member.py` 分享多维表格时使用 `coach_openid`（优先）→ `coach_user_id`（降级）。

**教训：** 飞书有 user_id、open_id、union_id 三种 ID 格式，Hermes gateway 用的是其中一种。新环境部署时务必先确认 Hermes 识别出的教练 user_id 是什么格式，再写入 `_config.coach_user_id`。

## MCP Server 进程缺少 HERMES_HOME → lark-cli 用错身份（2026-05-17 修复）

**现象：** MCP Server 写入飞书多维表格时报 `need_user_authorization`，但直接在终端调 lark-cli 完全正常。

**根因：** lark-cli 通过 `HERMES_HOME` 环境变量自动检测 Hermes workspace，加载 `~/.lark-cli/hermes/config.json`（`defaultAs: "bot"`, `strictMode: "bot"`）。MCP Server 是 Hermes 的子进程，启动时只有 6 个环境变量（`HOME`, `PATH`, `SHELL`, `USER`, `LANG`, `LOGNAME`），**没有 `HERMES_HOME`**。lark-cli 找不到 workspace → fallback 到根目录 `~/.lark-cli/config.json`（`defaultAs: "user"`, 有已登录 user token）→ 以 user 身份调 API → 报授权错误。

**诊断方法：**
```bash
# 查看 MCP Server 进程的环境变量
cat /proc/$(pgrep -f "mcp-server/server.py")/environ | tr '\0' '\n' | grep HERMES
# 如果输出为空，就是这个问题

# 验证：加 HERMES_HOME 后是否能正确写入
env -i HOME=/root HERMES_HOME=/root/.hermes PATH="..." lark-cli config show
# 期望看到 workspace: "hermes", users: "(no logged-in users)"
```

**修复：** 在 `~/.hermes/config.yaml` 的 MCP Server 配置中加 `env` 字段：
```yaml
fitness-data:
  command: python3
  args:
    - /root/.hermes/mcp-server/server.py
  env:
    HERMES_HOME: /root/.hermes
```
修改后需**重启 Hermes Agent**（MCP Server 进程重新创建才会加载新环境变量）。重启后 pending 的数据会自动同步到飞书。

**排查时间线（供参考）：** env -i 复现 → lark-cli config show 对比（workspace "local" vs "hermes"）→ `lark-cli config bind --source hermes` 帮助文档提到 "auto-detected from env signals" → diff hermes env vs mcp env → 发现 `HERMES_HOME` 是关键差异 → 验证。

## lark-cli strict_mode: 云端使用 bot 身份（已解决 2026-05-04）

**现象：** strict_mode 为 `bot-only` 时，`--as user` 操作被拦截。

**已解决：** bot 身份完全可以执行 bitable 操作（复制、读写表格），前提是飞书开放平台给 bot 应用开通了对应权限（`base:app:copy`、`base:table:read`、`base:table:write`）。

**`onboard_member.py` 已更新：** 脚本不再使用 `--as user`，改为纯 bot 身份操作。`--folder-token` 用于将多维表格直接创建到教练云盘文件夹。

**⚠️ `--folder-token` 陷阱（2026-05-04 → 2026-05-06 更新）：** 需要 `drive:drive` + `space:folder:create` 权限。未开通时返回 800004011 forbidden，开通后正常。**开通权限后实测可用（2026-05-06）。**

## 已有会员在新群回答问卷（多 chat_id 场景）

**现象（2026-05-04）：** 会员毛毛在新的飞书群中回答了入群问卷，但她的 member_id（maomao）已存在于 `~/.hermes/members/maomao/profile.json`，且另一个群的 chat_id 已在 group_map.json 中。

**正确处理流程：**
1. 解析问卷后，**先检查 `~/.hermes/members/` 下是否已有该会员的目录**
2. 如果已存在 → **不要调用 `onboard_member.py`**（会报错或创建重复档案）
3. 直接在 group_map.json 中添加新 chat_id 条目，`member_id` 指向已有会员，bitable_token/table_ids 从已有条目复制（或标 PENDING）
4. 问卷中的信息（style、goal 等）**以原有 profile 为准**，不覆盖（除非教练明确要求修改）
5. 不需要创建新的 cron job（已有群已在运行）

**⚠️ 关键信号：** 如果 `ls ~/.hermes/members/` 下已存在同名 member_id 目录，直接走映射流程，不要跑脚本。

## Bitable Sharing & URL 获取（2026-05-06 实测）

会员要求查看多维表格链接时的完整流程：

### 1. 获取 tenant_access_token
```bash
curl -s -X POST "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal" \
  -H "Content-Type: application/json" \
  -d '{"app_id":"{FEISHU_APP_ID}","app_secret":"{FEISHU_APP_SECRET}"}'
```
返回 `tenant_access_token`。

### 2. 分享给会员（Drive API）
```bash
curl -s -X POST "https://open.feishu.cn/open-apis/drive/v1/permissions/{bitable_token}/members?type=bitable" \
  -H "Authorization: Bearer {token}" \
  -H "Content-Type: application/json" \
  -d '{"member_type":"unionid","member_id":"{union_id}","perm":"full_access"}'
```
- `member_type`: 优先用 `"unionid"`（从 Hermes session key 获取 `on_xxx` 格式），也可用 `"userid"`
- 返回 `code: 0` 即分享成功

### 3. 获取多维表格 URL
用 lark-cli 最简单：
```bash
/usr/local/bin/lark-cli base +base-get --base-token "{bitable_token}"
```
返回中包含 `url` 字段，格式如 `https://pcn66xx6g0i0.feishu.cn/base/{token}`。

### ⚠️ 陷阱
- **share_link API 返回 404**：`POST .../create_share_link` 和 `PUT .../share_link` 两个端点在当前飞书版本都返回 404（可能是 API 版本问题），改用直接 `POST .../members` 分享给具体用户即可
- **union_id 获取**：从 Hermes 会话上下文的 `HERMES_SESSION_KEY` 环境变量中提取（格式 `...:on_xxxxxxx:...`）。`member_feishu_id`（group_map 中的 `f754274g` / `3d87d5a3` 格式）可能是 `userid` 而非 `unionid`，两种类型都试试
- **分享后会员说打不开**：可能是因为分享用的是 userid/union_id 格式不对，或者链接需要直接复制在飞书内打开（不是外部浏览器）

## 多维表格字段名因模板副本而异（2026-05-06 实测）

**现象：** 写入训练课次时使用 `"主题"` 和 `"日期"` 字段名，返回 `800030201 not_found` 错误。

**根因：** 从模板复制的多维表格，字段名由模板定义决定。不同版本的模板或不同时间复制的表格，字段名可能不同：
- 模板 A 可能用 `主题` / `日期`
- 模板 B（当前使用）用 `训练主题` / `训练日期` / `会员姓名`

**正确做法：** 新会员首次写入前，先 `+field-list` 确认字段名，不要假设。错误信息会列出前 5 个可用字段名，据此修正即可。

**`record-upsert` 返回结构注意：** record_id 在 `data.record.record_id_list[0]`（数组），不是 `data.record.record_id`（字符串）。示例见 `references/lark-cli-response-formats.md`。

## Feishu 云空间「移动文件」API 不存在（2026-05-06 实测）

**现象：** 想把已有的多维表格移动到教练云盘的「会员档案」文件夹，尝试了 `PATCH /drive/v1/files/{token}`、`POST .../transfer`、`POST .../move`、`POST .../transfer_to_folder`、`POST .../create_subscription`、`POST .../save_to_drive` 等多种端点，全部返回 404 或参数错误。

**结论：** 飞书开放平台**没有提供「移动已有文件到文件夹」的 API**。`PATCH /drive/v1/files/{token}` 只支持修改标题（`new_title`），不支持 `folder_token`。

**解决：** 必须在创建时就指定文件夹。`lark-cli base +base-copy --folder-token {folder_token}` 可在创建时直接放入目标文件夹（需 `drive:drive` + `space:folder:create` 权限）。已有文件只能手动拖拽。

## 多维表格 URL 格式

**格式：** `https://{feishu_domain}/base/{bitable_token}`
**当前域名：** `pcn66xx6g0i0.feishu.cn`
**域名来源：** `_config.feishu_domain`（group_map.json），`+base-copy` 返回的 `url` 字段也包含完整 URL。
**用途：** 新会员建档确认消息中必须包含此链接。

## 训练记录写入时的特殊格式处理（2026-05-06 实测）

**现象：** 教练发送的训练计划包含多种"非标准"格式，直接解析写入会出错或数据不准确。

### 1. 时间类动作（平板撑、悬垂举腿等）

**问题：** 动作以时间计（如"1分钟"、"30秒"），但多维表格的「次数」字段是数字类型，无法填"1分钟"。

**正确做法：** 向教练确认记录方式（如"次数填1、备注写每组1分钟"），不要自行决定。

### 2. 重量区间（递增组/递减组）

**问题：** 教练给出重量范围（如"6.81-13公斤"、"20-40公斤"），但「重量」字段只能填一个数字。

**正确做法：** 向教练确认填哪个值（最大值、最小值、平均值），不要自行决定。

### 3. 动作名称为 select 类型字段

**问题：** 多维表格的「动作名称」字段可能是 `select`（单选下拉）类型，不是自由文本。只有预设选项才能直接写入，写不存在的选项会报错。

**正确做法（2026-05-07 更新）：** 按 SKILL.md 第三节 3.0 的自动补充流程执行：
1. 写入前先 `+field-list` 确认字段类型和已有选项
2. 如果是 select 类型且值不在选项里 → 自动读取已有选项 → 合并新选项 → 用 `+field-update` 覆盖式写回 → 再正常写入记录
3. 无需再问教练或让教练手动添加，每个新选项只会触发一次合并
4. 覆盖式操作必须传入完整选项列表（已有 + 新增），否则已有选项会丢失

**新增 select 选项命令：**
```bash
/usr/local/bin/lark-cli base +field-update \
  --base-token "{bitable_token}" \
  --table-id "{table_id}" \
  --field-id "{field_id}" \
  --json '{
    "name": "动作名称",
    "type": "select",
    "options": [
      {"name": "已有选项1"},
      {"name": "已有选项2"},
      {"name": "新选项A"},
      {"name": "新选项B"}
    ]
  }'
```

**踩坑记录：**
- ❌ `--json '{"property": {"options": [...]}}'` → 报错 `Unrecognized key(s): 'property'`
- ❌ `--json '{"options": [...]}'` → 报错 `Invalid discriminator value`（缺少 `type`）
- ❌ `--json '{"type":"select","options":[...]}'` → 报错 `Provide a value of type string`（缺少 `name`）
- ✅ `--json '{"name": "字段名", "type": "select", "options": [...]}'` → 正确，`name`、`type`、`options` 是顶层字段，缺一不可
- `type` 必须传，否则报 `Invalid discriminator value`
- `name` 必须传，否则报 `Provide a value of type string`

**⚠️ Select hue 值限制（2026-05-08 实测）：**
- options 中的 `hue` 只允许 11 个值：`Red`, `Orange`, `Yellow`, `Lime`, `Green`, `Turquoise`, `Wathet`, `Blue`, `Carmine`, `Purple`, `Gray`
- 以下值会报错（`Use one of these allowed values`）：`Indigo`, `Cyan`, `Peach`, `Violet`, `Pink`, `Brown` 等
- `lightness` 只允许 `Lighter`（其他值如 `Default` 未测试，建议统一用 `Lighter`）
- 新增选项时，从已有选项中复制一个 hue/lightness 最安全，避免踩坑

**关键信号：** `+field-list` 返回中 `type: "select"` 且有 `options` 数组，就是单选下拉。

## 记录修正：删除 + 重建（2026-05-08 实测）

**场景：** 会员指出记录内容有误（如食物数量写错了），要求修正。

**问题：** `+record-upsert` 对饮食记录表等无唯一键的表，不会自动匹配已有记录做更新，而是创建新条目（重复记录）。

**正确流程：**
1. `+record-delete --record-id "{id}" --yes` 删除错误记录（`--yes` 必须，否则交互确认会卡住）
2. `+record-upsert` 创建正确的新记录

**注意事项：**
- 如果不确定 record_id，先 `+record-list` 查询找到目标记录
- 删除操作不可逆，操作前确认 record_id 正确
- 饮食记录表、体重记录表等通常没有唯一键，必须手动删+建
- 训练课次表/动作记录表如果有唯一键配置，`+record-upsert` 可自动匹配更新

## Member Offboard 完整清单（删除会员）

删除一个会员时需要清理的所有位置：

| 步骤 | 操作 | 命令/路径 |
|------|------|-----------|
| 1 | 列出该会员所有 cron jobs | 读取 profile.json 的 `cron_jobs` 或 `cronjob action=list` 按 name 过滤 |
| 2 | 逐个删除 cron jobs | `cronjob action=remove job_id=...` |
| 3 | 删除会员目录 | `rm -rf ~/.hermes/members/{member_id}/` |
| 4 | 删除 group_map.json 条目 | patch 移除对应 chat_id 的整个对象 |
| 5 | 删除飞书多维表格 | 见下方「多维表格删除」章节 |

**顺序重要：** 先删 cron jobs（需要 job_id），再删 profile（job_id 在里面）。

### 多维表格删除

**2026-05-22 迁移后：lark-cli 使用 Hermes 凭证，新建的多维表格归 Hermes 所有，可通过 API 删除。**

| 表格创建时间 | 所有者 | API 删除 |
|-------------|--------|---------|
| 2026-05-22 之后（lark-cli 用 Hermes 凭证） | Hermes（cli_a9789ef1a0b85cd5） | ✅ 可删除 |
| 2026-05-22 之前（lark-cli 用旧凭证 cli_a961e26f03b85cb5） | 旧 lark-cli 应用 | ❌ 只能手动删除 |

**API 删除方式（Hermes 凭证）：**
```python
# DELETE /drive/v1/files/{token}?type=bitable
# 需要 space:document:delete 权限
```

**手动删除路径（旧表格）：**
1. `lark-cli base +base-get --base-token {token}` 获取 URL
2. 教练在飞书中打开该 URL → 右上角「…」→「删除」
3. 或在云盘「会员档案」文件夹中找到该表格右键删除

**前提权限：** Hermes 应用需要 `space:document:delete` scope。开通链接：
`https://open.feishu.cn/app/cli_a9789ef1a0b85cd5/auth?q=space:document:delete&op_from=openapi&token_type=tenant`

## 私聊（DM）场景：SOUL.md 当前规则空白（2026-05-09 审计）

**现状：** 教练发现可以给会员开通私聊权限（Hermes bot 与会员直接 1v1 对话）。审计 SOUL.md 后发现私聊场景存在以下规则空白。

**已覆盖（正确的）：**
- 配置安全（第33行）："群聊 & 私聊均适用" — 会员私聊也不能改配置 ✅
- Skill 加载限制（第56行）："私聊（DM）不受此限制" — 私聊可加载任何 skill ✅
- 群聊入口判断（第62行）：明确排除私聊 ✅
- 系统自愈（第113行）：每次对话都做 ✅

**未覆盖（需补充）：**

| 缺失项 | 说明 |
|--------|------|
| **身份识别** | 第28-31行写的是"与该群 `member_feishu_id` 匹配"，纯群聊逻辑。私聊没有 chat_id 映射，怎么知道对面是谁？遍历 group_map 所有条目的 member_feishu_id？还是需要独立的 member→user_id 映射？ |
| **私聊入口流程** | 会员第一次私聊时做什么？发问卷？还是只对已有会员开放（教练手动开通）？ |
| **私聊能力范围** | 会员在私聊中能否查训练数据、记体重、看报告？还是私聊只做日常互动，数据操作回群里？ |
| **Profile 定位链路** | 群聊：chat_id → group_map → member_id → profile.json。私聊没有 chat_id，如何定位？ |

**设计要点（待实现时参考）：**
- 私聊身份识别最简方案：遍历 group_map 所有条目的 `member_feishu_id` 与 Hermes user_id 匹配
- 建议只对已有会员开放私聊（教练已建档案的），新会员走群聊问卷流程
- 私聊中会员可做的事应与群聊一致（查数据、记体重、看报告等），只是少了群聊特有的训练计划写入（教练不在私聊里发计划）

## Related Skills

- `fitness-coaching-assistant` (productivity/): earlier draft with full architecture docs, templates, and Feishu setup references. Superseded by `fitness-coach` for operational workflow, but still useful for onboarding/setup reference material.

## 群聊中会员 @机器人消息未到达 Hermes

**症状：** 会员在群聊中 @机器人发了消息，但 Hermes 没有触发回复，gateway 日志中也无对应记录。

**排查步骤（按顺序）：**

**1. 检查 Hermes 用户白名单（最常见）**
gateway 日志出现 `Unauthorized user: ou_xxxxx` 说明该会员的 user_id 不在允许列表中。健身教练场景有 30-60 个群、每个群 1-2 个会员，不可能逐个加白名单，**必须在 `.env` 中开启全员权限：**

```bash
echo 'FEISHU_ALLOW_ALL_USERS=true' >> ~/.hermes/.env
hermes gateway restart
```

⚠️ 这是最常见的拦截原因。新环境部署后第一个要确认的就是这个。

**2. 检查飞书事件订阅**
如果白名单已开启但仍收不到消息：
- 飞书开放平台 → 应用后台 → 事件与回调 → 事件配置
- `im.message.receive_v1` 事件是否已订阅
- 是否勾选了"接收群聊中@机器人的消息"

**3. 检查 gateway 日志**
```bash
journalctl -u hermes-gateway --since "1 hour ago"
```
- 如果完全没有 HTTP 请求到达 → 飞书回调/事件订阅问题
- 如果有请求到达但返回 `Unauthorized user` → 白名单问题（第1步）

**4. 如果私聊能收到但群聊收不到**
大概率是飞书事件订阅配置问题（第2步），群聊消息需要单独勾选。
