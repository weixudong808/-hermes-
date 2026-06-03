# MCP Fix Plan v3 — 问题 4 完整审计清单

> 创建时间：2026-05-18
> 来源：`~/.hermes/docs/mcp-fix-plan-v3.md` 问题 4 + 补充审计
> 目的：删除录入流程中所有 MCP write_* 调用，只保留凌晨 sync_to_sqlite.py 同步

---

## 审计方法

```bash
# 搜索所有 write_* 引用
grep -n "MCP.*写\|write_\|写本地\|本地.*SQLite.*写\|飞书写入完成后\|写完飞书\|写入本地" SKILL.md
grep -n "MCP.*写\|write_\|写本地\|本地.*SQLite.*写\|飞书写入完成后\|写完飞书\|写入本地" references/data-entry-paths.md
grep -rn "MCP.*写本地\|write_training\|write_exercises\|write_weight\|write_diet\|飞书写完后调 MCP" references/ | grep -v data-entry-paths
```

**关键教训：** fix plan v3 原始清单遗漏了 9 处（SKILL.md 3 处 + data-entry-paths.md 3 处 + references/ 3 个文件）。做架构级文档变更时，必须 grep 全目录，不能只看主文件。

---

## SKILL.md 改动清单（10 处）— ✅ 已完成（2026-05-18）

**grep 验证：** `grep -n "write_training\\|write_exercises\\|write_weight\\|write_diet\\|MCP.*写本地\\|写完飞书后调 MCP" SKILL.md` → 零匹配 ✅

**grep 验证：** `grep -n "write_training\\|write_exercises\\|write_weight\\|write_diet\\|MCP.*写本地\\|写完飞书后调 MCP" references/data-entry-paths.md` → 零匹配 ✅

**grep 验证：** `grep -n "双写\\|MCP.*写本地\\|写完飞书后调 MCP" references/mcp-server-plan.md` → 零匹配 ✅（write_* 工具定义行保留，因为仍是注册工具）

**实际执行备注：**
- 行 322-328 的 4 行删除改为合并为 1 行「写入训练/动作/体重/饮食记录 | lark-cli / record_diet.py 等 | 飞书为主路径」，比逐行删更简洁
- 行 457 改为「动作写入时通过飞书『关联课次』字段关联」，不再提 write_* 函数
- 行 752（参考文档索引 MCP Server 与本地数据库）保留不动，因为查询功能仍在

| 行号 | 当前内容 | 操作 | 实际操作 | 说明 |
|------|---------|------|---------|------|
| **317** | `**飞书写入由 lark-cli 负责（稳定），MCP 工具只负责写入本地 SQLite。**` | **改** | 改为「飞书写入由 lark-cli 负责，本地数据由凌晨 sync_to_sqlite.py 全量同步。」 |
| **322** | `写入训练课次（本地） \| mcp_fitness_data_write_training \| ...` | **删** | |
| **324** | `写入动作记录（本地） \| mcp_fitness_data_write_exercises \| ...` | **删** | |
| **326** | `写入体重记录（本地） \| mcp_fitness_data_write_weight \| ...` | **删** | |
| **328** | `写入饮食记录（本地） \| mcp_fitness_data_write_diet \| ...` | **删** | |
| **338** | `**MCP 写入工具的 member_id：** 使用 group_map.json 中的 member_id...` | **删** | ⚠️ 原始清单遗漏 |
| **350** | `├─ 是 → 调用 MCP 写入工具，流程结束` | **改** | ⚠️ 原始清单遗漏：改为 `├─ 是 → 继续 lark-cli 写入，流程结束` |
| **366** | `6. 写入成功后，再调用 MCP 写入工具` | **删** | ⚠️ 原始清单遗漏 |
| **399-409** | §3.1 Step 4 写课次后的 `MCP 写本地 SQLite` 子步骤 + 说明 | **删** | 整个子步骤 |
| **427-438** | §3.1 Step 6 写动作后的 `MCP 写本地 SQLite` 子步骤 + 说明 | **删** | 整个子步骤 |
| **457** | `传给 write_training(feishu_record_id=...) 和 write_exercises(session_feishu_record_id=...)` | **改** | 删除 write_* 部分，只保留「lark-cli 写课次 → 拿到 record_id → 传给动作记录的关联课次字段」 |
| **733** | `⚠️ Pitfall：修改 MCP write_* 工具行为时必须同时更新两处` | **删** | 不再适用 |

---

## data-entry-paths.md 改动清单（11 处）— ⬜ 待实施（Step 2）

| 行号 | 当前内容 | 操作 | 说明 |
|------|---------|------|------|
| **106-116** | Step 4 写课次的 MCP write_training 步骤 | **删** | |
| **136-149** | Step 6 写动作的 MCP write_exercises 步骤 + session_feishu_record_id 注意事项 | **删** | |
| **152** | `session_feishu_record_id` 不传的后果描述 | **删** | 问题不再存在 |
| **217-227** | 二、体重 Step 4 的 MCP write_weight 步骤 | **删** | |
| **336** | `飞书写完后调 MCP write_* 写本地 SQLite` | **改** | 改为「本地数据由凌晨 sync_to_sqlite.py 同步，无需手动写入」 |
| **337** | `**MCP 写入工具的 member_id**：...` | **删** | ⚠️ 原始清单遗漏 |
| **338** | `**MCP 写入工具的日期格式**：...` | **删** | ⚠️ 原始清单遗漏 |
| **340** | `写完飞书后调 mcp_fitness_data_write_diet 写本地` | **删** | |
| **348** | `如果 MCP 写入本地失败，不影响飞书数据，凌晨同步会兜底` | **改** | 改为「本地数据由凌晨同步更新，白天录入只写飞书」 |
| **350-382** | 已知限制 1 + 已知限制 2 + 影响链附录 | **整段删** | 问题均不再存在 |
| **388** | `如果本地通过 MCP 写入了飞书没有的数据...凌晨同步后会被删除` | **删** | ⚠️ 原始清单遗漏：不再有 MCP 写本地，此限制不存在 |

