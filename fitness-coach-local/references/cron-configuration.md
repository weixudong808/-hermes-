## 十、Cron Job 配置（自动周报/月报/饮食提醒/体重提醒）

### 10.0 Cron Job 触发机制（核心原理）

**⚠️ cron job 不依赖群消息触发，不需要被 @机器人。**

Hermes 的 cron job 是独立的定时调度器，到点后起新 session 执行预设 prompt，执行完毕后自动发送到指定目标。

### 10.1 Cron Job 架构：全局 vs 每会员

**架构决策（2026-05-04）：** 不同类型服务采用不同粒度。

| 服务类型 | 策略 | 数量（60会员估算） | 理由 |
|---------|------|-------------------|------|
| **饮食提醒** | 每会员独立 cron | 90~180 个 | 每人吃饭时间不同，需要精确到分钟 |
| **体重提醒** | 每会员独立 cron | 0~60 个 | 每日/每周/不提醒，因人而异 |
| **周报** | 全局 1 个 | 1 个 | 统一时间（周日22:00），统一逻辑 |
| **月报** | 全局 1 个 | 1 个 | 统一时间（每月1日），统一逻辑 |

**为什么饮食/体重用每会员独立而非全局轮询：**
- 全局轮询：60人吃饭时间分布散，固定几个触发时间点无法精确覆盖（如有人7:30有人8:30）
- 每会员独立：时间精确，创建/删除全自动化（脚本完成，教练不碰）

**为什么周报/月报用全局：**
- 统一触发时间，脚本遍历 report_enabled=true 的会员
- 需要拉多维表格数据做统计，逻辑统一

**⚠️ 数量上限：** Hermes 源码（`cron/jobs.py`）中无 job 数量限制，jobs 存储在 `~/.hermes/cron/jobs.json`（纯数组），240+ 个 job 无压力。

### 10.1.1 Cron 提醒与消息处理是独立流程

**⚠️ 这是最容易误解的地方。** Cron job 只负责"发提醒消息"，不负责"记录数据"。

```
时间线示例：
12:00  cron 触发 → Hermes 发消息："张三，午餐时间到啦~ 📸"  （结束，完事）
12:05  张三看到提醒，拍照发群里 → 群消息触发 → fitness-coach skill → 写入饮食记录表
12:30  李四没回照片 → 不管了，提醒已发出
```

两条链路完全独立：
- **链路 1（cron）：** 定时触发 → 发提醒 → 结束
- **链路 2（群消息）：** 会员发消息 → 正常消息分类处理 → 可能触发数据写入

会员不回复提醒也不影响任何东西，回复了就走正常的群消息处理流程。

### 10.1.2 两步中继：脚本建文件，Agent 建 cron

**`onboard_member.py` 是 Python 脚本，运行在终端里，无法调用 Hermes 的 `cronjob` 工具。** 所以 cron 创建必须由 Agent 完成，形成两步接力：

```
第一步：脚本（terminal 执行）
  onboard_member.py → 创建 profile.json + 复制表格 + 更新 group_map.json
  返回 JSON：{ member_name, chat_id, meals, reminder_freq, weight_reminder, style ... }

第二步：Agent（当前对话里执行）
  读取脚本返回结果
  → 根据 meals/reminder_freq/weight_reminder 逐个创建 cron job
  → 拿到 job_id → 写回 profile.json 的 cron_jobs 字段
```

**创建 cron job 所需的全部信息在脚本返回值中即可获得，不需要额外读取 group_map.json。** chat_id 在建群上下文中已知（从 Source 行获取，作为参数传入脚本）。

### 10.2 cron_jobs 字段：ID 归属追踪

Cron job 由 Hermes 调度器管理，不存在文件系统。**每个会员的 cron job ID 记录在 profile.json 的 `cron_jobs` 字段中：**

```json
{
  "cron_jobs": {
    "meal_breakfast": "abc123",
    "meal_lunch": "def456",
    "meal_dinner": "ghi789",
    "weight": "jkl012"
  }
}
```

