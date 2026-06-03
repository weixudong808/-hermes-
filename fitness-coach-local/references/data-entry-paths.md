# 数据录入路径（端到端 Checklist）

每种数据一条完整的 step-by-step 流程，命中后按表走，不要漏步。

---

## 一、训练计划录入路径

**触发条件：** 消息包含动作名 + 数值（组数/次数/重量至少一个），教练和会员均可触发
**写入权限：** 教练和会员发送的训练数据均可记录
|--------|---------|---------|
| 教练 | 无 | 直接写入，跳过 Step 0 |
| 会员 | 不需要 @机器人，包含训练数据即可 | 确认式写入，先执行 Step 0 |

**⚠️ 脚本封装：** 训练录入有专属脚本 `record_training.py`，将 Step 3~6（Select 选项检查 + 写课次 + 写动作）封装为 1 次 CLI 调用。Step 0~2 仍由 AI 助手处理（意图判断、数据解析、主题推断）。脚本 API 详见 `references/record-training-api.md`。

```bash
# 完整写入示例
python3 ~/.hermes/skills/fitness-coach/scripts/record_training.py \
  "{bitable_token}" "{table_ids.训练课次表}" "{table_ids.动作记录表}" \
  "{member_name}" "{YYYY-MM-DD}" "{theme}" \
  '[{"name":"卧推","weight":100,"sets":4,"reps":12},{"name":"夹胸","weight":30,"sets":3,"reps":15}]' \
  [--coach-notes "备注"]
```

**写入范围限制（会员专属）：**
- ✅ 可写入：训练课次表、动作记录表
- ❌ 不可写入：教练备注栏（留空）
- ❌ 不可操作：修改/删除已有记录
- 群隔离天然保证会员只能写入自己的表格（chat_id → bitable_token 映射）

### Step 0 — 确认式写入（仅会员触发时执行）

> **教练发送的消息跳过此步骤，直接进入 Step 1。**

**目的：** 防止闲聊被误录入，确保数据准确性。

**0.1 判断会员是否有明确记录意图：**

检查消息中是否包含以下关键词（至少一个）：
- "帮我记录"/"帮我记"/"记录一下"/"录入"/"打卡"/"记一下"/"写入"

**有明确记录意图 → 直接进入 Step 1，正常解析写入。**
**无明确记录意图（仅有训练数据描述，如"今天跑了5公里好累"） → 进入 0.2。**

**0.2 展示识别结果 + 反问会员：**

回复格式（按会员风格适配语气）：
```
{鼓励/肯定}
我识别到以下内容：
- {运动类型}：{数据摘要}
需要帮你记录到训练表里吗？
```

**会员确认（"记一下""嗯""好的""要"等） → 回到 Step 1 执行写入。**
**会员否认（"不用""算了"等） → 结束流程，不写入。**

**0.3 截图场景（会员发跑步机/运动手表截图）：**

1. 用 `mcp_zai_vision_mcp_analyze_image` 识别截图
   - prompt：`"这是一张运动设备/跑步机截图，请提取所有可见的运动数据，包括：距离、时长、卡路里/消耗、心率（平均/最大）、配速、坡度、步数等。无法确认的数据标注为'不确定'"`
2. 将识别结果展示给会员，**不确定的数据标注 ⚠️**
3. 如果会员同时发了文字描述，文字信息优先（更准确），截图作为补充
4. 进入 Step 1 正常写入

**⚠️ Vision 也会误判运动类型（2026-05-14 实测）：** Vision 可能把动感单车识别为跑步、把椭圆机识别为其他设备等。**运动类型（跑步/骑车/椭圆机等）和数值数据一样需要让会员确认**，不要只展示数字而默认运动类型正确。展示格式应包含运动类型 + 所有数据："跑步 8.97公里 30分09秒"，让会员整体确认。

### Step 1 — 提取基本信息

