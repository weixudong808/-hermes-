# Per-Member Memory 设计方案

> 创建日期：2026-05-13 | 更新日期：2026-05-15
> 状态：**已实施**（2026-05-15）
> 方案变更：~~独立 MEMORY.md~~ → 扩展 profile.json 的 memory 字段（教练决策）

## 方案选型记录

| 方案 | 可靠性 | 改动成本 | 结论 |
|------|--------|---------|------|
| A. 全局 memory 工具 | ~95% | 低 | ❌ 全局共享，无法隔离会员 |
| B. SKILL.md 规则驱动读文件 | ~95% | 低 | ✅ 性价比最高 |
| C. 代码级系统提示注入 | 100% | 高（改 Hermes 源码） | ❌ 维护成本高，等官方 #11430 |
| ~~独立 MEMORY.md（v1方案）~~ | ~95% | 低 | ❌ 改为 profile.json 方案 |
| ~~JSON Schema 验证~~ | — | 低 | ❌ 不需要（教练确认：规则写好就够了，Schema 是锦上添花不是必需品。写入逻辑负责限制条数和清理，Schema 只能报错不能删） |

### 为什么选 profile.json 而不是独立 MEMORY.md

- profile.json 已在 SKILL.md 前置步骤中每次读取，**不需要加新步骤**
- 信息隔离靠文件结构天然保证（每个会员一个 profile），不会串会员
- JSON 结构化存储，方便脚本操作
- 目前 profile.json 平均 630 bytes，加 memory 字段后预估 1.5~2 KB，对 token 消耗几乎无影响

### Hermes 官方进展（截至 2026-05-14）

- 当前版本 v0.12.0，最新 v0.13.0（差 139 commits）
- Issue #11430（per-user memory isolation in group chats）仍然 open，无官方方案
- v0.13.0 的 `X-Hermes-Session-Key` 仅适用于 API server 场景，不适用于飞书群聊
- 路线 C（代码级注入）需改 `prompt_builder.py`，每次 Hermes 升级需重新合并

## 最终方案：扩展 profile.json memory 字段

### memory 字段结构

```json
{
  "memory": {
    "habits": ["不爱吃西兰花", "喜欢五月天"],
    "injuries": ["左膝旧伤，避免大重量深蹲"],
    "preferences": ["喜欢被夸奖", "不喜欢太早训练"],
    "notes": ["最近在准备考试，训练频率可能下降"]
  }
}
```

### 容量限制

| 限制 | 值 | 理由 |
|------|-----|------|
| memory 字段上限 | **1 KB**（~20条） | 超过20条模型信息过载，旧条目应清理 |
| profile.json 总上限 | **2 KB** | 约 500~800 token，相对 SKILL.md 24KB 微不足道 |

### 更新方式

**SKILL.md 末尾规则驱动（不需要脚本，不需要 MCP）**

记忆更新属于理解性任务（需语义判断"这句话值不值得记"），只能靠模型。MCP/脚本无法解决核心问题（判断要不要记）。

### 写入规则（否定式优先）

**✅ 确认是事实性信息 → 更新**
**❌ 不确定 → 不更新**
**❌ 情绪化表达（"好累""不想练"）→ 不更新（走日常互动）**
**❌ 会员随口一提但未确认的 → 不更新**

**宁可不记，也不错记。重要的事情会员会反复提起，漏记一次不影响。**

### SKILL.md 中需添加的内容

在优先级3（日常互动）之后，消息处理流程末尾加一步：

```markdown
## 记忆更新（消息处理末尾必做）

处理完消息后，检查本条消息是否包含值得记住的信息：
- 会员主动分享的习惯/偏好
- 身体状态变化（如疼痛、伤病）
- 影响训练的生活事件

更新方式：用 patch 工具更新 profile.json 的 memory 字段对应子数组。
memory 字段上限 20 条（~1KB）。超过时，删除最旧且不再相关的条目。

写入原则：
- 确认是事实性信息 → 更新
- 不确定 → 不更新
- 情绪化表达（"好累""不想练"）→ 不更新（走日常互动）
- 会员随口一提但未确认的 → 不更新
- 宁可不记，也不错记
```

### 不写入的场景

