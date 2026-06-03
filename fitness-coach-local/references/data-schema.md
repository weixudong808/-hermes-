# Data Schema Reference

> 2026-05-06 整理。profile.json 和 group_map.json 的完整字段说明。
> **正式模板位置：** `templates/profile.json`（本 skill 内）。

## profile.json

**路径：** `~/.hermes/members/{member_id}/profile.json`

### 实际结构（扁平式，当前生产使用）

```json
{
  "name": "毛毛",
  "member_id": "maomao",
  "goal": "减脂",
  "style": "gentle",
  "meals": {
    "breakfast": "08:00",
    "lunch": "12:00",
    "dinner": "18:40"
  },
  "reminder_freq": "每顿都提醒",
  "report_enabled": false,
  "weight_reminder": "daily",
  "notes": "无",
  "cron_jobs": {
    "meal_breakfast": "db86d27dcafb",
    "meal_lunch": "0d5fcc3a4f25",
    "meal_dinner": "78559de0ac40",
    "weight": "2085cdbc678d"
  }
}
```

### 字段说明

| 字段 | 类型 | 来源 | 说明 |
|------|------|------|------|
| `name` | string | 问卷第1项 | 会员称呼 |
| `member_id` | string | 建档时自动生成 | 拼音/英文 ID，对应目录名 |
| `goal` | string | 问卷第2项 | "增肌"/"减脂"/"塑形" |
| `gender` | string | 教练补充 | 性别（可选） |
| `age` | number | 教练补充 | 年龄（可选） |
| `height` | number | 教练补充 | 身高 cm（可选） |
| `style` | string | 问卷第8项 | "energetic"(默认A)/"professional"(B)/"gentle"(C)/"strict"(D) |
| `meals.breakfast` | string/null | 问卷第3项 | 早餐时间 HH:MM，不需要提醒填 null/"无" |
| `meals.lunch` | string/null | 问卷第4项 | 午餐时间 |
| `meals.dinner` | string/null | 问卷第5项 | 晚餐时间 |
| `reminder_freq` | string | 问卷第6项 | "每顿都提醒"/"只提醒午餐和晚餐"/"其他" |
| `report_enabled` | boolean | 问卷第7项 | true=需周报月报，false=不需要（默认 true） |
| `weight_reminder` | string | 问卷第9项 | "none"(默认)/"daily"(每天08:00)/"weekly"(每周一09:00) |
| `notes` | string | 问卷第10项 | 特殊习惯/爱好/过敏等自由备注 |
| `cron_jobs` | object | 建档时由 Agent 写入 | cron job ID 追踪，详见下方 |

### cron_jobs 字段详解

**结构：** `{ cron_key: job_id | null }`

| cron_key | 说明 | job_id 来源 |
|----------|------|------------|
| `meal_breakfast` | 早餐提醒 | Agent 创建 cron 后写入 |
| `meal_lunch` | 午餐提醒 | Agent 创建 cron 后写入 |
| `meal_dinner` | 晚餐提醒 | Agent 创建 cron 后写入 |
| `weight` | 体重提醒 | Agent 创建 cron 后写入 |
| `weekly_report` | 周报 | Agent 创建 cron 后写入 |
| `monthly_report` | 月报 | Agent 创建 cron 后写入 |

**规则：**
- 建档时 `onboard_member.py` 创建 profile 时 `cron_jobs: {}` 为空
- Agent 根据 `meals`/`reminder_freq`/`weight_reminder` 逐个创建 cron，拿到 job_id 后写回此字段
- 没有 cron 的字段值为 `null` 或不存在
- 教练改时间 → 读取旧 job_id → 删除旧 job → 创建新 job → 更新此字段
- 会员退群 → 遍历所有值逐个删除 → 再删 profile

### 已废弃字段（已移除）

| 废弃字段 | 去向 |
|---------|------|
| `weight` / `target_weight` / `start_weight` / `target_date` | 多维表格"体重记录表" |
| `allergies` | `notes` 字段 |
| `basic_info.*`（嵌套结构） | 已展平为顶层字段（name, gender, age, height） |
| `fitness_level` | 未实际使用 |

