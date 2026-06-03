# MCP Server + 本地数据库 实施计划

> 2026-05-16 制定，小卫教练确认启动。进度追踪文档，跨 session 可用。

## 当前进度

| 阶段 | 状态 | 备注 |
|------|------|------|
| 阶段一：本地数据库搭建与首次同步 | ✅ 完成 | 8张表，14位会员，485条记录 |
| 阶段二：MCP Server 开发 | ✅ 完成 | 11个 tools，FastMCP+stdio，写入+查询验证通过 |
| 阶段三：Hermes 配置对接 | 🔄 进行中 | 3.1 ✅ 3.2 ✅ 3.3 待做 |
| 阶段四：测试 | 未开始 | |
| 阶段五：上线与运维 | 🔄 进行中 | 5.2 ✅ 代码已推 GitHub（commit 68269c0） |

## 阶段一：本地数据库搭建与首次数据同步

### 1.1 技术准备
- 数据库：SQLite（WAL 模式），`~/.hermes/data/fitness.db`
- Python 依赖：`sqlite3`（内置）、`mcp` SDK（已安装）
- 目录：`~/.hermes/data/`、`~/.hermes/mcp-server/`

### 1.2 Schema 设计（已实施）
- 实际 DDL 见下方「已实施 Schema」章节（与 bitable-table-schemas.md 的规划版有差异，以实际为准）
- 8 张表：members, training_sessions, exercise_records, diet_records, weight_records, cron_jobs, sync_log, sync_pending
- 外键约束已启用，UNIQUE 约束防重复（member_id + feishu_record_id）

#### 已实施 Schema（实际建表 DDL）

```sql
-- 注意：以下字段名与 bitable-table-schemas.md 规划版有差异
-- date/body_parts/notes/created_at 是实际使用的列名

CREATE TABLE training_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    member_id TEXT NOT NULL REFERENCES members(member_id),
    session_auto_id INTEGER,
    date TEXT,              -- YYYY-MM-DD
    body_parts TEXT,        -- JSON array: ["胸","上肢"]
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
    UNIQUE(member_id, feishu_record_id)
);

CREATE TABLE diet_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    member_id TEXT NOT NULL REFERENCES members(member_id),
    record_auto_id INTEGER,
    date TEXT,
    content TEXT,
    source_table TEXT,      -- "饮食记录表" or "健身饮食记录表"
    feishu_record_id TEXT,
    created_at TEXT,
    UNIQUE(member_id, feishu_record_id)
);

CREATE TABLE weight_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    member_id TEXT NOT NULL REFERENCES members(member_id),
    date TEXT,
    weight REAL,
    source_table TEXT,      -- "体重记录表" or "私教会员体重记录表"
    feishu_record_id TEXT,
    created_at TEXT,
    UNIQUE(member_id, feishu_record_id)
);
```

### 1.3 数据同步脚本 `~/.hermes/mcp-server/sync_to_sqlite.py`

**⚠️ 脚本不在 skill 目录下，在 `~/.hermes/mcp-server/` 目录。**

用法：
```bash
python3 ~/.hermes/mcp-server/sync_to_sqlite.py              # 全量同步所有会员
python3 ~/.hermes/mcp-server/sync_to_sqlite.py --member maomao  # 单会员
python3 ~/.hermes/mcp-server/sync_to_sqlite.py --dry-run    # 只拉取不写入
```

实现要点：
- 遍历 group_map.json，逐表调 `lark-cli base +record-list --format json --offset N --limit 200`
- lark-cli 返回格式：`data.data` 是值数组（按 field 位置索引），`data.fields` 是字段名数组，`data.record_id_list` 是记录 ID
- 自动分页：检查 `data.has_more`，每页间隔 0.3s 防限流
- **⚠️ 清空逻辑（2026-05-16 修复）：** `--member` 模式只清空该会员数据（`DELETE FROM ... WHERE member_id=?`），全量模式才清空所有。**之前的 bug 是 `--member` 也执行 `DELETE FROM` 无 WHERE 条件，导致 MCP 的 `maybe_auto_sync` 触发单会员同步时清空所有会员数据。**
- 表名分类函数 `classify_table()`：根据 group_map.json 的 table_ids key 名自动映射到本地表
- 记录 sync_log