---

## 其他 references 文件改动（3 个文件，原始清单完全遗漏）

### references/mcp-server-plan.md（7 处）— ✅ 已完成（2026-05-18）

| 行号 | 当前内容 | 操作 | 实际操作 |
|------|---------|------|---------|
| 128-131 | 4 个 write_* 工具描述「双写」 | **改** | 改为「仅本地」，参数更新（加 feishu_record_id?，删 session_auto_id?） |
| 134-139 | §2.3 写入逻辑（双写）6 行描述 | **改** | 精简为「仅本地 SQLite」2 行（用途说明 + 直接写入） |
| 186-192 | §3.2 训练/体重写入路径 + write_exercises session 关联 | **改** | 写入路径改为「飞书唯一路径 + 凌晨同步」，删除 session 关联注意事项 |
| 10 | 进度表「双写验证通过」 | **改** | 改为「写入+查询验证通过」 |
| 201 | 测试记录「双写验证」 | **改** | 改为「本地 SQLite 写入验证」 |
| 234 | 设计原则「双写架构」 | **改** | 改为「飞书写入为主路径，本地 SQLite 供查询」 |

⚠️ 原始清单只列了 7 处，实际 grep 发现 3 处历史描述残留（进度表、测试记录、设计原则），一并清理。

### references/pitfalls-and-architecture.md（3 处）— ⬜ 待实施（Step 4）

| 行号 | 当前内容 | 操作 |
|------|---------|------|
| 488 | `架构：lark-cli 写飞书 → MCP write_* 只写本地 SQLite。MCP 不再负责飞书写入。` | 改为 `架构：lark-cli 写飞书，凌晨 sync_to_sqlite.py 同步到本地 SQLite。MCP write_* 工具保留但录入流程不再调用。` |
| 491-492 | 已知问题 1、2 描述 | 标注为「已废弃（2026-05-18 录入流程不再调 MCP write_*）」 |

### references/cron-configuration.md

无需改动（grep 确认无 write_* 引用）。

---

## 执行进度

| Step | 文件 | 改动数 | 状态 |
|------|------|--------|------|
| **Step 1** | `SKILL.md` | 10 | ✅ 已完成（2026-05-18） |
| **Step 2** | `references/data-entry-paths.md` | 11 | ✅ 已完成（2026-05-18） |
| **Step 3** | `references/mcp-server-plan.md` | 10 | ✅ 已完成（2026-05-18） |
| **Step 4** | `references/pitfalls-and-architecture.md` | 3 | ⬜ 待实施 |

### Step 3 完成记录（2026-05-18）

原始清单 7 处 + grep 发现 3 处历史残留 = 共 10 处改动，grep 验证零匹配（write_* 工具表行保留，因为是工具定义不是流程步骤；双写/MCP写本地/写完飞书后调 MCP 全部清除）：
1. 工具表 4 行 write_* 描述：双写→仅本地，参数更新
2. §2.3 写入逻辑：6 行双写→2 行仅本地
3. §3.2 fitness-coach skill：写入路径重写 + 删除 session 关联注意事项
4. 进度表「双写验证通过」→「写入+查询验证通过」
5. 测试记录「双写验证」→「本地 SQLite 写入验证」
6. 设计原则「双写架构」→「飞书写入为主路径，本地 SQLite 供查询」

### Step 2 完成记录（2026-05-18）

实际改动 11 处，grep 验证零匹配：
1. Step 4 write_training 步骤（含 local_id 保存说明）→ 删除
2. Step 6 write_exercises 步骤 + session_feishu_record_id 注意事项 → 删除
3. session_feishu_record_id 不传后果描述 → 随 Step 6 一起删除
4. 体重 Step 4 write_weight 步骤 → 删除
5. 通用注意事项第2条 → 改为"凌晨同步"
6. 通用注意事项第3条（MCP member_id）→ 删除
7. 通用注意事项第4条（MCP 日期格式）→ 删除
8. 通用注意事项第6条（write_diet）→ 删除
9. "MCP 写入本地失败兜底"说明 → 删除
10. 已知限制1 + 已知限制2 + 影响链 → 整段删除
11. 同步脚本设计段落 → 删除

注意事项编号重排：原 5→3, 6→4, 7→5, 8→6, 9→7, 10→8

### Step 3 执行备注（2026-05-18）

⚠️ 原始审计清单只列了 mcp-server-plan.md 7 处，但改完后 grep 发现 3 处历史描述残留（进度表「双写验证通过」、测试记录「双写验证」、设计原则「双写架构」），一并清理。教训：grep 验证范围要覆盖「双写」等同义词，不能只搜 write_* 函数名。

---

## 不受影响的部分

- `~/.hermes/mcp-server/server.py` — write_* 工具保留不删（以后可能用到，cron 智能化可能需要）
- `~/.hermes/mcp-server/sync_to_sqlite.py` — 凌晨同步完全不受影响
- MCP query_* 查询工具 — 只读本地，不受影响
- MCP sync_now — 手动同步，不受影响
- lark-cli 写飞书的流程 — 完全不变
