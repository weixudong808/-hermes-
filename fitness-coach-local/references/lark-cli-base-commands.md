# lark-cli base-copy / table-list Response Formats

> 2026-05-03 实测，用于 onboard_member.py 开发

## +base-copy — 复制多维表格

```bash
lark-cli base +base-copy \
  --base-token "{template_token}" \
  --name "{member_name}的健身档案" \
  --time-zone "Asia/Shanghai" \
  --as user
```

**返回格式：**
```json
{
  "ok": true,
  "identity": "user",
  "data": {
    "base": {
      "base_token": "KW0nbsxvya53gesRWmGcdTrUnpd",
      "folder_token": "",
      "name": "测试小明的健身档案",
      "time_zone": "Asia/Shanghai"
    }
  }
}
```

**关键字段：** `data.base.base_token`（注意不是 `token`，是 `base_token`）

**⚠️ 复制是异步的：** base-copy 返回后，表格可能还在复制中。立即调用 table-list 会报错：
```json
{"ok": false, "error": {"code": 800004046, "message": "base is copying, please try again"}}
```
**解决方案：** table-list 需要重试机制，遇到 "is copying" 时等待 3-6 秒后重试（最多 3 次）。

## +table-list — 列出表格

```bash
lark-cli base +table-list \
  --base-token "{base_token}" \
  --as user
```

**⚠️ 返回格式因 lark-cli 版本/环境不同而异：**

**本地 Mac（测试企业，较早版本）：**
```json
{
  "ok": true,
  "data": {
    "count": 2,
    "items": [
      {"table_id": "tblVgIbTOeOZCT1J", "table_name": "训练课次表"},
      {"table_id": "tblPVlZCOP9sWG4w", "table_name": "动作记录表"}
    ]
  }
}
```
字段：`data.items[].table_name` + `data.items[].table_id`

**云端（正式企业，v1.0.23）：**
```json
{
  "ok": true,
  "data": {
    "tables": [
      {"id": "tblASGa3K6DtxjCU", "name": "训练课次表"},
      {"id": "tbl7K2DXtUIB2FUg", "name": "动作记录表"}
    ],
    "total": 4
  }
}
```
字段：`data.tables[].name` + `data.tables[].id`

**兼容处理（onboard_member.py 已修复）：**
```python
tables = result.get("data", {}).get("tables") or result.get("data", {}).get("items", [])
for table in tables:
    t_name = table.get("name") or table.get("table_name", "")
    t_id = table.get("id") or table.get("table_id", "")
```

## 踩坑总结

1. **base_token vs token**：+base-copy 返回的是 `data.base.base_token`，不是 `data.base.token`
2. **table-list 响应格式不统一**：本地返回 `data.items` + `table_name`/`table_id`，云端返回 `data.tables` + `name`/`id`。`onboard_member.py` 已兼容两种格式（优先 `tables`/`id`，fallback `items`/`table_id`）
3. **异步复制延迟**：base-copy 后不能立即 table-list，需要重试等待
4. **lark-cli 路径**：本地 Mac 在 `~/.nvm/versions/node/v20.20.0/bin/lark-cli`，云端阿里云在 `/usr/local/bin/lark-cli`。脚本通过 `LARK_CLI_PATH` 环境变量支持覆盖
5. **模板 token**：测试模板 `TGixbmcoEaiZ43sfXvQcZ513nnf`，正式模板 `EMy6bp9iLagx7CsOlxgcf1uSnSb`。通过 `BITABLE_TEMPLATE_TOKEN` 环境变量可覆盖
6. **⚠️ `--as user` 需要两步配置**：仅 `lark-cli auth login` 不够，还需 `lark-cli config default-as user`。否则脚本中 `--as user` 不会生效，`+base-copy` 等操作会因 strict_mode 为 bot-only 而失败。新环境部署后必须确认 `lark-cli auth status` 中 `defaultAs` 为 `user`
