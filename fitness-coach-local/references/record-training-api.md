# record_training.py — 训练计划录入脚本 API

**位置：** `~/.hermes/skills/fitness-coach/scripts/record_training.py`
**测试：** `test_record_training.py`（30 用例，pytest，mock subprocess.run）
**风格：** 与 `record_weight.py` / `record_diet.py` 保持一致（命令行参数、JSON stdout/stderr、`fail()` 函数、`run_lark()`）

---

## 设计原则

- **脚本不做智能推断**：训练主题、动作名称别名映射、语义匹配均由 AI 助手在调用脚本前处理
- **先查后写**：每次写入调两轮 `+field-list`（训练主题 + 动作名称各一次），确保 Select 选项存在后再写入
- **覆盖式选项更新**：`+field-update` 时保留全部原有选项，追加新选项到末尾
- **部分容错**：单个动作写入失败不阻断其他动作，最终汇总成功/失败数量
- **只写飞书，不同步本地**

---

## 接口

### 写入模式（默认）

```bash
python3 record_training.py <token> <课次表> <动作表> \
  "<member_name>" "<date>" "<theme>" '<exercises_json>' [--coach-notes "备注"]
```

| 参数 | 说明 | 示例 |
|------|------|------|
| `token` | 飞书多维表格 bitable_token | `U3CFbwLL...` |
| 课次表 | 训练课次表 table_id | `tblXXXXXX` |
| 动作表 | 动作记录表 table_id | `tblYYYYYY` |
| member_name | 会员姓名 | `"张三"` |
| date | 日期 YYYY-MM-DD | `"2026-05-24"` |
| theme | 训练主题 | `"胸"` |
| exercises_json | 动作列表 JSON 字符串 | 见下方 |
| `--coach-notes` | 教练备注（可选，空字符串不传字段） | `"今天状态不错"` |

**exercises_json 格式：**
```json
[
  {"name": "卧推", "weight": 100, "sets": 4, "reps": 12},
  {"name": "龙门架夹胸", "weight": 30, "sets": 3, "reps": 15, "notes": "慢放"},
  {"name": "平板支撑", "sets": 3, "reps": 1, "notes": "1分钟×3组"}
]
```

| 字段 | 必填 | 说明 |
|------|------|------|
| `name` | ✅ | 动作名称 |
| `weight` | 否 | 重量（默认 0，自重动作不传） |
| `sets` | 否 | 组数（默认 1） |
| `reps` | 否 | 次数（默认 0） |
| `notes` | 否 | 备注（为空时不传该字段） |

**执行流程：**
1. 检查 `+field-list`（课次表）→ 补充训练主题选项（如有缺失）
2. `+record-upsert` 写课次 → 提取 `record_id`
3. 检查 `+field-list`（动作表）→ 批量补充动作名称选项
4. 逐个 `+record-upsert` 写动作（部分失败不阻断）

**输出（stdout JSON）：**
```json
{
  "ok": true,
  "session_id": "recvAAA",
  "theme": "胸",
  "date": "2026-05-24",
  "exercises_written": 3,
  "exercises_failed": 0,
  "results": [
    {"name": "卧推", "record_id": "recvBBB", "ok": true},
    {"name": "夹胸", "ok": false, "error": "lark-cli error: permission denied"}
  ]
}
```

### 删除课次模式（级联删除）

```bash
python3 record_training.py <token> <课次表> <动作表> \
  --delete --session-id recvXXX
```

先查所有关联该 session_id 的动作记录，逐个删除，最后删除课次。

**输出（stdout JSON）：**
```json
{
  "ok": true,
  "deleted_session": "recvAAA",
  "deleted_exercises": 3,
  "deleted_exercise_ids": ["recvBBB", "recvCCC", "recvDDD"]
}
```

### 删除单个动作模式

```bash
python3 record_training.py <token> <课次表> <动作表> \
  --delete-exercise --record-id recvXXX
```

直接删除指定动作记录，不查关联。

**输出（stdout JSON）：**
```json
{"ok": true, "deleted_exercise": "recvBBB"}
```

### 查询模式

```bash
python3 record_training.py <token> <课次表> <动作表> \
  --query --session-id recvXXX
```

查询所有关联指定课次的动作记录。

