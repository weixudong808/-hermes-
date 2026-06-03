## 七、入群问卷回答处理

**⚠️ 重要架构说明：问卷发送逻辑已迁移至 SOUL.md（每次必加载）。** 原因：此 skill 的触发条件要求"群已映射"，但入群问卷需要"群未映射"时触发。如果问卷逻辑放在 skill 内会形成逻辑死循环——未映射群永远不会加载 skill，问卷永远发不出去。SOUL.md 每次对话必加载，不受此限制。

**当前流程：**
1. SOUL.md 检测到未映射群 → 发送问卷（教练发消息则不发问卷，直接问教练要会员信息）
2. 会员回复问卷后 → SOUL.md 指示加载本 skill → 执行下方流程

**注意：问卷内容在 SOUL.md 中维护，后续修改问卷需同步更新 SOUL.md 和本节。**

### 7.1 问卷回答处理

**会员回复问卷后，机器人执行以下步骤：**

1. **解析问卷内容** — 从会员的回复中提取各项信息
2. **如果信息不完整** — 提醒会员补充缺失项（如缺体重、缺吃饭时间等）
3. **⚠️ 检查是否已有该会员的档案** — `ls ~/.hermes/members/` 下是否存在同名 member_id 目录（member_id 通常为称呼的拼音/英文名）。
   - **如果已存在 → 还需比对 member_feishu_id**：读取已有 profile 关联的 group_map 条目中的 `member_feishu_id`，与当前回复者的 user_id 对比。
     - **feishu_id 匹配** → 同一人，跳过 `onboard_member.py`，直接在 group_map.json 中添加新 chat_id 条目（`member_id`、`bitable_token`、`table_ids` 从已有条目复制），style/goal 以原有 profile 为准。不要创建重复档案。详见 `references/pitfalls-and-architecture.md`「已有会员在新群回答问卷」。
     - **feishu_id 不匹配** → 不同人但同名（如两个会员都叫"静姐"），**作为新会员建档**。`onboard_member.py` 会生成不同的 member_id（带随机后缀），不会冲突。
   - **⚠️ 名字碰撞实际案例（2026-05-08）：** member_c981e1aa（"静姐"，feishu_id: b8ee19dg）和 member_b48131ea（"静姐"，feishu_id: 624d6782）是两个不同的人，各自有独立的 profile、bitable 和 cron jobs。
4. **信息完整且无已有档案 → 调用建档脚本（一键完成所有文件操作）：**

```bash
python3 ~/.hermes/skills/fitness-coach/scripts/onboard_member.py '{
  "name": "{称呼}",
  "chat_id": "{当前群的 oc_xxx chat_id}",
  "member_feishu_id": "{会员的 user_id}",
  "goal": "{增肌|减脂|塑形}",
  "style": "energetic",
  "meals": {"breakfast": "07:30", "lunch": "12:00", "dinner": "18:30"},
  "reminder_freq": "{每顿都提醒|只提醒午餐和晚餐|其他}",
  "report_enabled": true,
  "weight_reminder": "{none|daily|weekly}",
  "notes": "{特殊习惯或爱好}"
}'
```

**⚠️ 为什么用脚本而不是手动操作：** 之前让模型逐步执行（创建 profile → 复制表格 → 更新 group_map），模型经常漏掉 group_map.json 更新这一步。脚本将所有操作原子化，避免 LLM 步骤遗漏。

**脚本自动完成：**
- 创建 `~/.hermes/members/{member_id}/profile.json`（按 `templates/profile.json` schema）
- 创建 `~/.hermes/members/{member_id}/summaries/` 目录
- 从模板复制多维表格（`lark-cli base +base-copy --folder-token {folder_token}`），**直接创建到教练云盘「会员档案」文件夹**，带网络重试
- 获取新表格的 table_ids（`lark-cli base +table-list`），带复制中等待重试
- **自动把教练加为表格协作者**（`full_access`，通过 drive API `POST /drive/v1/permissions/{token}/members?type=bitable`），教练在「与我共享」中可直接查看，无需每次手动操作
- 更新 `group_map.json`（新条目含全部字段）
- **根据 meals/reminder_freq/weight_reminder 创建对应 cron job，job_id 写入 profile.json 的 cron_jobs 字段**（详见第十节）
- 返回 JSON 结果（包含 member_id、bitable_token、table_ids、cron_jobs）

