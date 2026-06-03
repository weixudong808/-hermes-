# MCP Server 本地 macOS 部署指南

> 2026-05-23 实测，适用于在本地 Mac 上部署 MCP Server 进行开发/测试。

## 前置条件

| 组件 | 最低版本 | 检查命令 |
|------|---------|---------|
| lark-cli | ≥ 1.0.23 | `lark-cli --version` |
| Python | 3.10+ | `python3 --version` |
| mcp SDK | 1.27.0 | Hermes-Agent venv 自带 |
| Node.js | 20+ | `node --version` |
| Hermes 绑定 | user-default | `HERMES_HOME=~/.hermes lark-cli config show` |

## 部署步骤

### 1. 创建目录结构

```bash
mkdir -p ~/.hermes/data ~/.hermes/mcp-server
```

### 2. 从 GitHub 克隆 MCP 脚本

```bash
git clone https://github.com/weixudong808/fitness-coach--Hermes.git /tmp/fc-prod
cp /tmp/fc-prod/mcp-server/server.py /tmp/fc-prod/mcp-server/sync_to_sqlite.py \
   /tmp/fc-prod/mcp-server/test_sync_consistency.py /tmp/fc-prod/mcp-server/README.md \
   ~/.hermes/mcp-server/
```

克隆后目录应有 4 个文件 + 后续的 fitness.db：
- `server.py`（554 行）— MCP Server
- `sync_to_sqlite.py`（447 行）— 飞书同步脚本
- `test_sync_consistency.py`（567 行）— 一致性测试
- `README.md` — 架构文档

### 3. 升级 lark-cli

```bash
sudo npm install -g @larksuite/cli@latest
```
需要输入 macOS 电脑密码。验证：`lark-cli --version` 应输出 ≥ 1.0.23。

**⚠️ 版本陷阱：** 旧版 v1.0.0 的 `base +record-list` 不支持 `--format json` 参数，`sync_to_sqlite.py` 会报 `unknown flag: --format`。

### 4. 绑定 Hermes Workspace

```bash
HERMES_HOME=~/.hermes lark-cli config bind --source hermes --identity user-default
```

新版 lark-cli 检测到 Hermes 环境后要求先绑定，否则拒绝所有操作。

**⚠️ `config init` 会被拒绝：** 在 Hermes 环境中，`config init` 报错 "config init is refused inside hermes context"，必须用 `config bind` 代替。

### 5. 用户授权登录

```bash
HERMES_HOME=~/.hermes lark-cli auth login --recommend
```

终端会打印一个飞书授权 URL，**教练需要复制到浏览器中打开并授权**。这条命令会阻塞等待用户完成授权。

授权完成后验证：
```bash
HERMES_HOME=~/.hermes lark-cli auth status
# 应显示 "tokenStatus": "valid", "identity": "user"
```

### 6. 同步数据初始化数据库

```bash
python3 ~/.hermes/mcp-server/sync_to_sqlite.py --dry-run   # 先预览
python3 ~/.hermes/mcp-server/sync_to_sqlite.py             # 正式同步
```

## 飞书两层权限模型（踩坑记录 2026-05-23）

### 问题现象

`lark-cli auth scopes` 显示 155 个权限（含 `base:record:read`），但 `base +record-list` 仍报 HTTP 403。

### 根因

飞书有**两层权限**：

1. **API Scope（应用级）**：在飞书开放平台开通，`auth scopes` 可查看。搜关键词 "记录" 或 "base:record"。
2. **文档级权限**：每个多维表格独立控制。即使应用有 API scope，如果表格没有授权给该应用，仍然 403。

### 为什么云端能工作

云端的多维表格是 Hermes 应用通过 `base:app:copy` 从模板创建的，**bot 是创建者，天然拥有文档权限**。本地测试企业中手动创建的表格没有这个优势。

### 解决方案

| 方案 | 操作 | 优缺点 |
|------|------|--------|
| A. SCP 数据库 | 从云端服务器 `scp root@xxx:~/.hermes/data/fitness.db ~/.hermes/data/` | 最快，但是快照 |
| B. 文档授权 | 在飞书中把多维表格的协作者添加为 Hermes 应用 | 完整但需逐表操作 |
| C. base:app:copy 重建 | 用 `onboard_member.py` 重新复制表格（Hermes 创建 = 天然有权限） | 最彻底但破坏现有数据 |

### 飞书开放平台权限名称注意

- **新版 Base API** 权限名是 `base:record:read`、`base:record:create` 等
- **旧版 Bitable API** 权限名是 `bitable:app`、`bitable:app:readonly` 等
- `sync_to_sqlite.py` 用的是新版 Base API（`base/v3/...`），需要 `base:record:*` 权限
- 在权限页搜索 "记录" 或 "base:record" 可以找到

## 验证部署成功

```bash
# 1. lark-cli 能拉数据
HERMES_HOME=~/.hermes lark-cli base +record-list --base-token <token> --table-id <id> --limit 2

# 2. 数据库有数据
python3 -c "import sqlite3; c=sqlite3.connect('$HOME/.hermes/data/fitness.db'); print(c.execute('SELECT count(*) FROM training_sessions').fetchone())"

# 3. MCP Server 能启动（手动测试）
HERMES_HOME=~/.hermes python3 ~/.hermes/mcp-server/server.py
# Ctrl+C 退出（stdio 模式会等待输入）
```

## 云端 vs 本地差异速查

| 维度 | 云端服务器 | 本地 macOS |
|------|-----------|-----------|
| lark-cli 版本 | 1.0.23+ | 需手动升级到 ≥ 1.0.23 |
| lark-cli 身份 | user（自动） | 需 `auth login` 手动授权 |
| Hermes binding | 自动（`HERMES_HOME` 已设） | 需 `config bind` |
| 数据库路径 | `/root/.hermes/data/fitness.db` | `~/.hermes/data/fitness.db` |
| 表格文档权限 | ✅（bot 创建的） | ❌ 需额外授权或 SCP |