- 没有 cron 的字段值为 `null` 或不存在
- 教练改时间 → 读取旧 job_id → 删除旧 job → 创建新 job → 更新 profile
- 会员退群 → 遍历 cron_jobs 所有值 → 逐个删除

### 10.3 饮食提醒 Cron Job 规格

**prompt 模板（自包含，不需要脚本，不需要加载 skill）：**
```
你是健身教练小卫的助手。提醒会员"{member_name}"该吃{meal_type}了。
风格：{style}（energetic=活泼鼓励多用表情, professional=简洁专业, gentle=温和关怀, strict=直接）。
直接输出提醒消息内容即可，系统会自动投递。不要加载任何 skill。
```

**⚠️ Prompt 编写红线（2026-05-11 事故复盘）：**
- **绝不能提到 `send_message`**：cron 的投递是系统自动的，prompt 里写"用 send_message 发送"会让模型纠结该不该调工具，暴露思考过程到群里
- **不需要指定目标群**：deliver 已在 cron job 配置中指定（`feishu:{chat_id}`），prompt 不需要再说"发送到群"
- **只让模型输出提醒内容本身**：一句"直接输出提醒消息内容即可，系统会自动投递"足够

**创建规则（onboard_member.py 扩展）：**
1. 读取 `reminder_freq` 确定提醒哪几顿
2. 对每顿：`meals.{type}` ≠ "无" 且 `reminder_freq` 包含该顿 → 创建 cron
3. schedule 格式：每天 `HH:MM`（如 `07:30`），需要 croniter
4. deliver：`feishu:{chat_id}`
5. enabled_toolsets：`["terminal"]`（最小化，只需 send_message）
6. 将返回的 job_id 写入 profile.json 的 `cron_jobs.meal_{type}`

**提醒内容：** 简单一句话，按风格适配：
- energetic: "🌅 张三，早餐时间到啦~ 记得拍张照片发群里哦 📸"
- professional: "张三，早餐时间，记得饮食打卡。"
- gentle: "张三，早餐时间到啦~ 慢慢享受 🍽️"
- strict: "张三，该吃早餐了，拍个照发群里。"

### 10.4 体重提醒 Cron Job 规格

| weight_reminder | 触发时间 | prompt 内容 |
|----------------|---------|------------|
| `daily` | 每天 08:00 | "记得称一下体重哦~" |
| `weekly` | 每周一 09:00（默认） | "新的一周开始啦，记得称一下体重~" |
| `none` | 不创建 | — |

**⚠️ 自定义星期：** 问卷中会员可指定任意星期几（如"每周二早上8:20"），此时 `weight_reminder` 仍记为 `weekly`，但 cron schedule 按会员指定的星期和时间创建。静姐案例：schedule `20 8 * * 2`（每周二 08:20）。profile.json 的 `notes` 字段记录原始请求。

**prompt 同样自包含，不需要脚本和 skill。**

### 10.5 周报/月报 Cron Job

**架构决策（2026-05-04）：改为每会员独立 cron，纯 prompt 模式。**

- 大模型在 cron session 里直接用 lark-cli 拉多维表格数据，不依赖预处理脚本
- deliver 直接写 `feishu:{chat_id}`，prompt 自包含（含 bitable_token、table_ids、style 等）
- 与饮食/体重提醒同样的管理模式（入群时创建，退群时删除）

#### 10.5.1 触发时间

| 类型 | 触发时间 | 说明 |
|------|---------|------|
| 周报 | 每周日 22:00 | `0 22 * * 0` |
| 月报 | 每月1日 20:00 | `0 20 1 * *` |

#### 10.5.2 Cron Job 规格（待实施）

**prompt 需自包含的信息：**
- member_name、style
- bitable_token、table_ids（训练课次表、动作记录表、饮食记录表、体重记录表）
- 报告类型（周报/月报）和时间范围