**脚本返回 `{"ok": false, ...}` 时：** 将 error 信息告知教练，不要静默忽略。

### 7.1.0 飞书应用权限清单（Onboarding 必需）

Onboarding 涉及多个飞书 API 权限，缺任何一个都会导致部分步骤失败。**⚠️ 不要等一个个发现再让教练开，首次遇到权限问题时，一次性列出所有可能需要的权限。**

| 权限 scope | 用途 | 缺失时的表现 |
|-----------|------|------------|
| `bitable:app` | 应用身份直接访问多维表格（`base:app:copy` 的前置依赖） | `+base-copy` 报 `800004011 forbidden`，**即使 `base:app:copy` scope 已开通也会报** |
| `base:app:copy` | 从模板复制多维表格 | onboard_member.py 失败，error 含 `base:app:copy` |
| `base:table:read` | 列出新表格的子表（获取 table_ids） | `+table-list` 报 400 `Access denied` |
| `base:app:read` | 获取多维表格信息（URL 等） | `+base-get` 报 400 `Access denied` |
| `drive:permission` | 共享文档给教练和群聊 | drive API 返回 403，code `1063002` |

**一键申请链接（Hermes 应用 cli_a9789ef1a0b85cd5）：**
- `bitable:app`：https://open.feishu.cn/app/cli_a9789ef1a0b85cd5/auth?q=bitable:app&op_from=openapi&token_type=tenant（⚠️ `base:app:copy` 的前置依赖，优先开通）
- `base:app:copy`：https://open.feishu.cn/app/cli_a9789ef1a0b85cd5/auth?q=base:app:copy&op_from=openapi&token_type=tenant
- `base:table:read`：https://open.feishu.cn/app/cli_a9789ef1a0b85cd5/auth?q=base:table:read&op_from=openapi&token_type=tenant
- `base:app:read`：https://open.feishu.cn/app/cli_a9789ef1a0b85cd5/auth?q=base:app:read&op_from=openapi&token_type=tenant
- `drive:permission`：https://open.feishu.cn/app/cli_a9789ef1a0b85cd5/auth?q=drive:permission&op_from=openapi&token_type=tenant
- `space:document:delete`：https://open.feishu.cn/app/cli_a9789ef1a0b85cd5/auth?q=space:document:delete&op_from=openapi&token_type=tenant（删除多维表格用）
- `space:document:delete`（删除多维表格）：https://open.feishu.cn/app/cli_a9789ef1a0b85cd5/auth?q=space:document:delete&op_from=openapi&token_type=tenant

**⚠️ 权限发现级联（2026-05-19/23 踩坑）：** 教练通常一次只开一个权限，修好后你又发现下一个缺的，来回复 3-4 轮才搞定。**正确做法：首次遇到权限问题时，把上面所有权限的申请链接一次性发给教练，让他全部开通后再继续。**

**⚠️ `800004011 forbidden` 的排查顺序（2026-05-23 实战）：** 不要反复重试 `+base-copy`——如果第一次就报 forbidden，重试不会好。按此顺序排查：
1. `lark-cli auth status | grep bitable:app` → 没有则先开 `bitable:app` scope（最常见原因，是 `base:app:copy` 的前置依赖）
2. 检查开放平台 + 应用管理后台两处权限都已启用并**发布版本**
3. 检查模板表格协作者列表是否有 Hermes bot

**权限依赖顺序：**
1. 先开 `bitable:app` → 应用身份访问多维表格（`base:app:copy` 的前置依赖）
2. 再开 `base:app:copy` → 脚本/手动复制表格
3. 再开 `base:table:read` → 获取 table_ids
4. 再开 `drive:permission` → 共享给教练和群聊
5. `base:app:read` → 获取表格 URL（nice-to-have，不影响核心功能）