**⚠️ maybe_auto_sync 的连锁风险：** MCP server 的查询工具在发现 >24h 未同步成功时会自动调 `sync_to_sqlite.py --member {id}`。如果同步失败（如 lark-cli 授权过期），旧代码会先清空全表再失败 → 所有会员数据丢失。此 bug 已修复，但 `maybe_auto_sync` 本身仍是个隐患——任何查询都可能触发同步。建议后续改为只增不减的增量同步，或把自动同步从查询路径中移除。

### 1.4 首次全量同步 ✅ 完成
- 2026-05-16 15:48 执行
- 14 位会员，0 错误
- 统计：训练课次 61、动作记录 283、饮食记录 120、体重记录 21 = **485 条**

## 阶段二：MCP Server 开发 ✅

### 2.1 项目初始化 ✅
- 目录：`~/.hermes/mcp-server/`
- 框架：Python + `mcp` 官方 SDK v1.27.0（`from mcp.server.fastmcp import FastMCP`）
- 传输：stdio（Hermes 标准方式）
- 入口：`server.py`（554 行）
- **环境变量（2026-05-22 可配置化）：** `FITNESS_DB_PATH`（默认 `~/.hermes/data/fitness.db`）、`FITNESS_GROUP_MAP_PATH`（默认 `~/.hermes/group_map.json`），支持其他 agent 复用

### 2.2 MCP Tools 定义（11 个，全部已实现并验证）

| 工具名 | 功能 | 输入参数 |
|--------|------|---------|
| `query_training` | 查询训练课次 | member_id, date_start?, date_end?, body_part? |
| `query_exercises` | 查询动作记录（LEFT JOIN 课次表获取日期） | member_id, date_start?, date_end?, exercise_name? |
| `query_diet` | 查询饮食记录 | member_id, date_start?, date_end? |
| `query_weight` | 查询体重记录（日期升序） | member_id, date_start?, date_end? |
| `get_member_profile` | 查询会员信息 | member_id |
| `get_summary` | 训练/饮食/体重摘要 | member_id, period(week/month/all) |
| `write_training` | 写入训练课次（仅本地） | member_id, date, body_parts[], notes?, feishu_record_id? |
| `write_exercises` | 写入动作记录（仅本地） | member_id, exercises[], session_feishu_record_id? |
| `write_diet` | 写入饮食记录（仅本地） | member_id, date, content |
| `write_weight` | 写入体重记录（仅本地） | member_id, date, weight, feishu_record_id? |
| `sync_now` | 手动触发同步（重试 pending + 全量同步） | member_id? |

### 2.3 写入逻辑（仅本地 SQLite） ✅
- **用途：** 保留供 cron 智能化等未来场景使用，当前录入流程不再调用
- **直接写入本地 SQLite**，不涉及飞书写入

### 2.4 查询逻辑 ✅
- **只读本地 SQLite**（快速，不依赖网络）
- **自动同步：** 查询前检查 sync_log，超过 24h 自动调 `sync_to_sqlite.py --member {id}`
- **同步失败不阻塞查询：** 返回本地数据 + 附注 sync_status 警告
- **query_exercises 使用 LEFT JOIN：** 关联 training_sessions 获取 session_date 和 body_parts

### 2.5 智能建议功能（低优先级，阶段二跳过）
- `analyze_weight_trend`：体重趋势分析
- `analyze_diet`：饮食分析（热量估算、营养均衡度）
- `generate_report`：周报/月报

### 2.6 架构关键点（阶段三集成时注意）

