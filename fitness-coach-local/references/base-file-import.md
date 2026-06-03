# .base 文件导入：绕过 API 权限的数据同步方案

## 背景

`sync_to_sqlite.py` 通过 lark-cli 调飞书 API 同步数据。部分会员的多维表格由教练**个人创建**（非应用模板复制），导致 lark-cli 用 `user` 身份请求时仍报 `91403 you don't have permission`。刷新 user token 也不能解决。

**适用场景：** sync_to_sqlite.py 报 91403 且无法通过权限配置解决时，用 .base 文件导入作为 fallback。

## .base 文件结构

飞书多维表格「导出 → .base」生成的文件是 JSON 格式，核心字段：

```json
{
  "gzipSnapshot": "<base64(gzip(json))>  ← 核心数据",
  "gzipExtraInfo": "<base64(gzip(json))>",
  "gzipDashboard": "<base64(gzip(json))>",
  "gzipAutomation": "<base64(gzip(json))>",
  "sign": "<md5>"
}
```

**⚠️ gzipSnapshot 包含完整记录数据**，不是只有 schema。

### gzipSnapshot 解析

解压后是一个数组，每个元素对应一次表结构变更的增量快照：

```python
snapshot = json.loads(gzip.decompress(base64.b64decode(data["gzipSnapshot"])))
# snapshot[i]["schema"] -> {base, owner, tableMap, data, structVersion}
```

**关键子结构：**

| 路径 | 内容 |
|------|------|
| `schema.base.blockInfos` | 所有表的 ID→名称映射 |
| `schema.data.table.meta` | 当前表元信息（tableId, name, recordsNum） |
| `schema.data.table.fieldMap` | 字段定义（fieldId → {name, type, property}） |
| `schema.data.table.recordMap` | **所有记录数据**（recordId → {fieldId: {value: ...}}） |

**重要：每个 snapshot 元素通常对应一张表**（按创建顺序）。最后几个元素包含所有表的完整数据。

## 字段值解析

### 选项字段（Multi-select, type=3）

选项字段存储的是选项 ID（如 `opt9eNIQz7`），不是可读文本。需要从 `fieldMap[fieldId].property.options` 中解析映射：

```python
# 构建选项映射
field_info = field_map[field_id]  # type=3 的字段
options = field_info["property"]["options"]  # [{id: "optXxx", name: "背"}, ...]
opt_id_to_name = {opt["id"]: opt["name"] for opt in options}
```

### 其他常见字段类型

| type | 含义 | value 格式 |
|------|------|-----------|
| 1 | 文本 | `[{text: "xxx", type: "text"}]` |
| 2 | 数字 | `60` / `0` |
| 3 | 多选 | `"optXxx"` 或 `["optXxx", "optYyy"]` |
| 5 | 日期 | 毫秒时间戳 `1777996800000` |
| 18 | 关联字段 | `["recvXxx"]`（关联记录 ID 列表） |
| 20 | 关联字段(新) | 同上 |
| 1005 | 自动编号 | `[{sequence: "21", number: "21"}]` |

### 富文本提取

```python
def extract_text(val):
    if isinstance(val, list):
        return "".join(item.get("text", "") for item in val if isinstance(item, dict))
    return str(val).strip()
```

### 时间戳转换

```python
from datetime import datetime
date_str = datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d")
```

## 完整导入流程

### 1. 获取 .base 文件

教练从飞书导出多维表格为 .base 文件，通过飞书发送。文件保存到 `~/.hermes/cache/documents/`。

### 2. 解析并写入 SQLite

```python
import json, gzip, base64, sqlite3
from datetime import datetime

BASE_FILE = "~/.hermes/cache/documents/doc_xxx.base"
DB_PATH = "~/.hermes/data/fitness.db"
MEMBER_ID = "member_xxx"  # 从 group_map.json 获取

# 1. 解压
with open(BASE_FILE) as f:
    raw = json.load(f)
snapshot = json.loads(gzip.decompress(base64.b64decode(raw["gzipSnapshot"])))

# 2. 提取每张表的 fieldMap + recordMap + 选项映射
for item in snapshot:
    schema = item["schema"]
    table_data = schema["data"]["table"]
    field_map = table_data["fieldMap"]
    record_map = table_data["recordMap"]
    table_id = table_data["meta"]["id"]
    table_name = schema["base"]["blockInfos"][table_id]["name"]

    # 3. 根据 table_name 分类写入对应的 SQLite 表
    #    训练课次表 → training_sessions
    #    动作记录表 → exercise_records
    #    健身饮食记录表 → diet_records
    #    私教会员体重记录表 → weight_records
```

### 3. 选项 ID 解析（导入后立即执行）

导入完成后，立即解析所有选项字段 ID 为可读文本：

```python
# 训练主题 opt → 中文名
# 动作名称 opt → 中文名
# UPDATE training_sessions SET body_parts = '[\"背\"]' WHERE body_parts = '["opt9eNIQz7"]'
```

**⚠️ 选项 ID 来自该会员自己的多维表格，不同会员的选项 ID 不同。每次导入必须重新解析。**

## 注意事项

1. **INSERT OR REPLACE**：用 `UNIQUE(member_id, feishu_record_id)` 保证幂等，可重复导入
2. **source_table 字段**：diet_records 和 weight_records 写 `"base_file"` 区分来源
3. **关联字段**：动作记录表的「关联课次」字段存的是 `session_feishu_record_id`，用于 JOIN
4. **增量导入**：如果只导出新数据，可指定日期范围过滤 recordMap
5. **与其他会员数据共存**：不影响已有数据（铮然、元宝等通过 API 同步的数据不受影响）

## 已知限制

- .base 文件由教练手动导出，非自动化流程
- 导出时可能不包含最新记录（取决于导出时间点）
- 如果多维表格字段结构变化（新增/删除列），需要调整解析代码
