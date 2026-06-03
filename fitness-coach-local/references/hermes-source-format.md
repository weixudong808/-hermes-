# Hermes 飞书群聊 Source 格式问题

## 现象

飞书群聊中，模型无法从 Source 行获取 `oc_` 格式的 chat_id。

## 根因

Hermes 源码 `gateway/session.py` 第 94-113 行，`SessionSource.description` 属性：

```python
# 第 103-104 行
elif self.chat_type == "group":
    parts.append(f"group: {self.chat_name or self.chat_id}")
```

飞书群聊有 `chat_name`（群名），所以**永远显示群名，不会回退到 chat_id**。

实际注入给模型的 Source 行：`**Source:** Feishu (group: 测试测试)`
期望的 Source 行：`**Source:** Feishu (Group chat oc_986a5c2f547148eec1597cee9befafb6)`

## 影响范围

- 模型无法从 Source 行获取 chat_id 来匹配 group_map.json
- SOUL.md 中"从 Source 行的 chat_id 检查该群是否已映射"的指引无法执行
- Delivery options 的 origin 行也有同样问题（第 392 行 `chat_name or chat_id`）

## PII 安全说明

飞书不在 `_PII_SAFE_PLATFORMS` 中（只有 WHATSAPP/SIGNAL/TELEGRAM/BLUEBUBBLES），所以 `redact_pii` 对飞书始终为 `False`，走的是 `src.description` 而非 redaction 分支。不是 PII 隐藏导致的。

## 已实施的修复（2026-05-03）

**方案：改 session.py 第 103-106 行**（已在本地方案实施，云端迁移时需同步）

```python
# 修改前：
elif self.chat_type == "group":
    parts.append(f"group: {self.chat_name or self.chat_id}")

# 修改后：
elif self.chat_type == "group":
    if self.chat_name:
        parts.append(f"Group chat {self.chat_id} ({self.chat_name})")
    else:
        parts.append(f"Group chat {self.chat_id}")
```

修复后 Source 行：`**Source:** Feishu (Group chat oc_986a5c2f547148eec1597cee9befafb6 (测试测试))`

**⚠️ Delivery options 的 origin 行（第 392 行）仍有同样问题**（`chat_name or chat_id`），但 origin 主要用于消息投递回目标，不影响模型的 chat_id 获取能力，暂不改。

**云端迁移：** 需 scp 覆盖或手动改同一行。详见 `~/.hermes/plans/migration-plan-local-to-cloud.md` 步骤 1.5。

## 文件位置

- `gateway/session.py` — `SessionSource.description` 属性（第 94-113 行）← **已修改**
- `gateway/session.py` — `build_session_context_prompt()` 函数（第 230+ 行）
- `gateway/session.py` — `_PII_SAFE_PLATFORMS` 定义（第 194 行）
- `gateway/session.py` — Delivery options origin 行（第 392 行）← 未改，暂不影响