**⚠️ 模板多维表格的协作者要求（2026-05-22）：** lark-cli 已迁移到 Hermes 凭证（cli_a9789ef1a0b85cd5），`+base-copy` 现在以 Hermes 身份调用。模板表格（`TGixbmcoEaiZ43sfXvQcZ513nnf`）由旧应用创建，Hermes 需要被加为协作者（至少 `edit`）才能复制。如果 `+base-copy` 返回 `800004011 forbidden`，需教练手动把模板表格分享给 Hermes 应用。**新复制的多维表格归 Hermes 所有**，可通过 drive API `DELETE /drive/v1/files/{token}?type=bitable` 删除（需 `space:document:delete` scope）。

**⚠️ `drive:permission` 403 vs 飞书开放平台设置：** 即使在飞书开放平台开通了权限，如果机器人应用管理后台的「权限管理」页面没有实际启用对应权限，API 仍会返回 403。需确保两处都启用。

**⚠️ Pitfall — 不要重跑脚本（2026-05-23 踩坑）：** 如果脚本失败步骤是 `"table-list"`（即 `+base-copy` 成功了但 `+table-list` 报 `800004046 "is copying"`），**绝对不要重新运行脚本**。重新运行会触发第二次 `+base-copy`，飞书会返回 `800004011 forbidden`（上一次复制还在进行/已完成，重复复制被拒）。正确做法：手动执行后续步骤（见下方手动降级流程），不要重新触发复制。

**脚本失败时的手动降级流程：** 如果脚本因 lark-cli 未配置/权限不足/复制超时等原因失败，Agent 必须手动完成以下步骤（详见 `references/cloud-migration-env-vars.md`「Manual Onboard Fallback」）：
1. 用 `write_file` 创建 profile.json（按 templates/profile.json schema）
2. 用 `write_file` 更新 group_map.json（bitable_token/table_ids 标记为 PENDING）
3. 用 `cronjob` 工具逐个创建饮食/体重提醒
4. 再次 `write_file` 更新 profile.json 写入 cron job ID
5. **通知教练**：告知具体失败原因。权限问题→一次性列出所有权限申请链接；复制超时→等几分钟后手动补齐：`+table-list`（如果 base-copy 成功了但 table-list 超时，只需重试 table-list，**不要**再 base-copy）→ drive API 共享 → 更新 group_map.json

### 7.1.1 非标准问卷回答处理

问卷回答经常出现非预设选项，以下是已遇到的场景和处理方式：

| 场景 | 示例 | 处理方式 |
|------|------|---------|
| **选择两个风格** | "C和A"（温和关怀+活泼鼓励） | `style` 字段只能存一个值，默认选第一个提到的或更主动的（如 energetic）。将完整描述写入 `notes`，在 cron prompt 中体现融合风格 |
| **非标准体重提醒日** | "每周二早上8点20" | 问卷默认周一是 `0 9 * * 1`，但会员可指定任意星期。cron schedule 用 `0 HH * * N`（N=0周日,1周一,...,6周六），profile 中 `weight_reminder` 仍记 `"weekly"` |
| **自定义性格/幽默要求** | "像贾玲说相声一样" | 写入 `notes`，同时在所有 cron job prompt 的风格描述中追加此要求，确保定时消息也符合期望风格 |
| **体重提醒有具体时间** | "每周二早上8点20" | cron 的 minute 和 hour 要匹配具体时间（如 `20 8 * * 2`），不要用默认的 08:00 或 09:00 |

**原则：** 问卷预设是给会员降低填答成本的，实际回答优先级高于预设。会员的个性化要求（幽默风格、特定时间、混合风格）务必尊重并在 cron prompt 中体现，否则定时消息的风格会"打回原形"。

**可选传入字段：** `gender`、`age`、`height`（问卷不包含，教练后续补充时用）

