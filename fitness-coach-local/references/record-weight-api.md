# record_weight.py API 参考

> 2026-05-21 重构，支持 4 种模式。单元测试文件同目录：`test_record_weight.py`。

## 命令格式

```bash
python3 record_weight.py <bitable_token> <table_id> <weight> [--date YYYY-MM-DD]
python3 record_weight.py <bitable_token> <table_id> --delete --date YYYY-MM-DD
python3 record_weight.py <bitable_token> <table_id> --delete --record-id recvXXX
python3 record_weight.py <bitable_token> <table_id> --query --date YYYY-MM-DD
python3 record_weight.py <bitable_token> <table_id> --trend [--days N]
```

## 输出格式

### 写入
```json
{"ok": true, "weight": 65.0, "date": "2026-05-19"}
```

### 删除
```json
{"ok": true, "deleted": ["recvAAA", "recvBBB"], "count": 2}
```

### 查询
```json
{"ok": true, "records": [{"weight": 65.0, "date": "2026-05-20", "record_id": "recvAAA"}], "count": 1}
```

### 趋势
```json
{"ok": true, "trend": "down", "change": -2.2, "start_weight": 70.0, "end_weight": 67.8, "data": [...]}
```
- `trend`: `"up"` / `"down"` / `"stable"` / `"insufficient_data"` / `"no_data"`
- `stable` 阈值：变化绝对值 < 0.3kg
- 默认 `--days 7`

## 设计规则

| 规则 | 说明 |
|------|------|
| 单位 | 只认公斤，不转换。斤由模型提示会员纠正 |
| 精度 | `round(weight, 1)` 保留一位小数 |
| 重复 | 同一天记两次不去重 |
| 身份 | 脚本不关心发送者身份 |
| 写入命令 | `+record-upsert`（创建新记录） |
| 删除命令 | `+record-delete --record-id XXX --yes` |
| 查询命令 | `+record-list` + filter |
| flat JSON | 不用 `{fields:{...}}` 嵌套 |
| 错误输出 | stderr JSON `{ok:false, error:"..."}` + exit ≠ 0 |

## 趋势数据中模型如何使用

模型拿到 `--trend` 返回的结构化 JSON 后，结合会员 profile（goal、style）生成个性化建议。趋势计算归脚本，话术生成归模型。

## 部署说明

### lark-cli 路径

脚本通过环境变量 `LARK_CLI_PATH` 查找 lark-cli，有默认值：

```python
LARK_CLI = os.environ.get("LARK_CLI_PATH", "/usr/local/bin/lark-cli")
```

| 环境 | lark-cli 位置 | 说明 |
|------|-------------|------|
| 云端（生产） | `/usr/local/bin/lark-cli` | 匹配默认值，无需配置 |
| 本地（开发） | `/Users/quhongfei/.nvm/versions/node/v20.20.0/bin/lark-cli` | ⚠️ 必须设置 `LARK_CLI_PATH` 环境变量，否则脚本报 `FileNotFoundError` |

**上传到云端不需要改任何配置**，默认值直接生效。

**⚠️ Pitfall — 本地调用必须设 LARK_CLI_PATH（2026-05-23 实踩）：** 脚本不通过 `PATH` 查找 lark-cli，直接读 `LARK_CLI_PATH` 环境变量（默认 `/usr/local/bin/lark-cli`）。本地开发时忘记设环境变量会导致 `FileNotFoundError`。**模型在本地调用 record_weight.py 时，必须写成：**

```bash
LARK_CLI_PATH=/Users/quhongfei/.nvm/versions/node/v20.20.0/bin/lark-cli \
  python3 ~/.hermes/skills/fitness-coach/scripts/record_weight.py \
  "{bitable_token}" "{table_id}" {weight}
```

**如果脚本报 `FileNotFoundError`，直接用 lark-cli 手动写入作为降级方案：**

