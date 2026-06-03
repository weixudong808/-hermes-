# MCP Server 维护注意事项

## 修改 server.py 后必须重启 MCP 进程

- MCP server 是长驻 stdio 进程，修改代码后旧进程仍在运行旧代码
- 重启步骤：`kill` 旧进程 → Hermes 下次调用 MCP 工具时自动用新代码启动
- 验证连接：`hermes mcp test fitness-data`（显示 Connected + 11 tools = 正常）
- **⚠️ Hermes MCP 客户端有冷却期：** 连续失败 3 次后 ~46 秒内不可重试，会报 "unreachable after 3 consecutive failures"。此时不要反复调 MCP 工具，等冷却结束或用 `execute_code` 直接查 SQLite 做验证

## 修改 DB Schema 后必须重新同步

- ALTER TABLE 加列后，历史数据的该列为 NULL
- 必须跑 `python3 ~/.hermes/mcp-server/sync_to_sqlite.py` 从飞书全量同步来填充新列
- 验证：`execute_code` 直接查 SQLite 确认新列有值

## 课次-动作关联键（2026-05-17 修复，2026-05-23 确认状态）

- 旧关联键：`exercise_records.session_auto_id = training_sessions.session_auto_id`（已废弃，因 lark-cli 写入时拿不到 auto_number）
- 新关联键：`exercise_records.session_feishu_record_id = training_sessions.feishu_record_id`
- 录入时 lark-cli 写课次 → 拿到 `record_id` → 动作写入时通过飞书「关联课次」字段关联
- `session_auto_id` 列保留但**不再用于关联**
  - `training_sessions.session_auto_id`：同步脚本会写入（飞书 `课次id` 可读）
  - `exercise_records.session_auto_id`：**全部为 NULL**，同步脚本不写入此字段
  - ⚠️ 不要尝试通过此字段关联 exercise → training，用 `session_feishu_record_id` ↔ `feishu_record_id`

## sync_to_sqlite.py --member 清空全表 bug（2026-05-16 修复）

- **问题：** `--member` 模式清空数据时用的是 `DELETE FROM table`（清空所有会员），而不是 `DELETE FROM table WHERE member_id=?`。当 `maybe_auto_sync` 触发单会员同步 → 清空全表 → 同步因 lark-cli 授权失败 → 所有会员数据丢失。
- **修复：** `--member` 模式改为 `DELETE FROM {table} WHERE member_id = ?`，只清空指定会员数据。全量模式（不带 `--member`）保持 `DELETE FROM table` 不变。
- **教训：** 同步脚本的清空逻辑必须与同步范围一致。单会员同步绝不能影响其他会员数据。

## ✅ server.py init_db() 已修复（2026-05-23）

**问题：** `server.py` 原本缺少 `init_db()` 建表函数，首次部署时数据库为空，所有 MCP 工具调用报 `no such table: members`。

**修复：** 已在 `get_db()` 之前添加 `init_db()` 函数，模块加载时自动调用 `CREATE TABLE IF NOT EXISTS`。`init_db()` 代码与下方生产 Schema 完全一致。

**⚠️ 获取正确 Schema 的方法：** 代码中无法推断完整 Schema（INSERT/SELECT 不含约束信息）。**唯一可靠来源是从云端生产数据库导出：** `sqlite3 ~/.hermes/data/fitness.db ".schema"`。反推 Schema 会导致字段遗漏（如 `members.goal`、`sync_pending.action`）和约束错误（如 UNIQUE 应为联合唯一而非单列）。

### 生产环境完整 Schema（8 张表）

> 来源：2026-05-23 从云端 `sqlite3 fitness.db ".schema"` 导出，**不是代码推断**。

```sql
CREATE TABLE members (
    member_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    feishu_id TEXT,
    chat_id TEXT,
    goal TEXT,
    style TEXT,
    bitable_token TEXT,
    created_at TEXT
);

CREATE TABLE training_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    member_id TEXT NOT NULL REFERENCES members(member_id),
    session_auto_id INTEGER,
    date TEXT,
    body_parts TEXT,
    notes TEXT,
    feishu_record_id TEXT,
    created_at TEXT,
    UNIQUE(member_id, feishu_record_id)
);

CREATE TABLE exercise_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    member_id TEXT NOT NULL REFERENCES members(member_id),
    session_auto_id INTEGER,
    record_auto_id INTEGER,
    exercise_name TEXT,
    sets INTEGER,
    weight REAL,
    reps INTEGER,
    notes TEXT,
    feishu_record_id TEXT,
    created_at TEXT,
    session_feishu_record_id TEXT,
    UNIQUE(member_id, feishu_record_id)
);

CREATE TABLE diet_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    member_id TEXT NOT NULL REFERENCES members(member_id),
    record_auto_id INTEGER,
    date TEXT,
    content TEXT,
    source_table TEXT,
    feishu_record_id TEXT,
    created_at TEXT,
    UNIQUE(member_id, feishu_record_id)
);

CREATE TABLE weight_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    member_id TEXT NOT NULL REFERENCES members(member_id),
    date TEXT,
    weight REAL,
    source_table TEXT,
    feishu_record_id TEXT,
    created_at TEXT,
    UNIQUE(member_id, feishu_record_id)
);

CREATE TABLE cron_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    member_id TEXT NOT NULL REFERENCES members(member_id),
    job_name TEXT,
    job_id TEXT,
    schedule TEXT,
    enabled INTEGER DEFAULT 1,
    created_at TEXT
);

CREATE TABLE sync_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sync_type TEXT,
    status TEXT,
    tables_synced TEXT,
    affected_rows INTEGER,
    error_message TEXT,
    started_at TEXT,
    finished_at TEXT
);

CREATE TABLE sync_pending (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    member_id TEXT,
    table_name TEXT,
    action TEXT,
    payload TEXT,
    retry_count INTEGER DEFAULT 0,
    created_at TEXT,
    last_retry_at TEXT
);
```