**Helper 函数封装（server.py 顶部）：**
- `get_member_info(member_id)` → 从 group_map.json 获取会员信息（bitable_token、table_ids 等）
- `find_feishu_table(member_id, local_type)` → 根据 LOCAL_TYPE_MAP 找飞书表名和 table_id
- `lark_upsert(bitable_token, table_id, fields, record_id?)` → 调 lark-cli 写入
- `add_sync_pending(conn, member_id, table_name, table_id, feishu_fields)` → 失败时写入待同步队列
- `maybe_auto_sync(conn, member_id)` → 查询前自动同步检查

**所有 tool 返回 str 类型（JSON 字符串）**，格式统一：
- 成功：`{"ok": true, "data": ...}` 或 `{"ok": true, "count": N, "data": [...]}`
- 失败：`{"ok": false, "error": "错误描述"}`

**验证结果（2026-05-16）：**
- 11 个 tools 注册成功
- query_training(maomao): ok=True, count=1
- query_weight(maomao): ok=True, count=1
- get_member_profile(maomao): ok=True, name=毛毛
- get_summary(maomao, week): sessions=0, diet=9

## 阶段三：Hermes 配置对接

### 3.1 注册 MCP Server ✅
```yaml
# config.yaml（实际使用绝对路径）
mcp_servers:
  fitness-data:
    command: python3
    args: [/root/.hermes/mcp-server/server.py]
```
- 重启 Hermes 后 11 个工具全部加载成功

### 3.2 更新 fitness-coach skill ✅
- 训练/体重记录写入：lark-cli 写飞书（唯一路径），凌晨同步更新本地
- 饮食记录写入：**保留 `record_diet.py`**（去重逻辑重要）
- 数据查询：MCP `query_*` 只读本地 SQLite
- 保留 lark-cli 作为降级方案（MCP 不可用时回退）
- **⚠️ select 字段自动补充仍需 lark-cli：** 训练主题和动作名称的下拉选项补充（3.0 节）仍需直接调 lark-cli `+field-list` / `+field-update`，MCP tools 不覆盖此逻辑

### 3.3 定时同步
- 在健康检查 cron 中加入同步调用
- 或单独建每小时同步的轻量 cron

### 3.5 本地 macOS 部署（2026-05-23 进行中）

**完整部署步骤：**
1. `mkdir -p ~/.hermes/data ~/.hermes/mcp-server`
2. 从 GitHub 克隆脚本：`git clone https://github.com/weixudong808/fitness-coach--Hermes.git /tmp/fc-prod && cp /tmp/fc-prod/mcp-server/*.py /tmp/fc-prod/mcp-server/README.md ~/.hermes/mcp-server/`
3. MCP SDK：Hermes-Agent venv 自带 `mcp` v1.27.0 ✅
4. **lark-cli 升级：** `sudo npm install -g @larksuite/cli@latest`（需要 ≥ 1.0.23）
5. **Hermes binding：** `HERMES_HOME=~/.hermes lark-cli config bind --source hermes --identity user-default`
6. **用户授权：** `HERMES_HOME=~/.hermes lark-cli auth login --recommend`（教练在浏览器中完成授权）
7. **同步数据：** `python3 ~/.hermes/mcp-server/sync_to_sqlite.py`（初始化本地 SQLite）

**⚠️ 当前阻塞：飞书文档级权限（2026-05-23）**
- lark-cli auth login 已完成，user 身份有 155 个 scope（含 `base:record:read`），但所有 Base API 调用仍报 403
- **根因：飞书两层权限模型——**
  - 第1层 API scope（应用级）✅：在飞书开放平台开通 `base:record:read` 等
  - 第2层 文档级权限（每个多维表格单独授权）❌：需要在飞书中把文档分享/授权给 Hermes 应用
- 云端能工作是因为表格是 Hermes 应用通过 `base:app:copy` 创建的，bot 天然有文档权限
- 本地测试企业里，用户手动创建的表格未授权给 Hermes 应用 → 403
- **解决方案 A：** 从云端服务器 SCP 数据库文件 `fitness.db`（最快）
- **解决方案 B：** 在飞书中把多维表格的协作者添加为 Hermes 应用
- 详见 `references/mcp-local-deployment.md`