5. **创建饮食/体重 cron job：**
   根据脚本的返回值（`meals`、`reminder_freq`、`weight_reminder`、`style`、`chat_id`），逐个创建 cron job。详见第十节（10.3 饮食提醒、10.4 体重提醒）。

   **判断逻辑：**
   - `reminder_freq="每顿都提醒"` → 检查 meals 中 ≠ "无" 的，每个都创建
   - `reminder_freq="只提醒午餐和晚餐"` → 只看 lunch 和 dinner
   - `reminder_freq="其他"` → 不创建，问教练具体要什么
   - **自由文本（如"早餐和午餐"）** → 根据文本语义判断创建哪些提醒，与 meals 字段交叉验证
   - `weight_reminder="daily"` → 创建每日 08:00 体重提醒
   - `weight_reminder="weekly"` → 创建每周一 09:00 体重提醒
   - `weight_reminder="none"` → 不创建

   **每个 cron 创建后：** 拿到 job_id → 写入 profile.json 的 `cron_jobs` 对应字段。

   **⚠️ 这一步只能由 Agent 完成**（脚本调不了 cronjob 工具）。两步接力：脚本建文件（第一步）→ Agent 建 cron（第二步）。

6. **提醒教练发送群公告：**
   建档完成后，在回复教练的确认消息末尾追加提醒："> 📌 小卫教练，记得给这个群发一下群公告哦~"
   
   群公告由教练手动发送（一键转发），不通过脚本或 agent 自动发送。原因：
   - 群公告可能包含图片，自动发送处理图片较复杂且增加脚本耗时
   - 教练转发前可以微调内容，更灵活
   - 公告内容更新时无需改任何代码

7. **回复会员确认：**
   > "收到！已为你建好专属档案 💪
   > - 目标：{goal}
   > - 饮食提醒：{reminder_freq}（{已创建的提醒列表}）
   > - 体重提醒：{weight_reminder 描述}
   > - 训练报告：{report_enabled ? '已开启' : '已关闭'}
   >
   > 📋 你的专属健身档案：{bitable_url}
   >
   > 以后有什么问题随时@我~"

   **⚠️ bitable_url 生成规则：** 脚本返回的 JSON 中包含 `bitable_url` 字段，直接使用即可。格式为 `https://pcn66xx6g0i0.feishu.cn/base/{bitable_token}`。**必须在确认消息中包含此链接，不要漏发。**

   **⚠️ 链接格式与文档卡片渲染（2026-05-08 实测验证）：**
   飞书对群聊消息中的链接有以下渲染规则（直接影响是否自动出现在群「云文档」tab）：
   - ✅ 裸 URL（`https://xxx.feishu.cn/base/xxx`）→ 渲染为文档卡片 → **自动出现在群「云文档」tab**
   - ✅ `[URL](URL)` 格式（如 `[https://xxx](https://xxx)`）→ 飞书 URL 识别优先于 markdown 解析，同样渲染为文档卡片 → **自动出现在群「云文档」tab**
   - ❌ `[自定义文字](URL)` 格式（如 `[点击查看](url)`、`[你的专属健身档案](url)`）→ 渲染为普通文字链接 → **不会**出现在群「云文档」tab

   **结论：** 确保链接的显示文本部分是合法 URL（或直接用裸 URL），不要用自定义文字作为 markdown 链接文本。

   **⚠️ 已知限制（2026-05-08）：** 脚本通过 drive API 共享文档给群聊（`member_type: "openchat"`），API 返回成功但单独此操作**文档不会出现在群的「云文档」tab 中**。这是飞书平台限制——drive permissions API 只做权限管理，不会把文档"归入"群的文档空间。**解决方案：** 在群聊中发送 bitable_url 消息，飞书识别到文档卡片后会自动为该群生成对应的「云文档」系统标签页。两个动作配合：drive API 给权限 + 群聊发链接触发云文档 tab。

7. **云盘文件夹：** 脚本已自动将多维表格创建到教练云盘「会员档案」文件夹（`COACH_FOLDER_TOKEN`），无需额外操作。教练在云盘中可直接查看和管理所有会员档案。

### 7.1.5 模板多维表格状态（已更新）

**✅ 已修复（2026-05-04）：** 模板多维表格（`TGixbmcoEaiZ43sfXvQcZ513nnf`）现在包含完整的 4 张表：