```bash
HERMES_HOME=~/.hermes lark-cli base +record-upsert \
  --base-token "{bitable_token}" \
  --table-id "{table_id}" \
  --json '{"日期":{毫秒时间戳},"体重":{weight}}'
```

**⚠️ 注意毫秒时间戳计算：** 用 Python 计算避免手算错误：
```python
python3 -c "
from datetime import datetime, timezone, timedelta
tz8 = timezone(timedelta(hours=8))
ts = int(datetime(2026, 5, 23, tzinfo=tz8).timestamp() * 1000)
print(ts)
"
```

### lark-cli 与 Hermes 网关是独立凭证

lark-cli 的 `~/.lark-cli/config.json` 和 Hermes 网关的环境变量（`FEISHU_APP_ID` 等）是**两套独立的应用凭证**，互不干扰：

- **Hermes 网关**：用 `FEISHU_APP_ID` 环境变量配置，负责收发飞书消息
- **lark-cli**：用 `~/.lark-cli/config.json` 配置，负责操作多维表格 API
- 两者的 appId 可以不同，也能正常协作（网关收消息 → 模型处理 → 调用 lark-cli 写表格）

### 多设备 lark-cli

lark-cli 配置存储在**每台设备本地的** `~/.lark-cli/config.json`，不存在"挤掉另一台设备登录"的问题。云端和本地各有自己的配置文件，互不影响。

## 踩坑记录

### argparse 的 stderr 污染
argparse 参数校验失败时往 stderr 写纯文本 usage 信息，和脚本自身的 JSON 错误输出混在一起导致解析失败。**解决：** 扔掉 argparse，手动解析参数。

### 趋势模式日期 bug（2026-05-21 修复）
`cmd_trend` 中所有记录的 date 都被设成 `start_date`，而不是从 lark-cli 返回值解析实际日期。**解决：** 从 `fields["日期"]`（毫秒时间戳）用 `datetime.fromtimestamp(ts/1000, tz=CST)` 还原实际日期。

### 本地 lark-cli 不支持 `--filter`，query/trend 模式不可用（2026-05-21）

本地 lark-cli（appId=`cli_a961e26f03b85cb5`）的 `+record-list` 命令**不支持 `--filter` 标志**，导致 `--query` 和 `--trend` 模式在本地环境直接报错：

```
Error: unknown flag: --filter
```

**影响范围：**
- ✅ 写入（`--write`）、删除（`--delete --record-id`）模式正常（不需要 `--filter`）
- ❌ 查询（`--query`）、趋势（`--trend`）模式在本地完全不可用
- 删除（`--delete --date`）也不可用（内部依赖 `+record-list --filter`）

**额外权限问题：** 即使 `--filter` 被支持，本地 bot 身份还缺少 `base:record:read` 权限，读取操作会报 99991672 错误。需要在飞书开放平台为该 appId 开通权限并发布版本。

**云端不受影响：** 云端 lark-cli 的 `+record-list` 支持 `--filter`，且 bot 身份已有完整权限。

**临时替代方案（本地开发）：** 查询/趋势改用 MCP 工具（`mcp_fitness_data_query_*`）读本地 SQLite，不依赖 lark-cli。

### pytest 调用测试 CLI 脚本
测试中 patch `subprocess.run` 不够，还必须 patch `sys.argv`，否则脚本读到的是 pytest 的命令行参数。正确方式：
```python
with patch("sys.argv", [script_name, token, table_id] + extra_args):
    script.main()
```

### `except SystemExit` 吞掉 fail() 的退出码
`fail()` 调用 `sys.exit(1)`，如果 main() 里用 `try/except SystemExit: return` 会吞掉退出码，测试无法检测失败。**不要**在 main() 中 catch SystemExit。

## 运行测试

```bash
cd ~/.hermes/skills/fitness-coach/scripts
pytest test_record_weight.py -v
```

macOS 上 pytest 可能不在 PATH 中，用完整路径：
```bash
/Users/quhongfei/Library/Python/3.9/bin/pytest test_record_weight.py -v
```