**⚠️ lark-cli 版本兼容性**
- `sync_to_sqlite.py` 调 `lark-cli base +record-list --format json`，需要 lark-cli ≥ 1.0.23
- 旧版 v1.0.0 的 `+record-list` 不支持 `--format` 参数 → 必须升级
- 新版 lark-cli（1.0.39）检测到 Hermes 环境时要求先 `config bind`，否则报错拒绝操作
- `config bind` 流程：检测 `HERMES_HOME` 环境变量 → 绑定 app → 之后 `auth login --recommend` 授权用户
- `sudo npm install -g @larksuite/cli@latest` 需要电脑密码（macOS admin）

### 3.4 MCP Server 环境变量修复 ✅（2026-05-17）
**问题：** MCP Server 子进程只有 6 个环境变量（HOME/PATH/SHELL/USER/LANG/LOGNAME），缺少 `HERMES_HOME`。lark-cli 无法自动检测 workspace="hermes"，fallback 到根目录配置（defaultAs: "user"），导致所有飞书写入报 `need_user_authorization`。
**修复：** config.yaml 的 fitness-data 配置加了 `env: HERMES_HOME: /root/.hermes`。需重启 Hermes Agent 生效。
**根因分析：** lark-cli 的 `config bind --source hermes` 通过 `HERMES_HOME` 环境变量自动检测 workspace。详见 `references/pitfalls-and-architecture.md`。

## 阶段四：测试

### 4.1 单元测试
- [x] 同步脚本：飞书→SQLite 逐条字段一致性 ✅ 5会员（毛毛/萌姐/浩哥/倩倩/少莉姐）全部通过，覆盖新旧表名
- [x] MCP 写入：本地 SQLite 写入验证 ✅ 阶段二已通过 38 用例
- [ ] MCP 查询：与飞书对比（待做）
- [x] 边界：API 失败、网络超时、空数据 ✅ 阶段二已通过 38 用例

### 4.2 集成测试
- [ ] 会员群消息 → MCP 写入 → 查询验证
- [ ] 健康检查 → 同步 → 数据一致
- [ ] MCP 挂掉 → 降级到 lark-cli

### 4.3 灰度发布
- [ ] 先选 1 个会员（如毛毛）切换到 MCP
- [ ] 观察 1-2 天，稳定后全量

## 阶段五：上线与运维

### 5.1 全量切换
- 所有会员切换到 MCP 通道
- 监控 1 周

### 5.2 文档与备份 ✅（2026-05-22）
- ✅ MCP Server 代码推送到 GitHub（commit `68269c0`）：server.py、sync_to_sqlite.py、test_sync_consistency.py、README.md
- ✅ health_check.py 已更新，每日自动备份 MCP 源码（之前只备份 .db，现在包含 .py 文件）
- ✅ 代码路径可配置化：`FITNESS_DB_PATH`、`FITNESS_GROUP_MAP_PATH` 环境变量（有合理默认值）
- [ ] 更新 SKILL.md 数据操作流程
- [ ] 更新健康检查脚本，加入 MCP 存活检测

### 5.3 后续优化（低优先级）
- 飞书 Schema 变更时自动同步
- 数据异常自动告警
- 更多智能分析功能

## 设计决策与约束

1. 数据准确性 > 一切：宁可不给数据，也不能给错数据
2. 飞书是 source of truth：冲突时以飞书为准
3. 飞书写入为主路径，本地 SQLite 供查询（凌晨同步更新）
4. 降级方案必须存在：MCP 挂了不能影响现有功能
5. 脚本的 JSON 格式差异：lark-cli --json 传 flat 对象，Bot API 需 {"fields":{...}} 包裹（见 feishu-bitable skill）
