# Local MCP Server 环境搭建指南

> 2026-05-23 实测整理。从零在本地 macOS 部署 MCP Server 的完整步骤。

## 前提条件

- Hermes Agent 已安装
- 飞书 Hermes 应用已创建（`cli_a9789ef1a0b85cd5`）
- lark-cli ≥ 1.0.23（1.0.0 不支持 `--format json`、Hermes 绑定、user auth）
- `mcp` Python SDK ≥ 1.27.0

## Step 1: 升级 lark-cli

⚠️ **sudo npm install -g 和 nvm 有 PATH 冲突。** sudo 装到 root 目录，nvm 的 PATH 优先拿到旧版。

```bash
# 先装到用户目录
npm install -g @larksuite/cli@latest
# 此时新版在 ~/.npm-global/bin/lark-cli

# 再替换 nvm 目录下的旧版（需要 sudo）
sudo rm -rf ~/.nvm/versions/node/v20.20.0/lib/node_modules/@larksuite/cli
sudo cp -r ~/.npm-global/lib/node_modules/@larksuite/cli ~/.nvm/versions/node/v20.20.0/lib/node_modules/@larksuite/cli

# 清理 npmrc（sudo npm install -g 会写入 prefix 配置，与 nvm 冲突）
rm -f ~/.npmrc

# 验证
lark-cli --version  # 应该 ≥ 1.0.23
```

**⚠️ Pitfall — `~/.npmrc` 与 nvm 冲突（2026-05-23）：** `sudo npm install -g` 会自动在 `~/.npmrc` 写入 `prefix=/Users/.../.npm-global`，导致每次开终端报 "has a `globalconfig` and/or `prefix` setting, which are incompatible with nvm"。lark-cli 已 `cp` 到 nvm 路径下，`~/.npmrc` 不再需要，直接 `rm ~/.npmrc` 即可。

## Step 2: lark-cli 绑定 Hermes + 用户授权

```bash
# 绑定到 Hermes workspace（user-default 身份，需要写飞书表格）
HERMES_HOME=~/.hermes lark-cli config bind --source hermes --identity user-default

# 用户授权登录（会在终端打印授权 URL，需要用户在浏览器中打开完成授权）
HERMES_HOME=~/.hermes lark-cli auth login --recommend

# 验证
HERMES_HOME=~/.hermes lark-cli auth status
# 应显示 identity: user, tokenStatus: valid, userName: 卫
```

## Step 3: 飞书开放平台权限

打开 https://open.feishu.cn/app/cli_a9789ef1a0b85cd5/permission

必须开通的权限（新版 Base API，不是旧版 bitable）：
- `base:record:read` — 读取记录
- `base:record:create` — 新增记录
- `base:record:update` — 更新记录
- `base:record:delete` — 删除记录
- `base:app:read` — 读取多维表格应用
- `base:app:copy` — 复制多维表格（onboard_member.py 用）

⚠️ **注意：** 权限命名是 `base:record:*`（新版 Base API v3），不是旧版 `bitable:record:*`。
搜关键词"记录"或"base:record"即可找到。
测试企业通常不需要发布版本即可生效。

## Step 4: 部署 MCP Server 脚本

```bash
# 创建目录
mkdir -p ~/.hermes/mcp-server ~/.hermes/data

# 从 GitHub 克隆或直接复制脚本
# 脚本: server.py, sync_to_sqlite.py, test_sync_consistency.py, README.md
```

脚本位置: `~/.hermes/mcp-server/`
数据库位置: `~/.hermes/data/fitness.db`（SQLite WAL 模式）

**SQLite WAL 模式辅助文件：** `~/.hermes/data/` 下会自动生成 `fitness.db-wal`（预写日志）和 `fitness.db-shm`（共享内存索引）。这是 `server.py` 中 `PRAGMA journal_mode = WAL` 启用的，属于 SQLite 正常行为，不需要手动管理。WAL 模式的好处是读操作不被写操作阻塞，适合 MCP Server 一边写一边读的场景。

## Step 5: 注册 MCP Server 到 config.yaml

在 `~/.hermes/config.yaml` 的 `mcp_servers` 下添加：

```yaml
mcp_servers:
  fitness-data:
    command: python3
    args: ["/Users/quhongfei/.hermes/mcp-server/server.py"]
    env:
      HERMES_HOME: /Users/quhongfei/.hermes
```

⚠️ `HERMES_HOME` 环境变量必须设置，否则 lark-cli 子进程无法自动检测 workspace，飞书写入会报 `need_user_authorization`。

重启 Hermes Agent 后 MCP Server 会自动启动，首次启动时自动建表。

## Step 6: 验证

```bash
# 检查 MCP tools 是否加载
#（Hermes 重启后应该能看到 11 个 fitness-data tools）

# 测试 lark-cli 能访问 Hermes 自建的表格
HERMES_HOME=~/.hermes lark-cli base +record-list --base-token <bitable_token> --table-id <table_id> --limit 1
```

## 常见问题

### 403 "you don't have permission"

两层权限都要满足：
1. **应用权限**（API scope）— 飞书开放平台开通 `base:record:*`
2. **文档权限** — 多维表格必须授权给 Hermes 应用
   - Hermes 通过 `base:app:copy` 创建的表格天然有权限
   - 用户手动创建的表格需要单独分享给 Hermes 应用（文档级权限）

### lark-cli 1.0.0 报 "unknown flag: --format"

旧版不支持 `--format json`，必须升级到 ≥ 1.0.23。见 Step 1。

### MCP Server 启动后数据库为空

正常。`server.py` 的 `init_db()` 在模块加载时自动建表（`CREATE TABLE IF NOT EXISTS`），数据通过 `sync_to_sqlite.py` 从飞书同步。
新会员的表格由 `onboard_member.py` 创建后，同步脚本会自动拉取。

如果 `init_db()` 不存在（旧版 server.py），需要从云端生产数据库导出 schema：`sqlite3 ~/.hermes/data/fitness.db ".schema"`。**不要从代码反推 schema** — INSERT/SELECT 语句不含约束信息，会漏字段和约束。完整生产 schema 见 `references/mcp-server-maintenance.md`。

### 本地 sync_to_sqlite.py 的权限差异（2026-05-23 实测）

本地运行 `python3 ~/.hermes/mcp-server/sync_to_sqlite.py` 时，会出现**部分会员成功、部分 403** 的现象：

- ✅ **成功**：通过本地 `onboard_member.py`（`base:app:copy`）创建的表格 → Hermes 应用天然有文档级权限
- ❌ **403**：云端创建的表格 → 本地 lark-cli 的 user identity 没有这些表格的文档级权限

**这是预期行为**，不影响正常使用：
- 新会员建档流程会通过 `base:app:copy` 创建表格，自动有权限
- 历史数据（云创建的表格）只能通过云端服务器同步
- 如需本地也能同步历史数据，需要在飞书里逐个把 Hermes 应用加为对应表格的协作者

**建议先用 `--dry-run` 确认：** `python3 ~/.hermes/mcp-server/sync_to_sqlite.py --dry-run` 只拉取不写入，可以提前看到哪些会员能同步、哪些会 403。

### group_map.json 重复映射

删除会员映射时注意检查是否有多条重复（同一个 member_id 绑了多个 chat_id）。同时清理 `~/.hermes/members/{member_id}/` 目录。

### "lark-cli is not bound to hermes"

新版 lark-cli (≥1.0.23) 检测到 `HERMES_HOME` 环境变量后会要求绑定。
见 Step 2 运行 `config bind`。
