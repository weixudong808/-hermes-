# Data Schema Reference

> 2026-05-03 整理。profile.json 和 group_map.json 的完整字段说明。
> **正式模板位置：** `templates/profile.json`（本 skill 内）。

## profile.json

**路径：** `~/.hermes/members/{member_id}/profile.json`

```json
{
  "basic_info": {
    "name": "王小明",
    "gender": "男",
    "age": 28,
    "height": 175,
    "health_conditions": []
  },
  "goal": "减脂",
  "fitness_level": "intermediate",
  "style": "energetic",
  "meals": {
    "breakfast": "07:30",
    "lunch": "12:00",
    "dinner": "18:30"
  },
  "reminder_freq": "每顿都提醒",
  "report_enabled": true,
  "training_days_per_week": 3,
  "diet_preference": "normal",
  "weight_reminder": "none",
  "notes": "特别喜欢五月天，讨厌吃西兰花",
  "joined_at": "2026-05-03"
}
```

### 字段说明

| 字段 | 类型 | 来源 | 说明 |
|------|------|------|------|
| `basic_info.name` | string | 问卷第1项 | 会员称呼 |
| `basic_info.gender` | string | 教练补充 | 性别 |
| `basic_info.age` | number | 教练补充 | 年龄 |
| `basic_info.height` | number | 教练补充 | 身高 cm |
| `basic_info.health_conditions` | array | 教练补充 | 健康状况/伤病 |
| `goal` | string | 问卷第2项 | "增肌"/"减脂"/"塑形" |
| `fitness_level` | string | 教练补充 | "beginner"/"intermediate"/"advanced" |
| `style` | string | 问卷第8项 | "energetic"(默认)/"professional"/"gentle"/"strict" |
| `meals.breakfast` | string/null | 问卷第3项 | 早餐时间 HH:MM，不需要提醒填 null |
| `meals.lunch` | string/null | 问卷第4项 | 午餐时间 |
| `meals.dinner` | string/null | 问卷第5项 | 晚餐时间 |
| `reminder_freq` | string | 问卷第6项 | "每顿都提醒"/"只提醒午餐和晚餐"/"其他" |
| `report_enabled` | boolean | 问卷第7项 | true=需周报月报，false=不需要（默认 true） |
| `training_days_per_week` | number | 教练补充 | 每周训练天数 |
| `diet_preference` | string | 教练补充 | "normal"/"vegetarian"/"keto"/"low_carb" |
| `weight_reminder` | string | 问卷第9项 | "none"(默认)/"daily"/"weekly" |
| `notes` | string | 问卷第10项 | 特殊习惯/爱好/过敏等自由备注 |
| `joined_at` | string | 建档时自动生成 | ISO 日期 |

### 已废弃字段（2026-05-03 移除）

| 废弃字段 | 去向 |
|---------|------|
| `basic_info.weight` | 多维表格"体重记录表" |
| `basic_info.target_weight` | 多维表格"体重记录表"（或 notes） |
| `basic_info.target_date` | 多维表格或 notes |
| `basic_info.allergies` | `notes` 字段 |

## group_map.json

**路径：** `~/.hermes/group_map.json`

```json
{
  "_config": {
    "coach_user_id": "ou_xxxxx"
  },
  "oc_xxxxx": {
    "member_id": "zhang_san",
    "member_name": "张三",
    "member_feishu_id": "ou_xxxxx",
    "bitable_token": "KO8PbLWk6aDJ2asQlricTKsxn2e",
    "table_ids": {
      "训练课次表": "tbloovwuHAUMIxop",
      "动作记录表": "tblE4LyJGAoX9flA",
      "饮食记录表": "tblXXXXXXXXXXXX",
      "体重记录表": "tblXXXXXXXXXXXX"
    },
    "style": "energetic",
    "report_enabled": true,
    "weight_reminder": "none",
    "reminder_freq": "每顿都提醒",
    "auto_record": true,
    "created_at": "2026-05-03T12:00:00"
  }
}
```

### 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `_config.coach_user_id` | string | 教练飞书 ID，全局唯一，身份判断用 |
| `oc_xxxxx`（key） | string | 群聊 chat_id，每条群消息用它查映射 |
| `member_id` | string | 拼音 ID，对应 `~/.hermes/members/{member_id}/` |
| `member_name` | string | 会员称呼，回复时用 |
| `member_feishu_id` | string | 会员飞书 ID，身份判断用 |
| `bitable_token` | string | 多维表格 token，所有 lark-cli base 命令必传 |
| `table_ids` | object | 表名 → table_id 映射，4 张表（训练课次/动作记录/饮食记录/体重记录） |
| `style` | string | 聊天风格，与 profile.json 同步 |
| `report_enabled` | boolean | 周报月报开关 |
| `weight_reminder` | string | "none"/"daily"/"weekly" |
| `reminder_freq` | string | 饮食提醒频率 |
| `auto_record` | boolean | 是否自动记录（默认 true） |
| `created_at` | string | 建档时间 |

### 已废弃字段

| 废弃字段 | 替代 |
|---------|------|
| `summary_freq` | `report_enabled`（true/false 统控周报月报） |
| `coach_user_id`（群条目内） | 已移至 `_config` 全局配置 |

### 重复字段说明

`style`、`member_name` 同时存在于 profile.json 和 group_map.json，原因：
- group_map.json 是群聊消息处理的入口文件，避免每次都要读取 profile.json 就能拿到关键信息
- profile.json 是会员完整档案，是 source of truth
- **修改时两边都要同步更新**（教练指令改称呼/改风格时）

## 数据一致性检查清单

排查问题时，快速检查点：

1. group_map.json 有 `report_enabled` 而非 `summary_freq`
2. ⚠️ group_map.json 的 `table_ids` 应有 4 张表（训练课次/动作记录/饮食记录/体重记录），但当前模板只有 2 张——见 SKILL.md 7.1.5
3. 已建会员（如 wang_xiaoming）的 group_map.json 仍是旧格式（2张表+summary_freq），需逐步迁移
4. profile.json 没有 `weight`/`target_weight`/`target_date`/`allergies` 字段
5. profile.json 有 `goal`/`meals`/`reminder_freq`/`report_enabled`/`weight_reminder` 字段
6. 旧 skill（`productivity/fitness-coaching-assistant`）是早期草稿，以本 skill 为准