- [ ] 从 group_map.json 获取：`member_id`、`bitable_token`、`table_ids.训练课次表`、`table_ids.动作记录表`、`member_name`
- [ ] 从消息中提取日期（默认今天，支持"昨天"/"X月X日"/"2026.5.4"等格式），转为 `YYYY-MM-DD` 格式
- [ ] 从消息中提取训练主题（教练明确写了就用，否则按动作自动推断，不确定写"待确认"）

### Step 2 — 解析动作列表

- [ ] 按行/逗号/顿号拆分为多个动作
- [ ] 每个动作提取：动作名称、重量(kg)、组数、次数
- [ ] 匹配规则：忽略"杠铃/哑铃"前缀，支持多种格式变体（见 SKILL.md §2.1）
- [ ] 自重动作清单：引体向上、平板支撑、双杠臂屈伸、俯卧撑、仰卧起坐、卷腹、悬垂举腿

**缺失字段处理（按发送者区分）：**

| 缺失字段 | 教练录入 | 会员录入 |
|---------|---------|---------|
| 未提组数 | 默认 1 组，回复中**告知教练** | **问会员确认**，不自行补默认值 |
| 重量为 0 或未提 | 自重动作 → 备注"自重" | 自重动作 → 备注"自重"；非自重 → **问会员确认** |
| 训练主题 | 自动推断，不确定写"待确认"并告知教练 | 自动推断，不问会员 |
| 动作名称别名 | 匹配后告知教练 | 匹配后**告知会员**（如"平板撑已对应平板支撑，如需改动请告诉我"） |

### Step 3~6 — 脚本写入（一步完成）

**⚠️ 使用 `record_training.py` 脚本替代手动调用 lark-cli（2026-05-24 起生效）。** 脚本封装了 Select 选项检查、课次写入、动作写入的全部逻辑。

```bash
python3 ~/.hermes/skills/fitness-coach/scripts/record_training.py \
  "{bitable_token}" "{table_ids.训练课次表}" "{table_ids.动作记录表}" \
  "{member_name}" "{date}" "{theme}" \
  '<exercises_json>' [--coach-notes "备注"]
```

**AI 助手负责的准备工作（调用脚本前）：**
- [ ] 解析动作列表为 JSON 数组（见 Step 2）
- [ ] 推断训练主题（如有多个用 `+` 连接的，拆分为数组或让教练指定）
- [ ] 处理动作名称别名（如"平板撑"→"平板支撑"）
- [ ] 时间类动作：次数填 1，时间写入 notes
- [ ] 重量区间：先问教练确认填哪个值

**脚本自动处理：**
- Select 选项检查与补充（训练主题 + 动作名称）
- 未来日期拦截
- coach-notes 空时不传字段
- 单个动作写入失败不阻断其余动作
- 返回 session_id 和每个动作的 record_id

**脚本也支持删除和查询（详见 `references/record-training-api.md`）：**
```bash
# 删除课次（级联删除关联动作）
python3 record_training.py ... --delete --session-id recvXXX
# 删除单个动作
python3 record_training.py ... --delete-exercise --record-id recvXXX
# 查询课次的动作列表
python3 record_training.py ... --query --session-id recvXXX
```


### Step 7 — 确认回复

**回复对象区分：**

| 维度 | 教练录入 | 会员录入 |
|------|---------|---------|
| 回复风格 | 风格适配（按对应会员 profile.style） | 同左 |
| 回复内容 | 写了几个动作、训练主题、日期；缺失字段告知教练 | 写了几个动作、训练主题、日期；缺失字段已在 Step 0/2 确认过，不再重复 |
| 失败通知 | 告知教练，附错误信息 | 告知教练，附错误信息（会员侧不暴露技术细节，按风格说"记录遇到了一点问题，已经告诉小卫教练了"） |

### 特殊情况处理

