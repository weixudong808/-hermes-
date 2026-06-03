# lark-cli base-copy / table-list Response Formats

> 2026-05-03 实测，用于 onboard_member.py 开发

## +base-copy — 复制多维表格

```bash
# ⚠️ 不要带 --as user，云端 strict_mode 为 bot-only
# ⚠️ 不要带 --time-zone，会导致 "timeZone is not a valid IANA timezone" 错误（2026-05-04 实测，lark-cli 1.0.23）
lark-cli base +base-copy \
  --base-token "{template_token}" \
  --name "{member_name}的健身档案"
```

**返回格式：**
```json
{
  "ok": true,
  "identity": "bot",
  "data": {
    "base": {
      "base_token": "KW0nbsxvya53gesRWmGcdTrUnpd",
      "folder_token": "",
      "name": "测试小明的健身档案"
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
# ⚠️ 不要带 --as user，云端 strict_mode 为 bot-only
lark-cli base +table-list \
  --base-token "{base_token}"
```

**返回格式（bot 模式，table-list 用 `tables` 而非 `items`）：**
```json
{
  "ok": true,
  "identity": "bot",
  "data": {
    "tables": [
      {
        "id": "tblVgIbTOeOZCT1J",
        "name": "训练课次表"
      }
    ],
    "total": 4
  }
}
```

**关键字段（⚠️ bot vs user 返回格式不同）：**
- **bot 身份：** `data.tables[].name` + `data.tables[].id`
- **user 身份（旧版）：** `data.items[].table_name` + `data.items[].table_id`
- `onboard_member.py` 已兼容两种格式（同时检查 `name`/`table_name` 和 `id`/`table_id`）

## +base-get — 获取多维表格信息（含 URL）

```bash
lark-cli base +base-get \
  --base-token "{base_token}"
```

**返回格式：**
```json
{
  "ok": true,
  "identity": "bot",
  "data": {
    "base": {
      "base_token": "LNd5bEpDia5FGzsNd0IcA5Gqngg",
      "is_advanced": false,
      "name": "陈航的健身档案",
      "revision": 0,
      "time_zone": "Asia/Shanghai",
      "url": "https://pcn66xx6g0i0.feishu.cn/base/LNd5bEpDia5FGzsNd0IcA5Gqngg"
    }
  }
}
```

**用途：** 当会员要求查看/打开自己的多维表格时，用此命令获取可分享的飞书链接。`data.base.url` 是完整的飞书访问地址。

## 共享给会员（非教练）

Onboard 时的自动共享只给教练（openid）。如果会员后续请求访问自己的表格，需要额外通过 drive API 共享：

```python
# 获取 tenant_access_token
# ...
# 共享给会员（使用 unionid）
req = urllib.request.Request(
    f"https://open.feishu.cn/open-apis/drive/v1/permissions/{BASE_TOKEN}/members?type=bitable",
    data=json.dumps({
        "member_type": "unionid",
        "member_id": MEMBER_UNION_ID,  # on_xxx 格式
        "perm": "full_access"
    }).encode(),
    headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
    method="POST"
)
```

**⚠️ member_feishu_id 不可用：** `group_map.json` 里的 `member_feishu_id` 字段是入群问卷时会员自己填写的 ID，格式不确定，**不是**有效的飞书 API 用户标识。共享时必须使用 `unionid`（`on_xxx` 格式）。

**获取会员 unionid 的方式：** 从 `HERMES_SESSION_KEY` 环境变量中提取。格式为 `agent:main:feishu:group:{chat_id}:on_{union_id}`，最后一个 `:` 后的 `on_` 开头的值就是 unionid。

**另一种方式（如果 session key 不可用）：** 通过飞书消息事件中的 `sender.sender_id.union_id` 字段获取（Hermes 会话上下文中通常可见）。

## 共享给群聊（让文档出现在群聊「云文档」tab）

**⚠️ member_type 不是 `chat_id`，是 `openchat`**（2026-05-08 实测踩坑）：传 `chat_id` 会返回 400 `field validation failed`。飞书 drive API 共享给群聊的正确 member_type 为 `openchat`。