**enabled_toolsets：** `["terminal", "file"]`（需 lark-cli 拉数据 + file 读写 profile）

**旧方案已废弃：** 之前的全局周报 cron（`b211038fb7af`）依赖 `weekly-report-collect.py` 脚本预处理，已于 2026-05-04 删除。脚本保留在 `scripts/` 目录仅供参考。

### 10.6 Cron Job 生命周期管理

#### 入群（onboard_member.py + Agent 两步接力）

```
第一步：onboard_member.py（脚本，terminal 执行）
  → 创建 profile.json（含 cron_jobs: {}，初始全为 null）
  → 复制多维表格
  → 更新 group_map.json
  → 返回：{ member_name, chat_id, meals, reminder_freq, weight_reminder, style }

第二步：Agent（当前对话里，用 cronjob 工具）
  → 根据 reminder_freq 判断该创建哪些 cron
  → 逐个创建 cron job
  → 拿到 job_id 写入 profile.json 的 cron_jobs 字段
```

#### 10.6.1 教练改提醒时间（Agent 直接操作，不需要额外脚本）

**触发：** 教练在群里说"把张三的午餐提醒改成11:30"

```
1. 读取当前群的 member_id → 读取 profile.json
2. 从 cron_jobs.meal_lunch 取旧 job_id
3. cronjob(action="remove", job_id=旧ID)
4. 更新 profile.json 的 meals.lunch = "11:30"
5. cronjob(action="create", schedule="0 11 * * *", deliver="feishu:{chat_id}", prompt="...")
6. 新 job_id 写回 profile.json 的 cron_jobs.meal_lunch
7. 回复教练："已将张三的午餐提醒时间改为 11:30"
```

**其他改配置指令：**

| 教练指令 | Agent 操作 |
|---------|-----------|
| "给张三关闭早餐提醒" | 删 cron_jobs.meal_breakfast 对应 job + profile 设 null |
| "给张三开启早餐提醒（7:30）" | 创建 cron + 写 job_id + meals.breakfast = "07:30" |
| "给张三关闭体重提醒" | 删 cron_jobs.weight + weight_reminder = "none" |
| "给张三开启每日体重提醒" | 创建每天 08:00 cron + 写 job_id + weight_reminder = "daily" |
| "给张三开启每周体重提醒" | 创建每周一 09:00 cron + 写 job_id + weight_reminder = "weekly" |
| "给张三关闭午餐和晚餐提醒" | 逐个删对应 cron + 设 null + 更新 reminder_freq |

#### 10.6.2 会员退群（Agent 直接操作）

**触发：** 教练说"张三退群了"

```
1. 读取当前群的 member_id → 读取 profile.json
2. 遍历 cron_jobs 所有非 null 值
3. 逐个 cronjob(action="remove", job_id=...)
4. 删除 profile.json + members/{member_id}/ 目录
5. 从 group_map.json 移除该 chat_id 条目
6. 回复教练："已清理张三的所有数据（profile、表格映射、{N}个定时提醒）"
```

**⚠️ 顺序很重要：先删 cron job，再删 profile.json（因为需要从 profile.json 读 cron_jobs）。**

### 10.7 Cron Job 丢失排查（环境迁移/重启后）

**症状：** 会员反馈没有收到饮食/体重提醒，但 profile.json 中 `cron_jobs` 字段有 job_id。

**根因：** 环境迁移、Hermes 重启或 scheduler 数据重置后，cron job 可能从调度器中丢失，但 profile.json 中仍保留旧 ID（幽灵 ID），导致提醒静默失效。

**排查步骤：**
```
1. cronjob(action="list") → 查看当前实际存在的 job
2. 对比 profile.json 中 cron_jobs 的所有 ID
3. 缺失的 job → 重新创建（schedule/deliver/prompt 同原规格）
4. 用新 job_id 更新 profile.json 的 cron_jobs 字段
```

**批量排查：** 如果怀疑多个会员的 cron 都丢失，遍历 `~/.hermes/members/*/profile.json`，逐个比对 cron_jobs 中的 ID 是否在 `cronjob list` 结果中存在。

