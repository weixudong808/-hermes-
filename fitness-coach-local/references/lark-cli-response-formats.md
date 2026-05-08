# lark-cli Response Formats (实测 2026-05-01)

## record-upsert — 训练课次表

```json
{
  "ok": true,
  "identity": "user",
  "data": {
    "created": true,
    "record": {
      "data": [["王小明", null, ["上肢"], "2026-05-01 00:00:00"]],
      "field_id_list": ["fldJ2eNvFY", "fldQvGvP5B", "fldcL2EosO", "fldgfsDJt0"],
      "fields": ["会员姓名", "教练备注", "训练主题", "训练日期"],
      "record_id_list": ["recvilxtoGKgtq"]
    }
  }
}
```

**关键字段：** `record_id_list[0]` 就是课次的 record_id，后续动作记录要用。

## record-upsert — 动作记录表

```json
{
  "ok": true,
  "identity": "user",
  "data": {
    "created": true,
    "record": {
      "data": [[
        [{"id": "recvilxtoGKgtq"}],  // 关联课次
        ["高位下拉"],                  // 动作名称
        15,                           // 次数
        1,                            // 组数
        45                            // 重量
      ]],
      "field_id_list": ["fldQw4HmLa","fldBKyYoSG","fldXIMYHgL","fld4jUPJUx","fldN7b0bkD"],
      "fields": ["关联课次","动作名称","次数","组数","重量"],
      "record_id_list": ["recvilxB9N7QUf"]
    }
  }
}
```

有备注时 fields 多一个 "备注"（fldPZdhm96），data 数组多一个元素。

## record-list — 训练课次表

```json
{
  "ok": true,
  "data": {
    "data": [
      ["1", ["下肢"], "2025-05-01 08:00:00", "王小明", "测试写入"],
      ["2", ["上肢"], "2026-05-01 00:00:00", "王小明", null]
    ],
    "fields": ["课次id","训练主题","训练日期","会员姓名","教练备注"],
    "has_more": false,
    "record_id_list": ["recvilqKEQFctK","recvilxtoGKgtq"]
  }
}
```

**解析：** `data[i]` 按字段顺序排列，`record_id_list[i]` 对应第 i 条记录。

## record-list — 动作记录表

```json
{
  "ok": true,
  "data": {
    "data": [
      ["1","2025/05/01",4,["深蹲"],"王小明",60,"膝盖无不适",[{"id":"recvilqKEQFctK"}],12],
      ["2","2026/05/01",1,["高位下拉"],"王小明",45,null,[{"id":"recvilxtoGKgtq"}],15]
    ],
    "fields": ["记录id","训练日期","组数","动作名称","会员姓名","重量","备注","关联课次","次数"],
    "has_more": false,
    "record_id_list": ["recvilqQn6zjiL","recvilxB9N7QUf"]
  }
}
```

**注意：** 动作名称返回的是数组 `["深蹲"]` 不是字符串。关联课次返回 `[{"id":"xxx"}]` 对象数组。重量为 0 代表自重或未填。

## 实测踩坑

1. 日期用毫秒时间戳（如 `1777564800000`），返回格式为 `"2026-05-01 00:00:00"`
2. 训练主题是数组 `["上肢"]`
3. 动作名称是数组 `["深蹲"]`
4. 关联字段传字符串 `"recvilxtoGKgtq"`，返回时变成 `[{"id":"recvilxtoGKgtq"}]`
5. `--json` 传 flat 对象，不能 `{"fields":{...}}`
6. `has_more: false` 表示没有更多页