**关键约束（代码推断无法得到）：**
- 所有数据表有 `REFERENCES members(member_id)` 外键
- 所有飞书关联表有 `UNIQUE(member_id, feishu_record_id)` 联合唯一（不是单列 UNIQUE）
- `sync_pending` 有 `action` 字段（推断版本遗漏）
- `members` 有 `goal` 字段（推断版本遗漏）
- 共 8 张表（推断版本只有 6 张，漏了 `cron_jobs` 和 `sync_log`）

## 同步架构决策（2026-05-24 确认）

### 数据写入的双通道

机器人通过 MCP server 写入数据时，`server.py` 的 `write_training`、`write_exercises`、`write_diet`、`write_weight` **同时写入飞书和 SQLite**，不需要跑同步脚本。

`sync_to_sqlite.py` 唯一要同步的是**教练直接在飞书多维表格里手动改的数据**（频率很低）。

### sync_to_sqlite.py 策略：全量 DELETE + 重灌

当前策略：先 DELETE 该会员的旧数据 → 从飞书全量拉取 → INSERT OR REPLACE。以飞书为唯一真相源。

**为什么不改增量同步：**
- lark-cli `record-list` 不支持按日期过滤，每次必须拉全量 → API 调用量无法减少
- 14 会员 × 4 表 = **56 次 API 调用/天**，无论全量还是增量都一样
- 全量 DELETE + 重灌逻辑最简单，bug 少，幂等性好
- 数据规模小（每人几百条），全量写入不到 2 秒，优化收益可忽略

**加 `--days` 参数能省什么：** 只省本地 SQLite 的删除和写入量，API 调用量一分不少。如果将来会员数超过 50+ 或单表超 5000 条再考虑。

### 是否需要每天自动同步

建议**日常不跑同步**，需要时手动触发（如教练在飞书手动改了数据后）。理由：
- 机器人写入已保证两边一致
- 每天白白消耗 56 次 API 调用
- 任何时候都可以手动跑一次全量同步来修正

### ⚠️ test_sync_consistency.py 已确认冗余（2026-05-24）

**结论：可以归档或删除。**

因为 `sync_to_sqlite.py` 每次都是全量 DELETE + 重灌，同步成功后本地和飞书**必定完全一致**。再跑检测脚本永远返回 ✅ 全部一致，等于白跑。

唯一能检测到不一致的场景是"同步失败了一半"（DELETE 成功但拉飞书时挂了），但这种情况重跑一次同步就能修好，检测脚本也救不了。

检测脚本最初是在"增量同步"思路下设计的审计工具，但既然最终选择了全量清空+重灌策略，它就没有存在价值了。

## sync_to_sqlite.py 权限问题：lark-cli 91403 错误（2026-05-29）

### 现象

`sync_to_sqlite.py` 对部分会员报 `91403 you don't have permission`，错误中 `"identity": "user"`。即使刷新 user token（`lark-cli auth login --recommend`）也无法解决。

### 根因

lark-cli 对不同会员的多维表格会使用不同身份：

| 会员类型 | 多维表格创建方式 | 身份 | 结果 |
|---------|-----------------|------|------|
| 铮然、元宝 | **应用（bot）通过模板复制创建** | bot | ✅ 正常 |
| 其余 12 人 | **教练手动创建后分享给 bot** | user | ❌ 91403 |

即使刷新了 user token，user 身份读取自己的文档也可能因飞书企业权限策略被拦截。这不是 token 过期问题，是**文档级权限问题**。

### 解决方案 A：让 bot 加入多维表格协作者

在飞书里打开对应多维表格 → 分享 → 添加协作者 → 搜索应用（Hermes）→ 给可阅读权限。一次操作永久生效。

### 解决方案 B：.base 文件导入（离线方式）

当 API 权限无法解决时，可让教练从飞书导出 .base 文件，直接解析写入 SQLite。

**.base 文件格式：** gzip 压缩的 JSON，结构如下：