| 场景 | 原因 |
|------|------|
| 日常训练数据 | 已在多维表格 |
| 体重数字 | 已有 record_weight.py |
| 单次对话上下文 | 临时信息，几天后无用 |
| 教练临时安排（"明天休息"） | 过期信息 |
| 情绪表达 | 非事实性信息 |

## Hermes Turn 概念（关键理解）

**Turn = 一条用户消息触发的完整处理周期。** 模型可能在一个 turn 内调用多个工具，但只要模型停止生成 token 且没有挂起的 tool call，该 turn 结束。

- 每条用户消息 = 一个独立 turn，不会合并
- 模型**无法预知**用户下一秒是否再发消息，也不需要预知
- 记忆更新是**每个 turn 独立判断**：这条消息有值得记的 → 写；没有 → 不写
- 后续 turn 可以追加/替换之前写入的条目，patch 是幂等式的

## 具体实施步骤

### Step 1: 给所有 profile.json 加 memory 字段

在 profile.json 末尾（cron_jobs 之后）添加：

```json
{
  "memory": {
    "habits": [],
    "injuries": [],
    "preferences": [],
    "notes": []
  }
}
```

模板文件 `templates/profile.json` 需同步更新。

### Step 2: 在 SKILL.md 消息处理流程末尾加规则

在优先级3（日常互动）之后，添加"记忆更新"检查步骤（规则内容见上方"SKILL.md 中需添加的内容"）。

### Step 3: 模型执行流程（每个 turn）

```
1. 会员消息说了什么？
2. 有没有事实性信息（习惯/伤病/偏好/生活事件）？
   ├─ 没有 → 回复用户，结束
   └─ 有 → 继续
3. 确定归到哪个子数组（habits/injuries/preferences/notes）
4. 该子数组里有没有相关旧条目？
   ├─ 有（信息更新了）→ patch 替换旧条目
   └─ 没有（全新信息）→ patch 追加到末尾
5. 检查总条数 > 20 → 删最旧不相关的
6. 回复用户
```

### Step 4: Patch 工具调用示例

**追加新信息：**
```json
patch(
  path: "~/.hermes/members/member_xxx/profile.json",
  old_string: "  \"notes\": []",
  new_string: "  \"notes\": [\"下周出差三天，无法训练\"]"
)
```

**替换旧信息（信息更新）：**
```json
patch(
  path: "~/.hermes/members/member_xxx/profile.json",
  old_string: "  \"injuries\": [\"深蹲时膝盖疼\"]",
  new_string: "  \"injuries\": [\"左膝已恢复，可以正常深蹲\"]"
)
```

**超 20 条清理（删最旧不相关的）：**
```json
patch(
  path: "~/.hermes/members/member_xxx/profile.json",
  old_string: "  \"notes\": [\"上个月加班多\", \"下周出差三天\", \"最近在准备考试\"]",
  new_string: "  \"notes\": [\"下周出差三天\", \"最近在准备考试\"]"
)
```

## 效果对比

### 无记忆机制时

```
Turn 1: 会员说膝盖疼 → 助手回复"跟教练说一声"
Turn 2: 会员问训练安排 → 助手建议深蹲 → 翻车（忘了膝盖疼）
```

### 有记忆机制后

```
Turn 1: 会员说膝盖疼 → patch 写入 injuries → 回复
Turn 2: 读 profile.json 带出 memory.injuries → 避开深蹲 → 会员满意
Turn 3: 会员说膝盖好了 → patch 替换 injuries（清空旧条目）→ 恢复正常安排
```

## 未来扩展

### workdir 机制（Cron 场景增强）

Hermes v0.12.0 支持 Per-job workdir。给每个会员的 cron job 设置 `workdir` 指向会员目录，cron 启动时自动注入 AGENTS.md。这能让 cron 场景（定时提醒、报告）的记忆注入达到 100% 可靠。

- 局限：仅对 cron 生效，群聊日常对话不适用
- 可以用机器人日常自动维护 AGENTS.md 来保持数据新鲜

### 新增 MCP 工具（计划中）

| 工具 | 用途 | 为什么用 MCP |
|------|------|-------------|
| `calculate_tdee` | TDEE/卡路里/宏量计算 | 确定性计算，模型算容易出错 |
| `generate_report` | 周报/月报生成 | 读数据→分析→生成，确定性流程，可封装在 cron 里 |
