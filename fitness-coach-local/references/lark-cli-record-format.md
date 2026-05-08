# lark-cli Record 操作格式备忘

> 从实际会话中观察到的返回格式，2026-05-01

## record-upsert 返回结构

```json
{
  "ok": true,
  "identity": "user",
  "data": {
    "created": true,
    "record": {
      "data": [[值1, 值2, ...]],
      "field_id_list": ["fldXXXX", ...],
      "fields": ["会员姓名", "教练备注", "训练主题", "训练日期"],
      "record_id_list": ["recvilxtoGKgtq"]
    }
  }
}
```

**取 record_id 的位置：** `data.record.record_id_list[0]`

### 关联字段在返回中的格式

当动作记录的关联课次写入成功后，返回中关联字段显示为：
```json
[{"id": "recvilxtoGKgtq"}]
```
即嵌套数组+对象，但**写入时只需传字符串** `recvilxtoGKgtq`。

## 训练课次表字段顺序

| 字段名 | field_id | 写入值类型 |
|--------|----------|-----------|
| 会员姓名 | fldJ2eNvFY | 字符串 |
| 教练备注 | fldQvGvP5B | 字符串（可为 null） |
| 训练主题 | fldcL2EosO | 字符串数组 `["上肢"]` |
| 训练日期 | fldgfsDJt0 | 毫秒时间戳 `1777564800000` |

## 动作记录表字段顺序

| 字段名 | field_id | 写入值类型 |
|--------|----------|-----------|
| 关联课次 | fldQw4HmLa | record_id 字符串 |
| 动作名称 | fldBKyYoSG | 字符串（单选） |
| 次数 | fldXIMYHgL | 整数 |
| 组数 | fld4jUPJUx | 整数 |
| 重量 | fldN7b0bkD | 数字（整数或小数） |
| 备注 | fldPZdhm96 | 字符串（可选） |

## 体重记录表字段

| 字段名 | field_id | 写入值类型 |
|--------|----------|-----------|
| 体重 | fld0jSCLOb | 数字（整数或小数） |
| 日期 | fldIQukLf4 | 自动填充当天日期，不需要手动写入 |

⚠️ 字段名是「体重」，不是「体重kg」。写 `"体重kg"` 会导致 800030201 not_found。

## 日期时间戳换算

```python
from datetime import datetime
# 2026-05-01 00:00:00 CST (UTC+8)
ts = int(datetime(2026, 5, 1).timestamp() * 1000)  # → 1777564800000
```

## 完整写入流程示例（1次训练3个动作 = 4次 lark-cli 调用）

```bash
# Step 1: 写训练课次
lark-cli base +record-upsert \
  --base-token "KO8PbLWk6aDJ2asQlricTKsxn2e" \
  --table-id "tbloovwuHAUMIxop" \
  --as user \
  --json '{"会员姓名":"王小明","训练日期":1777564800000,"训练主题":["上肢"],"教练备注":""}'
# → record_id = recvilxtoGKgtq

# Step 2: 写动作1 - 高位下拉
lark-cli base +record-upsert \
  --base-token "KO8PbLWk6aDJ2asQlricTKsxn2e" \
  --table-id "tblE4LyJGAoX9flA" \
  --as user \
  --json '{"动作名称":"高位下拉","组数":1,"次数":15,"重量":45.0,"关联课次":"recvilxtoGKgtq"}'

# Step 3: 写动作2 - 坐姿划船
lark-cli base +record-upsert \
  --base-token "KO8PbLWk6aDJ2asQlricTKsxn2e" \
  --table-id "tblE4LyJGAoX9flA" \
  --as user \
  --json '{"动作名称":"坐姿划船","组数":1,"次数":15,"重量":56.0,"关联课次":"recvilxtoGKgtq"}'

# Step 4: 写动作3 - 引体向上（自重）
lark-cli base +record-upsert \
  --base-token "KO8PbLWk6aDJ2asQlricTKsxn2e" \
  --table-id "tblE4LyJGAoX9flA" \
  --as user \
  --json '{"动作名称":"引体向上","组数":1,"次数":15,"重量":0,"关联课次":"recvilxtoGKgtq","备注":"自重"}'
```