```
{
  "gzipSnapshot": "<base64 gzip>",  // 包含表结构和记录数据
  "gzipExtraInfo": "<base64 gzip>", // 元信息
  "gzipDashboard": "<base64 gzip>", // 仪表盘配置
  "gzipAutomation": "<base64 gzip>",// 自动化（通常为空）
  "sign": "..."                     // 签名校验
}
```

**gzipSnapshot 解压后的结构：** 是一个**数组**，每个元素对应一张表的增量快照。最新元素是最完整的：

```python
import json, gzip, base64
with open("xxx.base") as f:
    data = json.load(f)
snapshot = json.loads(gzip.decompress(base64.b64decode(data["gzipSnapshot"])))
# snapshot[i]["schema"] 结构：
#   - base.blockInfos: {blockId: {name, blockType}} → 表名映射
#   - data.table.meta: {id, recordsNum} → 当前表 ID
#   - data.table.fieldMap: {fieldId: {name, type}} → 字段映射
#   - data.recordMap: {recordId: {fieldId: {value: ...}}} → 记录数据
```

**字段类型编码对照（重要，解析值时需要）：**

| type 值 | 含义 | 值格式 |
|---------|------|--------|
| 1 | 文本 | `[{text, type}]` 或纯字符串 |
| 2 | 数字 | 整数或浮点数 |
| 3 | 单选/多选 | `optXXXX`（选项 ID，需查找选项表） |
| 5 | 日期 | 毫秒时间戳 `1777996800000` |
| 18 | 关联字段 | `["recXXXX"]`（关联的 record_id 列表） |
| 20 | 公式/关联 | 值类型不固定 |
| 1005 | 自动编号 | `[{sequence, number}]` |

**⚠️ 单选字段值是选项 ID（如 `opt9eNIQz7`），不是可读文本。** 需要从 `fieldMap` 中的 `property.options` 映射出实际文本。训练主题、动作名称等都是单选字段。

**操作流程：** 教练从飞书导出 .base 文件 → 发到对话中 → 脚本解析并写入 SQLite。适合一次性批量导入历史数据。

**完整导入指南（含代码示例、选项 ID 解析、幂等写入）：** 详见 `references/base-file-import.md`。

## test_sync_consistency.py — 飞书 vs SQLite 一致性比对（已确认冗余，可归档）

**位置：** `~/.hermes/mcp-server/test_sync_consistency.py`

**用途：** 逐条字段比对飞书多维表格与本地 SQLite 的数据，检测缺失记录和值不一致。

**⚠️ 不是自动调用的：** 当前没有任何东西自动运行此脚本。`sync_to_sqlite.py` 不调用它，`health_check.py` 也不调用它。它是纯手动工具：
```bash
python3 ~/.hermes/mcp-server/test_sync_consistency.py              # 比对所有会员
python3 ~/.hermes/mcp-server/test_sync_consistency.py --member 元宝  # 只比对指定会员
```

**如需自动运行，** 需要在健康检查 cron 的 prompt 中添加一步调用。

### 比对范围

4 张数据表逐条字段比对（通过 `feishu_record_id` 匹配）：

| 表 | 比对字段 |
|----|---------|
| training_sessions | session_auto_id, date, body_parts, notes |
| exercise_records | record_auto_id, exercise_name, sets, weight, reps, notes, session_auto_id |
| diet_records | record_auto_id, date, content |
| weight_records | date, weight |

### 训练↔动作关联验证机制

脚本**不直接比对** `feishu_record_id` ↔ `session_feishu_record_id`。它通过飞书的关联关系间接验证 `session_auto_id`：

```
飞书动作记录.关联课次字段 → 拿到关联课次的 feishu_record_id
  → 查飞书训练课次表 → 拿到 session_auto_id
  → 与 SQLite exercise_records.session_auto_id 对比
```

### ⚠️ 已知误报问题：exercise_records.session_auto_id

**问题：** `compare_exercises` 第 343-357 行会验证 `session_auto_id`（通过飞书关联课次推导），但 `sync_to_sqlite.py` **不写入** `exercise_records.session_auto_id`（全部为 NULL），导致**每条动作记录都会报差异**：

```
[动作记录] 元宝 record=recXXXX: session_auto_id(link关联) 不一致 飞书推导=1 SQLite=None
```

**根因：** `session_auto_id` 是飞书多维表格的 auto_number 字段，lark-cli 写入时无法获取，同步脚本只读飞书数据不写入这个字段。

**待修复（方案 B，教练已确认方向）：** 从 `compare_exercises` 中删除或跳过 `session_auto_id` 验证（第 343-357 行），因为该字段已弃用，不应参与一致性校验。修复前需教练确认再动手。

### 输出

- 全部一致 → `✅ 所有数据完全一致！`，exit 0
- 有差异 → 列出每条差异的表名、会员名、record_id、字段名和两边值，exit 1
- ⚠️ 当前运行结果：exercise_records 的 `session_auto_id` 差异为已知误报（见上），其他字段如果一致则可忽略此误报