```python
# 共享给群聊（member_type = "openchat"，不是 "chat_id"）
req = urllib.request.Request(
    f"https://open.feishu.cn/open-apis/drive/v1/permissions/{BASE_TOKEN}/members?type=bitable",
    data=json.dumps({
        "member_type": "openchat",
        "member_id": CHAT_ID,  # oc_xxx 格式
        "perm": "full_access"
    }).encode(),
    headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
    method="POST"
)
```

**效果：** 共享成功后，该多维表格会出现在群聊的「云文档」tab 中，群成员可直接查看。`onboard_member.py` 已内置此逻辑（步骤 6b）。

**完整的 member_type 有效值：** `email, openid, unionid, openchat, opendepartmentid, userid, groupid, wikispaceid, appid`

## 给另一个 Bot 应用添加协作者权限

**场景：** 多维表格由应用 A 创建（A 拥有所有权），需要让应用 B 也能操作这些表格。

### 前提：获取目标 Bot 的 open_id

**⚠️ Bot 的 open_id ≠ app_id。** 不能用 app_id（`cli_xxx`）作为 member_id。

每个飞书应用 bot 有独立的 open_id（`ou_xxx` 格式），通过 bot info API 获取：

```bash
# 查询当前 lark-cli 对应 bot 的 open_id
lark-cli api GET /open-apis/bot/v3/info/
# 返回: {"bot":{"open_id":"ou_xxx","app_name":"xxx"}}
```

**⚠️ 这只能查当前 lark-cli 登录的 bot 的 open_id。** 要查目标 bot（应用 B）的 open_id，需要先用应用 B 的凭证获取 tenant_access_token 后调用同一 API：

```python
import urllib.request, json
token_resp = json.loads(urllib.request.urlopen(
    urllib.request.Request(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        data=json.dumps({"app_id": "cli_xxx", "app_secret": "xxx"}).encode(),
        headers={"Content-Type": "application/json"}
    ), timeout=30).read())
access_token = token_resp["tenant_access_token"]

bot_info = json.loads(urllib.request.urlopen(
    urllib.request.Request(
        "https://open.feishu.cn/open-apis/bot/v3/info/",
        headers={"Authorization": f"Bearer {access_token}"}
    ), timeout=30).read())
print(bot_info["bot"]["open_id"])  # ou_xxx
```

### 用 lark-cli 添加协作者

```bash
lark-cli drive permission.members create \
  --params '{"token":"{bitable_token}","type":"bitable","need_notification":false}' \
  --data '{"member_id":"{目标bot的open_id}","member_type":"openid","perm":"full_access","type":"user"}'
```

**参数说明：**
- `member_id` = 目标 bot 的 open_id（`ou_xxx`），**不是** app_id
- `member_type` = `openid`（不是 `userid`，不是 `appid`）
- `perm` = `full_access`（可管理）、`edit`（可编辑）、`view`（可阅读）
- `type` = `user`（bot 也用 `user` 类型）
- `--params` 中的 `type` = `bitable`（文件类型标识）

**⚠️ 踩坑（2026-05-22 实测）：** 用 app_id（`cli_xxx`）作为 member_id + member_type=`openid` 或 `userid` 都会返回 `1063001 Invalid parameter`。必须先用 bot info API 获取 open_id（`ou_xxx`），再用 open_id 作为 member_id。

### 批量操作脚本（所有会员表格）

当需要给应用 B 授权所有 15 个会员的多维表格时，遍历 `group_map.json` 中的所有 `bitable_token`，对每个执行上述命令。

### 切换 lark-cli 到新应用

授权完成后，修改 `~/.lark-cli/config.json`：

```json
{
  "apps": [{
    "appId": "cli_a9789ef1a0b85cd5",  // 新 app_id
    "appSecret": {
      "source": "plain",
      "value": "new_app_secret_here"
    },
    "brand": "feishu",
    "lang": "zh"
  }]
}
```

**⚠️ appSecret source：** 原 config 用 `"source": "keychain"`（macOS Keychain），新应用需要用 `"source": "plain"` + `"value": "xxx"` 或先通过 `lark-cli auth login` 配置。

### 转移所有权（可选）

lark-cli 还支持 `drive permission.members transfer_owner`，可以把文件所有权从当前应用转移到另一个用户。但**不能转移给 bot 应用**，只能转移给人类用户。所以对于 bot-to-bot 场景，只能用协作者权限方案。

## 踩坑总结