### ⚠️ basic_info 嵌套结构残留

部分 profile.json 仍使用旧的 `basic_info` 嵌套格式（如 `member_c981e1aa`、`member_b48131ea`），`name`/`gender`/`age`/`height` 在 `basic_info` 下而不是顶层。改名或编辑这些 profile 时注意实际路径，不要假设一定是扁平结构。

**⚠️ 代码访问 profile.json name 时的正确写法（2026-05-17 踩坑）：**

必须兼容两种格式，不能只取顶层 `name`：
```python
# ❌ 错误：大部分 profile 的顶层没有 name 字段
name = data.get("name", "")

# ✅ 正确：先查嵌套格式，再查顶层
name = data.get("basic_info", {}).get("name") or data.get("name", "")
```
| `training_days_per_week` | 未实际使用 |
| `diet_preference` | 未实际使用 |
| `joined_at` | 改用 group_map.json 的 `created_at` |

## group_map.json

**路径：** `~/.hermes/group_map.json`

```json
{
  "_config": {
    "coach_user_id": "f754274g",
    "coach_openid": "ou_c76485c09fb788c48c5ca81d7d1445de",
    "coach_drive_folder_token": "XP8afWxJQlEYhGdyhoacyytRnIb",
    "feishu_domain": "pcn66xx6g0i0.feishu.cn"
  },
  "oc_xxxxx": {
    "member_id": "maomao",
    "member_name": "毛毛",
    "member_feishu_id": "ou_xxxxx",
    "bitable_token": "EDbAbXwDeafp38smHuDc2UZbnxh",
    "table_ids": {
      "训练课次表": "tblRZC46YcoY5ueG",
      "动作记录表": "tblhX95KGhBb9JG5",
      "饮食记录表": "tblUGxToiVxiaaMc",
      "体重记录表": "tblbTWLEJiE5adgQ"
    },
    "style": "gentle",
    "report_enabled": false,
    "weight_reminder": "daily",
    "reminder_freq": "每顿都提醒",
    "auto_record": true,
    "created_at": "2026-05-04T18:50:00"
  }
}
```

### 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `_config.coach_user_id` | string | 教练 Hermes user_id，身份判断用（与飞书 open_id 不同） |
| `_config.coach_openid` | string | 教练飞书 open_id（ou_ 开头），用于 drive API 分享多维表格 |
| `_config.coach_drive_folder_token` | string | 教练云盘「会员档案」文件夹 token |
| `_config.feishu_domain` | string | 飞书域名，用于构造多维表格 URL |
| `oc_xxxxx`（key） | string | 群聊 chat_id，每条群消息用它查映射 |
| `member_id` | string | 拼音 ID，对应 `~/.hermes/members/{member_id}/` |
| `member_name` | string | 会员称呼，回复时用 |
| `member_feishu_id` | string | 会员飞书 ID，身份判断用 |
| `bitable_token` | string | 多维表格 token，所有 lark-cli base 命令必传 |
| `table_ids` | object | 表名 → table_id 映射，4 张表 |
| `style` | string | 聊天风格，与 profile.json 同步 |
| `report_enabled` | boolean | 周报月报开关 |
| `weight_reminder` | string | "none"/"daily"/"weekly" |
| `reminder_freq` | string | 饮食提醒频率 |
| `auto_record` | boolean | 是否自动记录（默认 true） |
| `created_at` | string | 建档时间 ISO |

### 已废弃字段

| 废弃字段 | 替代 |
|---------|------|
| `summary_freq` | `report_enabled`（true/false 统控周报月报） |
| `coach_user_id`（群条目内） | 已移至 `_config` 全局配置 |

### 重复字段说明

`style`、`member_name` 同时存在于 profile.json 和 group_map.json，原因：
- group_map.json 是群聊消息处理的入口文件，避免每次都要读取 profile.json
- profile.json 是会员完整档案，是 source of truth
- **修改时两边都要同步更新**（教练指令改称呼/改风格时）