| 情况 | 教练录入 | 会员录入 |
|------|---------|---------|
| 时间类动作（平板撑等，次数位是"1分钟"/"30秒"） | 问教练确认记录方式 | **次数填 1，时间写入「备注」**（如"1分钟×3组"），不问会员 |
| 重量区间（如 6.81-13公斤） | 问教练填最大值/最小值/平均值 | **问会员确认**填哪个值 |
| 一条消息超过 10 个动作 | 正常写入，提醒"动作较多，已全部记录" | 同左 |
| 不完整的计划（只有动作名没数字） | 问："这个动作的组数/次数/重量是多少？" | 问会员补充数据 |
| 消息模糊不确定是否为训练计划 | 问一句"这是训练计划吗？" | **确认式写入**：展示识别结果 → 问会员是否需要记录（见 Step 0） |
| 截图无法识别 | 不适用（教练通常发文字） | 告知截图看不清，请用文字描述 |

---

## 二、体重记录录入路径

**触发条件：** 发送者是会员 + 消息包含"体重"关键词 + 包含数字

**⚠️ 单位统一公斤：** 脚本只认公斤，不做斤→kg转换。如果会员发了斤数，提示会员自行纠正，走删除+重录流程。

### Step 1 — 提取体重数值

- [ ] 从消息中提取数字（支持"75.5kg"/"75.5"/"七十五点五"等格式）
- [ ] 提取失败（无有效数字）→ 不触发记录，按风格提醒会员补充："你说的是体重多少呀~ 记得带上数字哦"

### Step 2 — 判断是否为历史体重

- [ ] 消息中是否包含历史日期（"昨天"/"上周一"/具体日期）？
  - 否 → 用今天日期
  - 是 → 转为对应日期的毫秒时间戳

### Step 3 — 边界检查

| 情况 | 处理 |
|------|------|
| 未来日期的体重 | 拒绝："还没到呢，到了那天再记吧" |
| 同一天已记录过 | 正常写入新记录，告知："今天已有一条记录了，新记录已添加，如有误可以让教练帮忙清理" |

### Step 4 — 写入体重记录表

**record_weight.py 支持四种模式：写入、删除、查询、趋势。** 完整 API 见 `references/record-weight-api.md`。

```bash
# 写入当天体重（自动 round 到一位小数）
python3 ~/.hermes/skills/fitness-coach/scripts/record_weight.py \
  "{bitable_token}" "{table_ids.体重记录表}" {体重kg}

# 写入指定日期
python3 ~/.hermes/skills/fitness-coach/scripts/record_weight.py \
  "{bitable_token}" "{table_ids.体重记录表}" {体重kg} --date 2026-05-19

# 按日期删除
python3 ~/.hermes/skills/fitness-coach/scripts/record_weight.py \
  "{bitable_token}" "{table_ids.体重记录表}" --delete --date 2026-05-20

# 按 record_id 删除
python3 ~/.hermes/skills/fitness-coach/scripts/record_weight.py \
  "{bitable_token}" "{table_ids.体重记录表}" --delete --record-id recvXXX

# 查询某天体重
python3 ~/.hermes/skills/fitness-coach/scripts/record_weight.py \
  "{bitable_token}" "{table_ids.体重记录表}" --query --date 2026-05-20

# 查看趋势（默认7天）
python3 ~/.hermes/skills/fitness-coach/scripts/record_weight.py \
  "{bitable_token}" "{table_ids.体重记录表}" --trend --days 7
```

**脚本返回值（stdout JSON）：**

| 模式 | 关键字段 |
|------|---------|
| 写入 | `{"ok":true, "weight":65.0, "date":"2026-05-19"}` |
| 删除 | `{"ok":true, "deleted":["recvAAA"], "count":1}` |
| 查询 | `{"ok":true, "records":[{weight,date,record_id}], "count":N}` |
| 趋势 | `{"ok":true, "trend":"down/up/stable/no_data/insufficient_data", "change":-2.2, "start_weight":70.0, "end_weight":67.8}` |