1. **base_token vs token**：+base-copy 返回的是 `data.base.base_token`，不是 `data.base.token`
2. **table_name vs name**：+table-list 返回格式因身份而异（见上方）。bot 用 `tables[].name`，user 用 `items[].table_name`
3. **异步复制延迟**：base-copy 后不能立即 table-list，需要重试等待
4. **lark-cli 路径**：本地 Mac 在 `~/.nvm/versions/node/v20.20.0/bin/lark-cli`，云端阿里云在 `/usr/local/bin/lark-cli`。脚本通过 `LARK_CLI_PATH` 环境变量支持覆盖
5. **模板 token**：脚本默认 `TGixbmcoEaiZ43sfXvQcZ513nnf`（旧测试企业），正式企业通过 `BITABLE_TEMPLATE_TOKEN` 环境变量覆盖。实际使用的模板请以环境变量为准。
6. **⚠️ --time-zone 参数会导致 base-copy 失败**：lark-cli 1.0.23 传 `--time-zone "Asia/Shanghai"` 报 `800004006 timeZone is not a valid IANA timezone`。不传时区参数即可正常复制。
7. **⚠️ --as user 在云端被拦截**：strict_mode bot-only 下所有 lark-cli 命令都不要带 `--as user`
8. **表格在机器人云空间**：base-copy 创建的表格默认在 bot 的云空间，教练看不到。必须通过 drive API 共享（见下方「自动共享给教练」）
9. **⚠️ 群聊共享 member_type 是 `openchat` 不是 `chat_id`**：drive API 共享给群聊时，`member_type` 必须填 `openchat`，填 `chat_id` 会 400 报错 `field validation failed`

## 自动共享给教练和群聊（onboard_member.py 内置）

base-copy 创建的表格在机器人云空间里，教练默认看不到。脚本在复制后自动通过 **drive API** 把教练加为协作者：

```bash
# API（非 lark-cli，脚本内 urllib 调用）
POST https://open.feishu.cn/open-apis/drive/v1/permissions/{base_token}/members?type=bitable
Authorization: Bearer {tenant_access_token}
{"member_type": "openid", "member_id": "{coach_openid}", "perm": "full_access"}
```

**返回 `{"code": 0}` 表示成功。** 教练在飞书「与我共享」中可直接看到。

**⚠️ 不是 bitable API**：飞书多维表格权限管理用的是 drive API（`/drive/v1/permissions/`），不是 bitable API（`/bitable/v1/apps/.../permissions/...`）。bitable 权限 API 返回 404。

**⚠️ 共享给群聊的已知限制（2026-05-08）：**
通过 drive permissions API 给群聊（`member_type: "openchat"`）加权限后，文档**不会自动出现在群的「云文档」tab 中**。API 返回成功，群成员可以通过链接访问文档，但文档只显示在成员的「与我共享」里，不在群的云文档空间中。这是飞书平台的限制，drive API 只做权限管理，不做"文档归入群文档空间"的操作。**目前没有已知 API 能实现这一点。** 替代方案：在群聊中发送文档链接消息。

**⚠️ member_type 可选值（2026-05-08 实测）：**
`member_type` 不是随便填的，有效值为：`[email, openid, unionid, openchat, opendepartmentid, userid, groupid, wikispaceid, appid]`。传 `chat_id` 会返回 400 `field validation failed`。群聊必须用 `openchat`。

**已有表格手动共享：** 如果 onboard 脚本执行时权限未开通导致共享失败，可后续手动执行：
```python
import urllib.request, json, os
token_resp = json.loads(urllib.request.urlopen(
    urllib.request.Request(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        data=json.dumps({"app_id": os.environ["FEISHU_APP_ID"], "app_secret": os.environ["FEISHU_APP_SECRET"]}).encode(),
        headers={"Content-Type": "application/json"}
    ), timeout=30).read())
access_token = token_resp["tenant_access_token"]
req = urllib.request.Request(
    f"https://open.feishu.cn/open-apis/drive/v1/permissions/{BASE_TOKEN}/members?type=bitable",
    data=json.dumps({"member_type": "openid", "member_id": COACH_OPENID, "perm": "full_access"}).encode(),
    headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
    method="POST"
)
print(json.loads(urllib.request.urlopen(req, timeout=30).read()))
```