### 多 chat_id 映射同一会员

同一个会员可能有多个 chat_id（群聊 + 私聊），在 group_map.json 中是两条独立记录，指向同一个 `bitable_token` 和 `member_id`。

## 会员改名流程（Member Rename）

教练要求改名时（如"静姐"→"婧姐"），以下位置需要同步更新：

### 必须改（影响运行）

| # | 位置 | 字段 | 操作 |
|---|------|------|------|
| 1 | `group_map.json` | `{chat_id}.member_name` | JSON 编辑 |
| 2 | `profile.json` | `name`（顶层，新格式）或 `basic_info.name`（旧嵌套格式） | JSON 编辑 |
| 3 | `channel_directory.json` | 群名称中的会员名 | JSON 编辑（⚠️ 见下方同名区分坑） |
| 4-7 | cron jobs（最多4个） | `name` + `prompt` 中的会员名 | `hermes cron edit` |

**⚠️ cron job 改名步骤：**
1. 从 profile.json `cron_jobs` 读取该会员的 job_id 列表
2. 用 `hermes cron edit {job_id} --name "新名-XX提醒" --prompt "新prompt内容"` 逐个更新
3. prompt 中的旧名需手动替换为新名（prompt 是写死的文本，不会自动同步）
4. `hermes cron edit --prompt` 是覆盖式替换，不是追加，需传入完整 prompt 内容
5. **不需要**删旧建新，也不需要更新 profile.json 的 `cron_jobs`（job_id 不变）

**⚠️ 同名会员的 cron job 区分（2026-05-17 实战踩坑）：**

当多个会员同名时，**绝不能靠 cron job name 匹配**（都是"静姐-XX提醒"），必须通过 profile.json 的 `cron_jobs` 字段交叉确认：
```
profile.json → cron_jobs.breakfast_reminder → job_id → 确认这是哪个会员的
```
改错会员的 cron job 会导致另一个会员的提醒里名字被替换。

**⚠️ channel_directory.json 的坑（2026-05-17 实战踩坑）：**

`channel_directory.json` 存储群名称（如"贺静姐的健身群聊"），但群名称可能包含会员名。改名前必须用 chat_id 交叉确认该群属于哪个会员：
1. 从 group_map.json 获取目标会员的 chat_id
2. 在 channel_directory.json 中用该 chat_id 查找群名称
3. 只有 chat_id 匹配时才改名
4. **不要看到名字就改**，同名会员可能都有包含自己名字的群名

### 建议改（保持文档一致性）

| # | 位置 | 内容 |
|---|------|------|
| 8 | `references/cron-configuration.md` | 文档中提到的会员名案例 |
| 9 | `references/onboarding.md` | 文档中提到的会员名案例 |

### 不需要改

- `sessions/` — 历史会话日志，改了也没意义
- `cron/output/` — 历史提醒输出

### 同名会员区分

存在同名会员时（如两个"静姐"），先通过 `profile.json` 的 `memory.preferences`、`style`、`joined_at` 等特征区分，确认 member_id 后再改。**不要两个都改。**

## 数据一致性检查清单

1. profile.json 使用**扁平结构**（name/goal/style 在顶层），不是 `basic_info` 嵌套
2. profile.json 有 `cron_jobs` 字段，记录所有 cron job ID
3. group_map.json 有 `report_enabled` 而非 `summary_freq`
4. group_map.json 的 `table_ids` 应有 4 张表
5. ⚠️ 不同会员的表格字段名可能略有不同，写入失败时用 `+field-list` 查看
6. profile.json 没有 `weight`/`target_weight`/`allergies` 字段
7. `cron_jobs` 中的 job ID 必须在 `cronjob action=list` 结果中存在，不存在则需重建（幽灵 ID）
8. 旧 skill（`productivity/fitness-coaching-assistant`）是早期草稿，以本 skill 为准