**预防：** 环境迁移后，将 cron job 健康检查纳入部署验证清单（类似 lark-cli config bind）。

### 10.8 Cron Job Prompt 编写规范（2026-05-11 事故复盘）

**核心原则：prompt 只负责定义提醒内容，不负责投递逻辑。**

1. **不提 `send_message`**：Hermes cron 自动投递最终回复到 `deliver` 指定的目标。prompt 里写"用 send_message 发送"会让模型纠结，部分模型会把思考过程暴露到群里
2. **不重复指定投递目标**：`deliver: feishu:{chat_id}` 已在 job 配置中设定，prompt 不需要再说"发送到群 oc_xxx"
3. **自包含但最小化**：风格、会员名、提醒内容已足够，不传多余的投递指令
4. **结尾明确说**："直接输出提醒消息内容即可，系统会自动投递"

**反面示例（导致思考过程暴露）：**
```
请发送提醒消息到群。用 send_message 发送到 feishu:{chat_id}。
```

**正面示例：**
```
直接输出提醒消息内容即可，系统会自动投递。不要加载任何 skill。
```

### 10.9 Cron Job 外壳包装（Response Wrapping）

Hermes 默认会在 cron 输出外包裹 header + footer（`cron.wrap_response: true`）：

```
Cronjob Response: 双双-体重提醒
(job_id: e9ed0199c08d)
-------------

<模型输出>

To stop or manage this job, send me a new message (e.g. "stop reminder 双双-体重提醒").
```

**与模型无关**，换任何模型都会带这两段。当前保留默认包装（会员能看到这是定时提醒）。

如需去除，在 `~/.hermes/config.yaml` 中设置：
```yaml
cron:
  wrap_response: false
```

### 10.10 Cron Job 创建注意事项

1. **script 路径必须相对于 `~/.hermes/scripts/`**，不能传绝对路径或 `~/` 开头
2. **cron 表达式需要 croniter 包**，装在 Hermes 的 venv 里，不是系统 Python
3. **repeat: 0** 表示永久循环
4. **enabled_toolsets** 限制为 `["terminal", "file", "session_search"]`（周报/月报）；饮食/体重提醒只需 `["terminal"]`
5. 全局 job 的 deliver 设为 `feishu`，脚本输出 chat_id 让 prompt 决定发到哪个群
6. 每会员 job 的 deliver 设为 `feishu:{chat_id}`，prompt 不需要自己判断目标
7. **原地更新安全**：用 `cronjob(action='update')` 改 prompt 不影响 schedule/deliver，不会中断提醒

### 10.11 GitHub 备份范围（health_check.py --github-sync）

**⚠️ `health_check.py --github-sync` 每天凌晨自动备份到 GitHub，但备份范围有限：**

| 内容 | 是否备份 | 说明 |
|------|---------|------|
| `members/`（所有 profile.json） | ✅ | 会员档案 |
| `group_map.json` | ✅ | 群映射 |
| `memory_store.db` | ✅ | 全息记忆（sqlite3 .backup） |
| `skills/fitness-coach/`（SKILL.md、references/、scripts/） | ❌ **未备份** | skills 目录不在 sync_to_github() 的复制列表中 |
| MCP SQLite（fitness.db） | ❌ **未备份** | 本地查询数据库 |
| `config.yaml` | ❌ **未备份** | Hermes 配置 |
| `docs/`（fix plan 等） | ❌ **未备份** | 文档 |

**影响：** 服务器全量重置后，skills 目录的改动（如 SKILL.md 精简）需要手动恢复。备份仓库 `/tmp/fitness-coach-hermes` 的 skills 目录可能是旧版本。

**如需扩展备份范围：** 修改 `health_check.py` 的 `sync_to_github()` 函数，在 copy 步骤中加入 `cp -r ~/.hermes/skills/ /tmp/fitness-coach-hermes/skills/`。

