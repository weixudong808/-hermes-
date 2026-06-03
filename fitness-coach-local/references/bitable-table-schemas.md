# 飞书多维表格实际字段结构

> 2026-05-16 从飞书 API 实测获取。不同会员的表格名可能不同，但字段结构一致。

## 表名差异

飞书表格存在两套命名（同一模板在不同时期复制导致），但结构相同：

| 类型 | 旧名（毛毛等） | 新名（萌姐等） |
|------|---------------|---------------|
| 饮食表 | 饮食记录表 | 健身饮食记录表 |
| 体重表 | 体重记录表 | 私教会员体重记录表 |

**本地数据库设计时应用同一张表，加 `source_table_name` 字段区分来源。**

## 训练课次表

| 字段名 | 类型 | 说明 |
|--------|------|------|
| 教练备注 | text | 教练附注 |
| 课次id | auto_number | 自动编号，length=3 |
| 会员姓名 | text | 会员称呼 |
| 训练日期 | datetime | 格式 yyyy/MM/dd |
| 训练主题 | select (multiple) | 选项：胸、上肢、下肢、核心 |

## 动作记录表

| 字段名 | 类型 | 说明 |
|--------|------|------|
| 次数 | number | precision=0 |
| 备注 | text | 自由文本 |
| 动作名称 | select (single) | 下拉选项，需自动补充 |
| 重量 | number | precision=1 |
| 组数 | number | precision=0 |
| 关联课次 | link → 训练课次表 | 关联字段 |
| 会员姓名 | formula | 引用关联课次的会员姓名，**本地不需要存** |
| 记录id | auto_number | 自动编号，length=3 |
| 训练日期 | formula | 引用关联课次的训练日期，**本地不需要存** |

**注意：** 会员姓名和训练日期是 formula 字段，通过关联课次自动计算。本地数据库只需存 member_id + session_id 即可推导。

## 饮食记录表 / 健身饮食记录表

| 字段名 | 类型 | 说明 |
|--------|------|------|
| 饮食内容 | text | 自由文本 |
| 记录ID | auto_number | 自动编号，length=3 |
| 记录日期 | datetime | 格式 yyyy/MM/dd |

**结构极其简单**，只有 3 个字段。没有餐次字段，餐次信息需要从饮食内容文本中推断。

## 体重记录表 / 私教会员体重记录表

| 字段名 | 类型 | 说明 |
|--------|------|------|
| 单选 | select (single) | 目前选项为空，用途待确认（可能是晨起/睡前体重分类） |
| 日期 | datetime | 格式 yyyy/MM/dd |
| 体重 | number | precision=1 |

## 本地 SQLite Schema（生产环境）

> ⚠️ **Schema 来源：** 2026-05-23 从云端生产数据库 `sqlite3 fitness.db ".schema"` 导出。**不要从代码反推 Schema**（会遗漏字段和约束）。
> ⚠️ `server.py` 已添加 `init_db()` 函数（2026-05-23），首次部署自动建表。完整 DDL 见 `references/mcp-server-maintenance.md`。

### 8 张表概览

| 表名 | 用途 | 关键约束 |
|------|------|---------|
| `members` | 会员基本信息 | `member_id` PK, `name` NOT NULL, 有 `goal` 字段 |
| `training_sessions` | 训练课次 | `UNIQUE(member_id, feishu_record_id)` |
| `exercise_records` | 动作记录 | `UNIQUE(member_id, feishu_record_id)`, 有 `session_feishu_record_id` |
| `diet_records` | 饮食记录 | `UNIQUE(member_id, feishu_record_id)` |
| `weight_records` | 体重记录 | `UNIQUE(member_id, feishu_record_id)` |
| `cron_jobs` | 定时任务配置 | — |
| `sync_log` | 同步日志 | — |
| `sync_pending` | 待同步队列 | 有 `action` 字段（反推版本遗漏） |

所有数据表（除 `sync_log`、`sync_pending`）有 `REFERENCES members(member_id)` 外键。

### 与规划版 Schema 的关键差异

| 差异 | 规划版 | 生产版 |
|------|--------|--------|
| 课次日期列名 | `training_date` | `date` |
| 课次主题列名 | `training_theme` | `body_parts` |
| 教练备注列名 | `coach_notes` | `notes` |
| 同步时间列名 | `synced_at` | `created_at` |
| 饮食日期列名 | `record_date` | `date` |
| 动作关联键 | `session_id` (FK→id) | `session_feishu_record_id` (TEXT) |
| 体重 `select_option` | 有 | 无 |
| `sync_pending.action` | 无 | 有 |
| `members.goal` | 无 | 有 |
| `cron_jobs` 表 | 无 | 有 |
| UNIQUE 约束 | 无 | `UNIQUE(member_id, feishu_record_id)` |
| 外键约束 | 有 | 有（生产版确认存在） |

### 规划版 Schema（已废弃，仅历史参考）

完整 DDL 已被生产版替代。关键差异见上表。如需查看原始规划 SQL，查看 Git 历史。

| 飞书类型 | SQLite 类型 | 备注 |
|---------|-------------|------|
| text | TEXT | |
| number | REAL | 统一用 REAL，precision 由应用层控制 |
| datetime | TEXT | 存 ISO 格式 YYYY-MM-DD |
| select | TEXT | 多选用 JSON array 字符串 |
| auto_number | INTEGER | |
| link | INTEGER (FK) | 关联字段用外键 |
| formula | 不存储 | 可从关联推导 |