**输出（stdout JSON）：**
```json
{
  "ok": true,
  "session_id": "recvAAA",
  "exercise_count": 2,
  "exercises": [
    {"record_id": "recvBBB", "name": "卧推", "weight": 100, "sets": 4, "reps": 12, "notes": ""},
    {"record_id": "recvCCC", "name": "夹胸", "weight": 30, "sets": 3, "reps": 15, "notes": "慢放"}
  ]
}
```

### 错误处理

所有错误输出到 **stderr**（JSON 格式）：
```json
{"ok": false, "error": "错误描述"}
```

| 错误场景 | 错误信息关键词 |
|---------|-------------|
| 未来日期 | "未来日期" |
| exercises JSON 格式错误 | "动作 JSON 格式错误" |
| exercises 为空数组 | "动作列表不能为空" |
| `--delete` 和 `--delete-exercise` 同时传入 | "二选一" |
| `--delete` 缺少 `--session-id` | "需要 --session-id" |
| `--delete-exercise` 缺少 `--record-id` | "需要 --record-id" |
| `--query` 缺少 `--session-id` | "需要 --session-id" |
| lark-cli 超时 | "timed out" |
| `+field-list` 返回异常格式 | "field-list returned unexpected format" |

---

## 边界行为

| 场景 | 行为 |
|------|------|
| 未来日期 | 拒绝，不调 lark-cli |
| coach-notes 空字符串 | 不传 `教练备注` 字段（避免飞书显示空白单元格） |
| exercises 中某个 action 的 name 为空 | 跳过该动作，记录 failed |
| lark-cli 写入单个动作失败 | 记录 failure，继续写其余动作 |
| `--delete` 的 session_id 不存在 | lark-cli 返回错误，脚本透传 |
| `--delete-exercise` 的 record_id 不存在 | lark-cli 返回错误，脚本透传 |

---

## 内部实现

| 函数 | 说明 |
|------|------|
| `_run_lark(args)` | 执行 lark-cli，失败时 `fail()` 退出 |
| `_run_lark_safe(args)` | 执行 lark-cli，失败时返回 `(None, error_str)` 不退出（用于动作逐条写入） |
| `_get_field_options(token, table, field_name)` | `+field-list` 获取字段的 `(field_id, options_list)` |
| `_ensure_options(token, table, field_name, needed_values)` | 批量检查并补充缺失选项 |
| `_find_linked_exercises(token, exercise_table, session_id)` | `+record-list` 查找关联某课次的所有动作 record_id |
| `_build_exercise_payload(ex, session_id)` | 构建单条动作的 JSON payload |
| `_date_to_ts(date_str)` | YYYY-MM-DD → 毫秒时间戳（00:00 CST） |
| `_is_future_date(date_str)` | 判断是否为未来日期 |

---

## 测试要点（30 用例）

| 分类 | 用例数 | 覆盖点 |
|------|--------|--------|
| A 写入 | 14 | 单动作、多动作、主题透传、新主题自动添加、新动作自动添加、混合新旧、自重、指定日期、coach-notes、exercise notes、部分失败、10动作、空 notes 不传、未来日期拦截 |
| B 删除 | 7 | 级联删除、空课次删除、缺 session_id、lark 失败、单动作删除、不存在动作、flag 冲突 |
| C 查询 | 3 | 有结果、无结果、缺 session_id |
| D 错误 | 6 | 无效 JSON、空列表、无效日期、超时、缺参数、field-list 异常格式 |

## 实施陷阱（2026-05-24 实测）

### `+field-update` 缺少 `--yes` 导致 confirmation_required

**症状：** 脚本调用 `_ensure_options()` 补充 Select 选项时报 `confirmation_required`，错误信息 `add --yes to confirm`。
**原因：** lark-cli 的 `+field-update` 被归类为 `high-risk-write`，需要 `--yes` 确认。
**修复：** `_ensure_options()` 中 `+field-update` 命令必须包含 `--yes` 参数。已在 2026-05-24 修复。
**排查：** 其他脚本（`record_weight.py`、`record_diet.py`）如也调用 `+field-update`，需同步检查。

---

## 测试陷阱（2026-05-24 实测）：
- lark-cli 超时错误消息是 "timed out after 30 seconds"，不含 "timeout" → 测试用 `"timed" in err["error"].lower()` 而不是 `"timeout"`
- `+field-list` 返回 `{"fields": "not_a_list"}` 时 `fields` 遍历会静默成功（空迭代）→ 需要显式检查 `isinstance(fields, list)`，否则用缺失 key 的 mock（如 `{"wrong_key": []}`）会让 fields 默认为空列表，不会触发错误