**趋势判定规则：** `|change| < 0.3kg` → stable，否则看正负。

- [ ] 体重表字段名通常是 `体重` + `日期`，但不同会员可能不同
- [ ] 写入失败 → 用 `+field-list` 查看实际字段名，调整后重试

### Step 5 — 确认回复

- [ ] 按会员风格回复："已记录！体重{N}kg，继续保持~"
- [ ] 如果是历史补记，注明日期："已补记 {日期} 的体重 {N}kg"

### ⚠️ 字段名踩坑

- 字段名是 `"体重"`（不是 `"体重kg"`，后者会报 800030201 not_found）
- 字段名是 `"日期"`（不是其他变体）
- 不同会员的表格字段名可能略有不同，写入失败时用 `+field-list` 确认

---

## 三、饮食记录录入路径

**触发条件：** 发送者是会员，满足以下任一条件：
- 发送图片 + 明确要求记录饮食（如"帮我记录早餐/午餐/晚餐"）→ 走 Step 1（图片路径）
- 发送文字描述的饮食内容（如"午餐：米饭半碗，鸡块一小份"）→ 跳过 Step 1-2，直接从 Step 3 开始

### Step 1 — 获取图片路径（仅图片记录时执行）

- [ ] 从消息中提取图片缓存路径（通常为 `/root/.hermes/cache/images/img_xxx.jpg`）

### Step 2 — 识别食物内容（仅图片记录时执行）

1. 优先：`mcp_zai_vision_mcp_analyze_image`（prompt 见 SKILL.md 饮食记录流程）
2. 都失败 → 回复会员：\n3. **⚠️ 识别结果不要添加克数估算**，只用相对分量描述（如"约一小碗""一份""几块"）

**⚠️ Vision 识别准确率低（2026-05-13 踩坑）：** Vision AI 经常把食物认错（山药→香肠、黄瓜→肉肠、卤牛肉→"撕碎的肉类"）。**图片识别后必须先展示给会员确认，会员确认后再写入，不要先写入再问。** 先写入会导致反复 delete→rewrite 的尴尬循环，会员体验很差。

**正确的图片识别流程：**
1. Vision 识别 → 列出识别到的食物清单
2. 回复会员展示清单，问"你看我识别的对吗？有什么需要改的？"
3. 会员确认/修正后 → 再调用 record_diet.py 写入
4. 如果会员逐条纠正（如"不是香肠，是山药"），每次纠正后不要立即重写，等会员说"对了"/"没问题"后再统一写入
3. **⚠️ 识别结果不要添加克数估算**，只用相对分量描述（如"约一小碗""一份""几块"）

### Step 3 — 推断餐次 + 提取食物描述

**图片记录：** 根据当前时间推断餐次（6-10 点早餐，10-14 点午餐，14-21 点晚餐），消息文本中提到餐次则以消息为准
**文字记录：** 从消息中识别餐次（早/午/晚餐）+ 食物内容

- [ ] 饮食内容格式：仅食物描述部分（如"燕麦片（约一小碗）、红枣4颗、鸡蛋1个"），不要包含餐次前缀（脚本自动加）
- [ ] **⚠️ 图片识别不添加克数，只用相对分量**；但会员文字中自带克数时照原样记录

### Step 4 — 调用 record_diet.py 脚本写入

**脚本自动处理去重和追加，不需要手动查询或检查。**

**正常写入：**
```bash
python3 ~/.hermes/skills/fitness-coach/scripts/record_diet.py \
  "{bitable_token}" "{table_ids.饮食记录表}" "{餐次}" "{食物描述}"
```

**追加模式（会员补充同一餐的内容，如"还有一个鸡蛋"）：**
```bash
python3 ~/.hermes/skills/fitness-coach/scripts/record_diet.py \
  "{bitable_token}" "{table_ids.饮食记录表}" "{餐次}" "{食物描述}" --append
```

