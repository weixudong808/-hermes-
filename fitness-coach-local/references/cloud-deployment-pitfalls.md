# 云端部署踩坑记录（阿里云 Linux 3）

> 2026-05-04 首次云端迁移实战总结
> 目标服务器：阿里云轻量应用服务器，60.205.204.63，2C4G，Alibaba Cloud Linux 3

## lark-cli 配置

- **`--as user` 需要两步：** `lark-cli auth login`（扫码授权）+ `lark-cli config default-as user`。缺第二步会导致 `+base-copy` 因 strict_mode=bot-only 失败。验证：`lark-cli auth status` 中 `defaultAs` 必须为 `user`
- **表名差异：** 正式企业模板表名可能是「健身饮食记录表」「私教会员体重记录表」（带前缀），跟测试环境不同。脚本按表名匹配无影响，但人工查表时注意

## session.py 补丁（群聊 Source 格式）

- **必须改：** 不改会导致已映射群每次都发问卷
- **⚠️ 绝对不要用 sed 改 Python 代码：** sed 会破坏多行缩进，导致 IndentationError，整个 gateway 无法启动
- **正确方式：** 用 Python 脚本修改，或从本地 scp 覆盖（但要确认版本一致）
- **版本风险：** `hermes update` 会覆盖补丁，需重新应用
- **一键修复脚本：** 见 `~/.hermes/plans/session-py-chatid-patch.md`
- **⚠️ 验证缩进不要肉眼看终端：** 终端复制粘贴会吃掉前导空格，`sed -n '103,112p'` 的输出看起来缩进没了但实际可能有。用以下方式验证：
  ```bash
  # 方式1：cat -A（空格原样显示，行尾显示 $）
  cat -A /path/to/session.py | sed -n '103,112p'
  # 方式2：Python repr（精确显示每行缩进空格数）
  python3 -c "
  with open('/path/to/session.py') as f:
      lines = f.readlines()
  for i in [103, 104, 105, 106, 107, 108]:
      n = len(lines[i]) - len(lines[i].lstrip())
      print(f'Line {i+1}: {n} spaces')
  "
  ```

## Hermes 版本

- 本地 v0.11.0 vs 云端 v0.12.0（2026-05-04），版本不同
- **不要 scp 源代码文件跨版本：** 可能不兼容。应 `git checkout` 恢复原版后重新打补丁
- 云端代码路径：`/usr/local/lib/hermes-agent/`
- 云端 venv 路径：`/usr/local/lib/hermes-agent/venv/`

## PATH 问题

- 云端 SSH 重连后 PATH 可能丢失，`hermes` 命令找不到
- 解决：`source ~/.bashrc` 或使用完整路径 `/usr/local/lib/hermes-agent/venv/bin/hermes`
- 建议在 `.bashrc` 中加：`export PATH="/usr/local/lib/hermes-agent/venv/bin:$PATH"`
- **本地 Mac 跑 `hermes gateway` 前台模式会占住终端：** scp/ssh 等命令必须在**新终端窗口**执行，不要在跑 gateway 的终端里操作（输入会被吞掉无反应）

## Gateway 运维

- **重启必须先 stop 再 restart：** 直接 restart 报 `Another gateway instance` 冲突
- **所有 gateway 命令带 `--system`：** 因为装成了 systemd 服务
- **查看日志：** `journalctl -u hermes-gateway -n 100 --no-pager`
- **.env 修改后需重启 gateway 才生效**

## 系统环境

- 系统 Python 是 3.6.8，不能用；Hermes 自带 venv 里是 3.11
- Node.js 用 dnf 装的 v20.20.2，在 `/usr/local/bin/`
- npm 全局包（lark-cli）在 `/usr/local/bin/`
- uv 在 `/root/.local/bin/`（不在默认 PATH 中）

## 环境变量（~/.hermes/.env）

部署必须配置的变量：

| 变量 | 值 | 说明 |
|------|-----|------|
| `FEISHU_ALLOW_ALL_USERS` | `true` | 允许会员消息不被拦截 |
| `LARK_CLI_PATH` | `/usr/local/bin/lark-cli` | 云端 lark-cli 路径 |
| `BITABLE_TEMPLATE_TOKEN` | `EMy6bp9iLagx7CsOlxgcf1uSnSb` | 正式企业模板 token |
