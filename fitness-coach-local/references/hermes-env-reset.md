# Hermes 环境重置（格式化 ~/.hermes + 从 GitHub 恢复生产数据）

## 适用场景
- 需要清空 Hermes 本地状态，从 GitHub 仓库恢复生产数据
- 从云端生产环境切换到本地开发/测试环境

## 前提
- `gh` CLI 已登录且有仓库读取权限
- 已知生产数据仓库名称（默认 `weixudong808/fitness-coach--Hermes`）

## 步骤

### 1. 备份并创建空目录
```bash
mv ~/.hermes ~/.hermes.bak.$(date +%Y%m%d)
mkdir ~/.hermes
```

### 2. 恢复机器配置（API 密钥是本机的，不能从 GitHub 拉）
⚠️ macOS 坑：多个 cp 命令链式 `&&` 容易超时，**拆成单独命令执行**。
```bash
cp ~/.hermes.bak.XXXXXXXX/config.yaml ~/.hermes/config.yaml
cp ~/.hermes.bak.XXXXXXXX/.env ~/.hermes/.env
cp ~/.hermes.bak.XXXXXXXX/auth.json ~/.hermes/auth.json
```

### 3. 克隆生产数据
⚠️ 根据认证方式选择克隆方法：
- **SSH 密钥已配置** → `git clone git@github.com:weixudong808/fitness-coach--Hermes.git /tmp/fc-prod`
- **SSH 未配置但 `gh` CLI 已登录** → `gh repo clone weixudong808/fitness-coach--Hermes /tmp/fc-prod`（gh 用 HTTPS + token 认证，不依赖 SSH）
- **都没有** → `GIT_TERMINAL_PROMPT=0 git clone --depth 1 https://github.com/weixudong808/fitness-coach--Hermes.git /tmp/fc-prod`

用 `gh auth status` 确认 gh 是否已登录，用 `ssh -T git@github.com` 确认 SSH 是否可用。

### 4. 复制生产数据到 ~/.hermes
```bash
cp /tmp/fc-prod/SOUL.md ~/.hermes/SOUL.md
cp /tmp/fc-prod/group_map.json ~/.hermes/group_map.json
cp -r /tmp/fc-prod/members ~/.hermes/members
mkdir -p ~/.hermes/skills && cp -r /tmp/fc-prod/skills/fitness-coach ~/.hermes/skills/fitness-coach
cp -r /tmp/fc-prod/references ~/.hermes/references
cp -r /tmp/fc-prod/templates ~/.hermes/templates
```

### 5. 清理
```bash
rm -rf /tmp/fc-prod
```

### 6. 自愈机制说明
- `sessions/`、`state.db`、`cron/`、`memories/` **不恢复**（这些会通过 SOUL.md 自愈机制在首次对话时逐步重建）
- 首次对话 → SOUL.md 自动检测并重建"系统健康检查" cron job
- 健康检查 cron 凌晨运行时 → 检测会员 cron 丢失并自动恢复

## 本地环境适配（从云端切换到本地）

恢复后需要手动修改的配置：

| 文件 | 字段 | 说明 |
|------|------|------|
| `group_map.json` | `_config.coach_user_id` | 替换为本地飞书 user_id |
| `group_map.json` | `_config.coach_openid` | 替换为本地飞书 user_id |
| `group_map.json` | 各群的 `member_feishu_id` | 如果本地测试用户不同则需更新 |
| `config.yaml` | `approvals.mode` | 飞书 gateway 无法响应确认弹窗，本地需设为 `off` |
| `config.yaml` | `.env` / `auth.json` 中的 API key | 使用本地环境的密钥 |

## 本地开发环境的 Cron 行为（与健康检查/自愈相关）

**⚠️ `cronjob action=list` 查的是当前机器（本地 Mac）的 cron 状态，不是云端生产环境的。** 不能用本地 `cronjob list` 的结果推断云端状态。

### 本地健康检查 cron 的预期行为

| 组件 | 本地开发环境 | 云端生产环境 |
|------|-------------|-------------|
| 健康检查 cron 是否存在 | ✅ SOUL.md 自愈自动创建 | ✅ 同 |
| 凌晨 3 点是否执行 | 取决于电脑是否开机 | ✅ 服务器 24h 运行 |
| 会员 cron jobs 检查 | ❌ 本地无会员 cron → `has_issues=true`（误报） | ✅ 有真实 cron → 准确判断 |
| 飞书消息投递 | ❌ 凌晨电脑关机 → `last_delivery_error: DNS failed` | ✅ 有网 |
| GitHub 备份 | ❌ `/tmp/` 可能被清理 + 无网 | ✅ 有网 + SSH key |

### 关键区分：`last_delivery_error` 是本地问题

如果 `cronjob list` 显示 `last_status: error`，错误来自**当前机器**的执行，不是云端。本地凌晨没网（电脑关机）导致的 `DNS failed` 是预期行为，不代表云端有问题。

### 自愈系统的已知 gap

当前自愈设计（SOUL.md「系统自愈」章节）**只检查健康检查 cron 是否存在**（`check_health_cron_exists()`），**不检查上次执行是否成功**。即使 cron 存在但执行失败（如网络中断），下次对话也不会通知教练。

**教练期望的行为：** 健康检查失败后，下一次对话（不管是教练还是会员发的消息）的第一条回复应附上告警。这是一个待实现的设计改进。

## macOS 特殊坑
- `cp` 多文件链式 `&&` 容易超时，拆成单独命令
- 克隆方式取决于认证配置（见步骤 3），不要盲目选 `git clone`

## Git 操作挂起导致终端阻塞（2026-06-03 踩坑）

**⚠️ 中国大陆网络环境下，git clone/fetch/pull GitHub 私有仓库极易超时挂起（30-60 秒无响应）。一旦挂起，后续所有 terminal 命令都会被中断（exit code 130，SIGINT）。**

### 现象
- `git clone --depth 1 git@github.com:...` 超时后，后续 `echo hello`、`pwd` 等简单命令全部返回 `[Command interrupted] exit_code: 130`
- `execute_code`（Python）也被中断，无法作为备用方案
- 终端完全不可用，直到会话重启或进程被杀

### 规避策略
1. **首选 `gh repo clone`**（gh CLI 用 HTTPS + token，通常比 SSH 稳定）：`gh repo clone weixudong808/fitness-coach--Hermes /tmp/fc-prod`
2. **必须用 SSH 时，加超时保护**：`timeout 15 git clone --depth 1 git@github.com:weixudong808/fitness-coach--Hermes.git /tmp/fc-prod`（15 秒超时自动终止）
3. **避免 `--depth 1` 之后的 `git fetch`**（full fetch 大仓库更容易挂），用 shallow clone 尽量一步到位
4. **不要在同一个终端会话里连续尝试多种 git 协议**（SSH 挂 → HTTPS → API），每次失败都会增加阻塞风险
5. **如果已挂起**：无法在当前会话恢复，需等教练手动 `killall git` 或重启 Hermes 进程

### 网络诊断
- SSH 超时：`ssh -T git@github.com -o ConnectTimeout=10`
- HTTPS 超时：`curl -s --connect-timeout 10 https://api.github.com/repos/weixudong808/fitness-coach--Hermes`
- 如果都超时，放弃本次操作，建议教练切换网络或用代理后再试