**补记历史日期：**
```bash
python3 ~/.hermes/skills/fitness-coach/scripts/record_diet.py \
  "{bitable_token}" "{table_ids.饮食记录表}" "{餐次}" "{食物描述}" --date YYYY-MM-DD
```

**脚本返回值处理：**

| action | 含义 | 回复 |
|--------|------|------|
| `created` | 新记录已创建 | 按风格确认"已记录" |
| `dedup_skipped` | 重复记录已跳过 | "这条已经记录过了哦" |
| `appended` | 已合并到已有记录 | "已补充记录" |

### Step 5 — 确认回复

- [ ] 按会员风格回复：根据脚本的 action 给出对应的确认
- [ ] **⚠️ 图片识别的饮食记录不在此处问确认**——确认已在 Step 2 完成，此处仅做写入成功的确认

### ⚠️ 训练课次已创建后需要更新主题（常见坑）

**场景：** 先创建了课次（主题为单选如"胸"），之后发现需要补充为多选（如["胸","肩膀"]），用 `+record-upsert` 会创建重复课次而非更新已有记录。

**正确做法：**
1. 用 `+record-batch-update` 更新已有记录：
   ```bash
   lark-cli base +record-batch-update \
     --base-token "{bitable_token}" \
     --table-id "{table_ids.训练课次表}" \
     --json '{"record_id_list":["{record_id}"],"patch":{"训练主题":["胸","肩膀"]}}'
   ```
2. 如果已误创建了重复记录，用 `+record-delete` 删除：
   ```bash
   lark-cli base +record-delete \
     --base-token "{bitable_token}" \
     --table-id "{table_ids.训练课次表}" \
     --record-id "{duplicate_record_id}" --yes
   ```

**⚠️ 注意：lark-cli 没有 `+record-update`（单条更新）命令**，只有 `+record-upsert`（创建或更新）和 `+record-batch-update`（批量更新）。更新已有记录必须用 `+record-batch-update`。

**预防措施：** 如果教练写的主题包含"+"（如"胸+肩膀"），在写课次前就拆分为多选数组，一次性传入，避免后续补更新。

---

## 通用注意事项

1. **飞书写入由 lark-cli 负责（唯一写入飞书的路径）**（见 SKILL.md §三"数据通道优先级"表）
2. **本地数据由凌晨 sync_to_sqlite.py 全量同步**，白天录入只写飞书，无需手动写入本地
3. **Select 选项管理仍用 lark-cli**：写入前检查仍需 lark-cli `+field-list` / `+field-update`
4. **饮食记录统一使用 `record_diet.py` 脚本**，脚本自动处理去重
5. **训练录入统一使用 `record_training.py` 脚本**，脚本封装 Select 选项检查 + 课次/动作写入
6. **不要带 `--as user`**（云端 strict_mode bot-only）
8. **写入失败不静默忽略**，必须告知教练或会员
9. **不确定的数据宁可标注"待确认"或问一句，不编造**
10. **更新已有记录用 `+record-batch-update`**，不要用 `+record-upsert`（会创建重复记录）

---


## 附录：lark-cli +record-upsert 响应格式（2026-05-17 实测）

```json
{
  "ok": true,
  "data": {
    "created": true,
    "record": {
      "data": [["会员姓名值", ["主题选项"], "2025-05-17 16:00:00"]],
      "field_id_list": ["fldJ2eNvFY", "fldcL2EosO", "fldgfsDJt0"],
      "fields": ["会员姓名", "训练主题", "训练日期"],
      "record_id_list": ["recvjSGuCeY3Ku"]
    }
  }
}
```

**关键发现：** `fields` 只包含写入时传入的字段，不包含 auto_number（课次id）、formula（会员姓名、训练日期在动作表中）等自动计算字段。`record_id` 在 `record.record_id_list[0]` 中。