| 表名 | table_id |
|------|---------|
| 训练课次表 | tbl8qEBvezIs7FVx |
| 动作记录表 | tblV7N2yDAFhde5U |
| 健身饮食记录表 | tbljQcZmP13t4TXz |
| 私教会员体重记录表 | tblGNqXBGNvYrjko |

新会员建群时 `+base-copy` 会自动获得完整 4 张表，无需手动补建。

### 7.2 group_map.json 新条目格式

```json
{
  "{chat_id}": {
    "member_id": "{member_id}",
    "member_name": "{称呼}",
    "member_feishu_id": "{ou_xxxxx}",
    "coach_user_id": "{教练的 user_id}",
    "bitable_token": "{从模板复制后的新 token}",
    "table_ids": {
      "训练课次表": "{新 table_id}",
      "动作记录表": "{新 table_id}",
      "饮食记录表": "{新 table_id}",
      "体重记录表": "{新 table_id}"
    },
    "style": "energetic",
    "report_enabled": true,
    "weight_reminder": "none",
    "reminder_freq": "每顿都提醒",
    "auto_record": true,
    "created_at": "2026-05-03T12:00:00"
  }
}
```

**profile.json 不存体重数据**（weight/target_weight/start_weight/target_date 均已移除），体重统一在多维表格"体重记录表"中记录。`allergies` 字段已移除，过敏信息写入 `notes`。

> 📋 **标准 schema 见 [templates/profile.json](templates/profile.json)**，新会员建档时以此为准。

**style 字段映射：**
- A → `energetic`（默认）
- B → `professional`
- C → `gentle`
- D → `strict`

### 7.3 教练跳过问卷

如果教练在未映射群里直接发了训练计划或会员信息（跳过问卷），按原流程处理：
1. 从消息中提取会员信息
2. 如果教练没明确说会员是谁 → **问一句**
3. 如果教练说了 → 调用 `onboard_member.py` 脚本（问卷未填的字段用默认值，chat_id 从 Source 行获取，member_feishu_id 从消息上下文获取或问教练）

**⚠️ 教练提供文件路径时直接读取：** 如果教练直接给了 profile.json 或其他配置文件的路径（如"读取这个文件，这是这个群的配置"），**立即 read_file 读取该文件**，不要再反复问会员姓名、飞书ID等已经可以从文件中获取的信息。教练给路径 = 信息已在文件里，问一遍就够了。

**⚠️ group_map.json 外部修改竞态：** group_map.json 可能被其他 Hermes session 或外部进程在对话中途修改。如果第一次读取时群未映射，但教练后续提供了 profile 路径或暗示群已配置，重新读取 group_map.json 确认最新状态，避免基于过期数据重复操作。

### 7.4 多 chat_id 映射同一会员

同一个会员可能有多个 chat_id（如：群聊 + 私聊），在 group_map.json 中是两条独立记录，指向同一个 `bitable_token` 和 `member_id`。这是正常设计——Hermes 为每个 chat_id 分配独立 session，但数据统一写入同一个多维表格。

### 7.5 会员移除（Offboarding）

**触发：** 教练明确要求删除某个会员的所有信息。

**执行顺序（不可遗漏）：**

1. **列出并删除所有 cron job** — `cronjob action=list`，筛选该会员相关的 job（名称含会员名），逐个 `cronjob action=remove`
2. **删除 group_map.json 中的条目** — 用 patch 移除对应 chat_id 的整个 JSON 块（注意：同一会员可能有多个 chat_id 条目，全部删除）
3. **删除 member 目录** — `rm -rf ~/.hermes/members/{member_id}`
4. **删除多维表格（如教练要求）** — 见下方

**多维表格删除：**
- lark-cli 没有 `+base-delete` 命令，需调用飞书 Drive API：`DELETE /drive/v1/files/{bitable_token}?type=bitable`
- **需要权限：** `space:document:delete` 或 `drive:drive`（Hermes 应用 cli_a9789ef1a0b85cd5 默认未开通）
- 如果权限不足，给教练申请链接后由教练在飞书开放平台开通；或让教练在飞书云盘中手动右键删除
- ⚠️ `DELETE /bitable/v1/apps/{token}` 返回 404，**不是正确的删除接口**，必须用 drive API

---
