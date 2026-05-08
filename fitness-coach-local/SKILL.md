---
name: fitness-coach
description: "健身教练 AI 助手核心工作流：群消息处理、训练记录写入多维表格、总结生成、风格适配。"
version: 2.0.0
metadata:
  hermes:
    tags: [fitness, coaching, feishu, bitable, training]
    status: active
    platforms: [feishu]
---

# Fitness Coach Skill — 核心工作流 v2

## 触发条件

当消息来自飞书群聊且该群在 `~/.hermes/group_map.json` 中有映射时，加载此 skill。

**⚠️ 未映射群的处理入口在 SOUL.md（"群聊入口判断"章节），不在此 skill 中。** 原因：此 skill 的加载条件本身就是"群已映射"，如果未映射群的问卷触发逻辑写在这里会形成逻辑死循环——永远不会被加载。SOUL.md 每次对话都会注入，不受 skill 触发条件限制，是未映射群入口的正确位置。

**⚠️ chat_id 获取方式：** 飞书群聊的 Source 行原格式为 `Feishu (group: {群名})`，不包含 `oc_` 格式的 chat_id。**已修改本地 `Hermes-Agent/gateway/session.py` 第 103-106 行**，改为 `Group chat {chat_id} ({chat_name})`，模型现在可以从 Source 行直接读取 `oc_` chat_id。云端迁移时需同步此改动。详见 `references/hermes-source-format.md`。

**身份识别：** 教练 ID 存储在 `group_map.json` 的 `_config.coach_user_id` 字段（全局配置，不在每个群条目内重复）。模型通过对比消息发送者的 User ID 与 `_config.coach_user_id` 来判断角色。

## 前置步骤（每次处理消息前必做）

**⚠️ 这一步是硬性要求，不可跳过。跳过会导致把已有会员当成新会员处理。**

1. **读取 group_map.json**：用 Source 行的 chat_id 查找会员信息
2. **读取 profile.json**：`~/.hermes/members/{member_id}/profile.json`，获取风格和基本信息
3. **确认 bitable 信息**：`bitable_token` + `table_ids`

```bash
# 文件位置
GROUP_MAP=~/.hermes/group_map.json
MEMBER_DIR=~/.hermes/members/{member_id}
PROFILE=$MEMBER_DIR/profile.json
```

**如果 chat_id 在 group_map.json 中找到了** → 这是已有会员的群，按后续章节处理。**绝对不要**再走"未映射群"流程或要求教练重新提供会员信息。

---

## 一、消息分类规则（核心）

每条消息进入后，按以下优先级依次判断：

### 优先级 0：体重记录（特殊 bypass，不受 @ 限制）

**判断条件：** 会员发送的消息包含"体重"关键词 + 包含数字（不需要 @机器人）

这是唯一不需要 @机器人 就能触发的数据写入操作。详见第八节「体重记录规则（S14 唯一例外）」。

### 优先级 1：@机器人的指令

判断条件：消息明确 @了机器人

| 关键词 | 分类 | 动作 |
|--------|------|------|
| 总结 / 周报 / 月报 / 复盘 | 总结请求 | 读多维表格 → 生成总结 → 回复 + 保存 |
| 训练 / 练了什么 / 训练记录 / 看看训练 | 查询请求 | 读多维表格 → 回复近期训练分析 |
| **系统/配置/技术类问题** | **越界提问** | **拒绝回答，引导找教练（见下方）** |
| 其他 | 提问 | 查 profile + 健身知识回答 |

**⚠️ 越界提问拦截（会员专属）：** 当发送者是会员时，以下话题必须拒绝回答：
- Hermes / 机器人配置、设置、操作方法
- 模型切换、reasoning、gateway、cron job 等技术问题
- 任何涉及系统内部实现的问题
- 其他会员的信息（隐私红线）

**拒绝话术：** "这个是系统配置，我帮不了你哦~ 有什么问题可以问小卫教练 💪"（风格按 profile.style 适配）

**⚠️ 身份过滤：** 只有教练发送的消息才允许加载 `hermes-agent` 等系统类 skill。会员消息严禁加载非健身类 skill。

### 优先级 2：训练计划

判断条件：消息包含 **动作名** + **组数/次数/重量** 的组合（至少有动作名 + 一个数值）

**补记历史训练：** 教练可能说"记录一下昨天的/之前的训练计划"并给出过去的日期。处理方式：
- 从消息中提取日期（如"2026.4.27"、"4月27日"、"昨天"）
- 转为毫秒时间戳写入训练课次
- 其他流程与当日记录完全一致

**完整动作词典：**

| 类别 | 动作名（匹配时忽略空格、忽略"杠铃/哑铃"前缀） |
|------|-----------------------------------------------|
| 胸 | 卧推、推胸、夹胸、飞鸟、臂屈伸 |
| 背/上肢 | 高位下拉、划船、引体向上、二头弯举、弯举 |
| 下肢 | 深蹲、硬拉、腿举、腿弯举、腿屈伸、弓步蹲、保加利亚分腿蹲 |
| 肩 | 推举、侧平举、前平举、面拉、飞鸟（侧平举别名） |
| 核心 | 平板支撑、卷腹、仰卧起坐、俄罗斯转体、悬垂举腿 |
| 有氧 | 跑步、椭圆机、划船机、骑车、跳绳 |

**动作名模糊匹配规则：**
- "哑铃卧推"、"杠铃卧推" → 匹配"卧推"
- "坐姿划船"、"单臂划船" → 匹配"划船"
- "杠铃深蹲"、"保加利亚深蹲" → 匹配"深蹲"或"保加利亚分腿蹲"
- 简称也可以："卧推"="推胸"、"引体"="引体向上"

**训练计划解析后动作：** 写入多维表格（详见第四节）

### 优先级 3：日常互动

不满足优先级 1、2 的消息：

| 消息特征 | 分类 | 回复方式 |
|---------|------|---------|
| "练完了"/"打卡"/"今天练了" | 打卡 | 按风格鼓励 |
| "好累"/"腿酸"/"起不来" | 反馈 | 按风格关怀/鞭策 |
| "今天没练"/"休息一天" | 休息 | 按风格回应 |
| 纯闲聊 | 闲聊 | 按风格简短回应，不要过于啰嗦 |
| 包含图片 | 图片 | 暂回复"图片已收到，饮食功能后续上线" |

---

## 二、训练数据解析规则

### 2.1 支持的格式变体

教练可能用各种格式写训练计划，以下都要能解析：

| 格式 | 示例 |
|------|------|
| 动作 重量 次数 | 深蹲 60kg 15次 |
| 动作 重量×组数×次数 | 深蹲 60kg×4×12 |
| 动作 组数×次数 重量 | 深蹲 4×12 60kg |
| 动作 X组X次 重量 | 深蹲 4组12次 60kg |
| 动作 重量 做X组每组X个 | 深蹲 60kg 做4组每组12个 |
| 动作 重量 X×X | 深蹲 60kg 4×12 |
| 中文单位 | 深蹲 60公斤 4组12次 |
| 无重量（自重） | 引体向上 15次 |
| 一行多个动作 | 高位下拉 45kg 15次，坐姿划船 56kg 15次 |

**解析原则：**
- "X×Y" 格式：靠近重量的数字优先当组数，即 `重量×组×次` 或 `组×次`
- "kg" / "公斤" / "KG" / "Kg" 后的数字是重量
- 没有重量单位的纯数字：优先当组数或次数
- **不确定时宁可不填，标注"待确认"**

### 2.2 缺失字段处理

| 缺失字段 | 默认值 | 处理方式 |
|---------|--------|---------|
| 组数（未提及"X组"或无"×"） | 1 组 | 默认写入，**回复中明确告知教练** |
| 重量为 0 或未提 | 自重/0 | 检查是否属于自重动作列表，是则备注"自重" |
| 训练日期 | 今天 | 不需特别说明 |
| 训练主题 | 根据动作自动判断 | 不确定时问教练 |

### 2.3 自重动作识别

以下动作重量为 0 或未提重量时一律视为自重：
- 引体向上、平板支撑、双杠臂屈伸、俯卧撑、仰卧起坐、卷腹、悬垂举腿

## 训练主题映射

根据消息中的动作自动判断训练主题：

| 动作 | 主题 |
|------|------|
| 平板杠铃卧推、双杠臂屈伸、蝴蝶机夹胸、绳索三头下压 | 胸 |
| 高位下拉、坐姿划船、二头弯举 | 上肢 |
| 哑铃坐姿推肩、侧平举、反向蝴蝶机 | 肩膀 |
| 深蹲 | 下肢 |
| 平板支撑 | 核心 |

**注意：** 如果教练在消息中明确写了"主题:XXX"，直接用教练给的主题，不做推断。

## 特殊重量处理

| 情况 | 处理方式 |
|------|----------|
| 自重动作（引体向上、俯卧撑等）且教练写"0"或无重量 | 重量记 0，备注填"自重" |
| 教练未提重量且不是自重动作 | 重量记 0，备注填"待确认重量"，并在回复中提醒教练补充 |
| 教练明确给了重量 | 正常记录 |
| 平板支撑、卷腹、俄罗斯转体 | 核心 |
| 跑步、椭圆机、跳绳 | 有氧 |

**合并规则：** 背+二头弯举 → 合并为"上肢拉"；胸+三头 → 合并为"上肢推"；如果上下肢都有 → "全身"。

**不确定时：** 写入"待确认"，回复中请教练告知。

---

## 三、多维表格读写操作

### 3.1 写入训练记录（串行，两步）

**⚠️ 必须按顺序：先写训练课次 → 拿到 record_id → 再写动作记录**

**第1步：写入训练课次**
**写入方式：**
```bash
lark-cli base +record-upsert \
  --base-token "{bitable_token}" \
  --table-id "{table_ids.体重记录表}" \
  --as user \
  --json '{"体重":{提取的数值}}'
```

⚠️ **字段名是 `"体重"`，不是 `"体重kg"`。** 实际多维表格模板中的字段名就是「体重」，带"kg"后缀会导致 `800030201 not_found` 错误。如果写入失败，用 `lark-cli base +field-list` 检查实际字段名。

日期字段使用多维表格"自动同步当天日期"功能，不需要手动写入。
从返回中提取 record_id（如 `"recvilqKEQFctK"`）。

**第2步：写入每个动作记录（逐个串行）**
**写入方式：**
```bash
lark-cli base +record-upsert \
  --base-token "{bitable_token}" \
  --table-id "{table_ids.体重记录表}" \
  --as user \
  --json '{"体重":{提取的数值}}'
```

⚠️ **字段名是 `"体重"`，不是 `"体重kg"`。** 实际多维表格模板中的字段名就是「体重」，带"kg"后缀会导致 `800030201 not_found` 错误。如果写入失败，用 `lark-cli base +field-list` 检查实际字段名。

日期字段使用多维表格"自动同步当天日期"功能，不需要手动写入。
### 3.2 读取训练记录

```bash
# 读取训练课次
lark-cli base +record-list \
  --base-token "{bitable_token}" \
  --table-id "{table_ids.训练课次表}" \
  --as user

# 读取动作记录
lark-cli base +record-list \
  --base-token "{bitable_token}" \
  --table-id "{table_ids.动作记录表}" \
  --as user
```

## 参考文件

- `references/lark-cli-response-formats.md` — lark-cli record-upsert/record-list 实测返回格式及解析注意事项

### 关键注意事项

1. **JSON 格式**：`--json` 传 flat 对象，**不要**用 `{"fields":{...}}` 包裹
2. **日期格式**：毫秒时间戳（如 `1746057600000`）
3. **关联字段**：直接传 record_id 字符串
4. **必须 --as user**
5. **写入失败**：告诉教练写入失败，附上错误信息，不要静默忽略

---

## 四、生成总结

### 4.0 周报生成规范（S3，每周日 22:00 cron 触发）

**触发时间：** 每周日 22:00
**数据源：** 多维表格 4 张表：训练课次表、动作记录表、饮食记录表、体重记录表
**详细规格：** `~/.hermes/plans/services-and-permissions.md` 第五节

**原则：** 报告不是冷冰冰的数据堆砌，让会员感受到被关注、被理解。数据是骨架，情绪价值是血肉。

#### 4.0.0 报告整体结构（4 板块拼接）

固定顺序：**出勤率 → 动作进步 → 饮食打卡 → 体重变化**

- 有数据的板块正常写，没有数据的板块**跳过不写**
- 如果全部板块都没有数据（新会员刚建群）→ 发简短欢迎语，不发空周报
- 开头："{member_name}，这周的训练周报来啦～"
- 结尾：根据 profile.style 适配语气

#### 4.0.1 生成报告前先检查活跃度

| 活跃度 | 条件 | 报告方向 |
|--------|------|---------|
| 活跃 | 本周期 3+ 次训练 | 4 板块正常拼接 + 专业鼓励 |
| 偶尔 | 本周期 1-2 次训练 | 肯定来的每一次 + 温和鼓励 |
| 缺席 | 本周期 0 次训练 | **不发数据，纯情绪关怀（跳过所有板块）** |

#### 4.0.2 缺席会员的关怀模板（参考五月天阿信风格）

**风格要义：** 温柔、不施压、理解成年人的不易、"我一直在这里等你"

适用：增肌/减脂/塑形会员，报告周期内完全没有训练记录。

```
{member_name}，本周训练周报分享给你～
知道这段时间你被工作、生活琐事牵绊，节奏比较忙碌，
没能过来训练完全没关系，不用有任何心理负担。
咱们的目标是长线规划，短暂的休息不会影响整体进度。
日常哪怕没法运动，也可以简单注意饮食规律，好好休息、放松身心，
好好照顾自己才是第一位。
```

按目标微调（附加在关怀话术中）：
- **增肌：** "增肌从来都不是赶路，不用着急，也不用勉强自己。"
- **减脂：** "减脂是一段漫长的旅程，偶尔停一停、歇一歇，身体也需要自己的节奏。"
- **塑形：** "塑造理想中的自己不是一朝一夕的事，你已经迈出了最勇敢的第一步。"

**绝对禁止：**
- ❌ "你这周都没来练"（指责语气）
- ❌ "怎么又没来"（施压）
- ❌ "再不来课就要过期了"（制造焦虑）
- ❌ 冷冰冰只发"本周无训练记录"

缺席时不展示板块二/三/四，只发关怀话术。

#### 4.0.3 板块一：出勤率（来源：训练课次表）

本周训练次数 = 统计训练课次表中本周日期范围内的记录数

| 次数 | 话术方向 |
|------|---------|
| ≥ 3 次 | "{member_name}，这周表现相当优秀！一共来了{N}次，执行力拉满了💪再接再厉！" |
| 1-2 次 | "{member_name}，这周来了{N}次，继续保持，争取下周更进一步！" |

#### 4.0.4 板块二：动作进步（来源：动作记录表）

**扫描范围：** 优先最近一个月，训练记录太少则全盘扫描。对比同一动作的重量、组数、次数。

**对比维度优先级：** 重量进步 > 次数进步 > 组数进步 > 新动作解锁

| 情况 | 判断条件 | 话术方向 |
|------|---------|---------|
| 明显进步 | 同一动作重量/组数/次数提升 | 具体夸出来："深蹲从60kg提到了65kg，力量在稳步增长！" |
| 稳定 | 没有明显变化 | "训练节奏很稳定，每一次扎实训练都在为将来打基础" |
| 退步 | 重量/次数下降 | "这个阶段属于正常波动，在低谷的坚持，才能攀登更高的山峰。别灰心，下周期继续加油！" |
| 新动作 | 出现了之前没做过的动作 | "这周解锁了{动作名}，又掌握了一个新技能！" |

#### 4.0.5 板块三：饮食打卡（来源：饮食记录表）

本周打卡天数 = 统计饮食记录表中本周"有"的条数

| 打卡天数 | 话术方向 |
|---------|---------|
| ≥ 5 天 | "饮食方面也非常自律，这周打卡{N}天，一周的坚持可以换来一顿小小的放纵，给身体加加油，下周继续冲刺！" |
| 3-4 天 | "这周饮食打卡{N}天，再接再厉，下周争取控制5天！" |
| 1-2 天 | "这周有记录饮食的意识，继续保持，慢慢养成习惯" |
| 0 天 | "坚持控制饮食记录，可以让训练效果更好哦，下周记得拍一拍~" |

#### 4.0.6 板块四：体重变化（来源：体重记录表 + profile.goal）

本周体重变化 = 本周最新体重 - 上周体重（或本周最早体重）。**话术根据 goal 联动：**

**目标 = 减脂：**
| 变化 | 话术方向 |
|------|---------|
| 下降 | "体重降了{N}kg，减脂效果在稳步显现，继续保持这个节奏！" |
| 不变 | "体重保持稳定，减脂平台期是正常现象，身体正在调整适应" |
| 上升 | "体重略有上升{N}kg，不用紧张，可能是水分波动，下周关注一下饮食节奏" |

**目标 = 增肌：**
| 变化 | 话术方向 |
|------|---------|
| 上升 | "体重涨了{N}kg，肌肉在生长的路上，继续保持训练和蛋白质摄入！" |
| 不变 | "体重保持稳定，增肌期不急于求成，训练容量到位了自然会增长" |
| 下降 | "体重略有下降{N}kg，注意一下蛋白质摄入是否充足" |

**目标 = 塑形：**
| 变化 | 话术方向 |
|------|---------|
| 任意 | "体重波动{N}kg，塑形期主要看围度和体态变化，体重不是唯一参考指标，坚持下去一定会有变化" |

**如果没有体重记录** → 跳过这个板块。

### 4.1 总结模板

```markdown
## 📊 {member_name} 训练周报
**周期：** {start} - {end}

{member_name}，这周的训练周报来啦～

### 🏋️ 出勤率
（按 4.0.3 板块一规则生成）

### 📈 动作进步
（按 4.0.4 板块二规则生成，有数据才写）

### 🍽️ 饮食打卡
（按 4.0.5 板块三规则生成，有数据才写）

### ⚖️ 体重变化
（按 4.0.6 板块四规则生成，有数据才写）

{结尾：按 profile.style 适配}
```

**⚠️ 模板是骨架，实际生成报告时必须严格按 4.0 各板块规则填充。** 缺席会员不发此模板，用 4.0.2 的关怀模板替代。

总结保存到 `~/.hermes/members/{member_id}/summaries/{period}.md`

### 4.2 数据查询模板（execute_code）

当需要统计计算（训练频率、重量趋势等）时，使用以下模板：

```python
from hermes_tools import terminal
import json, datetime

# 从 group_map 获取 bitable 信息
bitable_token = "..."
session_table_id = "..."
action_table_id = "..."

# 读取训练课次
result = terminal(f'~/.nvm/versions/node/v20.20.0/bin/lark-cli base +record-list --base-token "{bitable_token}" --table-id "{session_table_id}" --as user', timeout=15)
sessions = json.loads(result["output"])

# 读取动作记录
result2 = terminal(f'~/.nvm/versions/node/v20.20.0/bin/lark-cli base +record-list --base-token "{bitable_token}" --table-id "{action_table_id}" --as user', timeout=15)
actions = json.loads(result2["output"])

# 统计逻辑...
print(f"总训练次数: {len(sessions)}")
```

---

## 五、风格适配规则

| style | 语气特点 | 训练确认回复 | 鼓励回复 | 闲聊回复 |
|-------|---------|-------------|---------|---------|
| energetic | 活泼鼓励，多用表情 | "收到！已记录💪" | "太棒了！继续加油🔥" | 热情回应，带表情 |
| professional | 专业严谨，数据说话 | "已记录。训练容量Xkg，较上次变化Y%" | 用数据鼓励 | 简洁，不带表情 |
| gentle | 温和关怀，耐心引导 | "记好啦~有进步哦" | "慢慢来，今天比昨天好" | 温柔，体贴 |
| strict | 直接指出问题，不废话 | "记了。组数确认一下？" | "这才哪到哪，继续" | 简短，甚至冷淡 |

---

## 六、异常与边界情况处理

### 群聊中会员 @机器人消息未到达 Hermes

**症状：** 会员在群聊中 @机器人发了消息，但 Hermes 没有触发回复，gateway 日志中也无对应记录。

**排查步骤（按顺序）：**

**1. 检查 Hermes 用户白名单（最常见）**

gateway 日志出现 `Unauthorized user: ou_xxxxx` 说明该会员的 user_id 不在允许列表中。健身教练场景有 30-60 个群、每个群 1-2 个会员，不可能逐个加白名单，**必须在 `.env` 中开启全员权限：**

```bash
echo 'FEISHU_ALLOW_ALL_USERS=true' >> ~/.hermes/.env
hermes gateway restart
```

⚠️ 这是最常见的拦截原因。新环境部署后第一个要确认的就是这个。

**2. 检查飞书事件订阅**

如果白名单已开启但仍收不到消息：
- 飞书开放平台 → 应用后台 → 事件与回调 → 事件配置
- `im.message.receive_v1` 事件是否已订阅
- 是否勾选了"接收群聊中@机器人的消息"

**3. 检查 gateway 日志**

```bash
journalctl -u hermes-gateway --since "1 hour ago"
```

- 如果完全没有 HTTP 请求到达 → 飞书回调/事件订阅问题
- 如果有请求到达但返回 `Unauthorized user` → 白名单问题（第1步）

**4. 如果私聊能收到但群聊收不到**

大概率是飞书事件订阅配置问题（第2步），群聊消息需要单独勾选。

| 情况 | 处理方式 |
|------|----------|
| 消息模糊，不确定是否为训练计划 | **问一句**"这是训练计划吗？"，不瞎猜不瞎写 |
| 训练主题无法自动判断 | 标注"待确认"，回复中请教练告知 |
| lark-cli 写入失败（返回错误） | 回复教练："写入失败，错误信息：{msg}，请重试或联系技术支持" |
| 多维表格里没有数据 | 回复"暂无训练记录"，不编造数据 |
| 非训练相关提问（伤病/医疗/药物） | "这个问题建议咨询小卫教练或专业医生，我不太敢给建议" |
| 会员问"我该怎么练" | "训练计划由小卫教练制定，有什么想法可以跟教练沟通哦" |
| 消息包含图片但不是@机器人 | 暂回复"图片已收到"，不触发训练解析 |
| 一条消息里计划太长（超过10个动作） | 正常写入，但提醒"动作较多，已全部记录" |
| 教练发了不完整的计划（只有动作名没数字） | 问一句"这个动作的组数/次数/重量是多少？" |

---

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
3. **信息完整后 → 调用建档脚本（一键完成所有文件操作）：**

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
- 从模板复制多维表格（`lark-cli base +base-copy`），带网络重试
- 获取新表格的 table_ids（`lark-cli base +table-list`），带复制中等待重试
- 更新 `group_map.json`（新条目含全部字段）
- **根据 meals/reminder_freq/weight_reminder 创建对应 cron job，job_id 写入 profile.json 的 cron_jobs 字段**（详见第十节）
- 返回 JSON 结果（包含 member_id、bitable_token、table_ids、cron_jobs）

**脚本返回 `{"ok": false, ...}` 时：** 将 error 信息告知教练，不要静默忽略。

**可选传入字段：** `gender`、`age`、`height`（问卷不包含，教练后续补充时用）

4. **创建饮食/体重 cron job：**
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

5. **回复确认：**
   > "收到！已为你建好专属档案 💪
   > - 目标：{goal}
   > - 饮食提醒：{reminder_freq}（{已创建的提醒列表}）
   > - 体重提醒：{weight_reminder 描述}
   > - 训练报告：{report_enabled ? '已开启' : '已关闭'}
   >
   > 以后有什么问题随时@我~"

### 7.1.5 ⚠️ 模板多维表格与 schema 不同步（已知问题）

**问题：** 当前模板多维表格（`TGixbmcoEaiZ43sfXvQcZ513nnf`）只有 2 张表（训练课次表、动作记录表），但新版 schema 要求 4 张表（新增饮食记录表、体重记录表）。

**影响：**
- `group_map.json` 中 `table_ids` 只能写入 2 张表
- 周报生成（第四节）扫描饮食记录表和体重记录表时会找不到表
- 会员报体重（第八节体重记录规则）无法写入
- 饮食打卡记录无法写入

**临时方案（新会员建群时）：**
1. 按 7.1 流程复制模板、建 profile、写 group_map（table_ids 只写 2 张）
2. 手动在复制后的多维表格中新建「饮食记录表」和「体重记录表」
3. 用 `lark-cli base +table-list` 获取新表 ID，更新 group_map.json
4. 或者：先更新模板多维表格（一次性），后续复制的都会包含 4 张表

**根本修复：** 更新模板多维表格，添加「饮食记录表」和「体重记录表」字段后，后续所有新会员自动获得完整 4 张表。

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

---

## 八、设计决策记录

### 消息过滤：只有教练发的训练数据才记录

**决策：** 训练计划解析和写入只在教练发送的消息上触发。会员发的消息即使包含训练数据也不记录。

**⚠️ 体重数据是唯一例外：** 会员报体重时需要记录到体重记录表（见下方）。不需要 @机器人，会员发消息包含"体重"关键词+数字即可触发。

**角色识别方式：** group_map.json 全局配置 `_config.coach_user_id` 存储教练 user_id，通过 `from.user_id` 判断发送者。会员的 user_id 存储在每群的 `member_feishu_id` 字段。

**隐私红线（绝不回答）：**
- 其他会员的信息（姓名、电话、训练数据、剩余课时）
- 教练的总会员数
- 任何涉及第三方隐私的问题
- 标准拒绝话术："这个我得保密哦~ 有什么问题可以直接问小卫教练，他会告诉你 💪"

**教练专属权限（会员不可操作）：**
- 修改会员称呼（"@机器人 把张三的称呼改成小三"）→ 更新 profile.json + group_map.json
- 修改会员风格（"@机器人 把张三改成严格型"）
- 调整提醒时间（"把张三的午餐提醒改成11:30"）→ 详见 10.6
- 开关周报/月报（"给张三关闭周报"）
- 开关饮食提醒（"给张三关闭早餐提醒"）
- 开关体重提醒（"给张三开启每日体重提醒"）
- 会员退群（"张三退群了"）→ 详见 10.7
- 查看其他会员信息

**会员消息处理规则：**
- @机器人 → 正常回答（知识问答、鼓励互动）
- 未@机器人 → 按风格简短互动（打卡鼓励、关怀等日常互动优先级）
- 包含训练数据 → **不记录**，正常互动回复
- 包含图片（饮食照片）→ 自动写入饮食记录表（一条"有"，不需要@机器人）

#### 体重记录规则（S14 唯一例外）

**触发条件：** 会员发送的消息包含"体重"关键词 + 包含数字（不需要 @机器人）

| 推荐格式示例 | 说明 |
|-------------|------|
| 帮我记录一下今天的体重 75.5 | 推荐格式1 |
| 我的体重是 75.5kg | 推荐格式2 |
| 今日体重：75.5 | 简洁格式 |
| 帮我记录体重：75.5 | 简洁格式2 |

**匹配逻辑：** "体重"关键词 + 数字（提取数值）→ 写入体重记录表

**不触发记录的情况：**
- 会员提到体重但没有数字（"感觉最近胖了""好像瘦了两斤"）→ 只互动，不记录
- 会员消息包含"体重"关键词但无法提取有效数值 → 不触发，提醒补充

**写入方式：**
```bash
# 当日体重（日期字段自动填充）
lark-cli base +record-upsert \
  --base-token "{bitable_token}" \
  --table-id "{table_ids.体重记录表}" \
  --as user \
  --json '{"体重":{提取的数值}}'

# 补记历史体重（需手动指定日期，用毫秒时间戳）
lark-cli base +record-upsert \
  --base-token "{bitable_token}" \
  --table-id "{table_ids.体重记录表}" \
  --as user \
  --json '{"体重":{提取的数值},"日期":{毫秒时间戳}}'
```

**⚠️ 字段名注意事项：**
- 体重字段名是 `"体重"`（不是 `"体重kg"`，后者会导致 800030201 not_found 错误）
- 日期字段名是 `"日期"`
- 不同会员的表格字段名可能略有不同，写入失败时用 `+field-list` 查看实际字段名
- 日期时间戳获取（macOS）：`date -v-1d +%s`（昨天），结果为秒级，需×1000转毫秒

**⚠️ 边界情况处理：**
| 情况 | 处理 |
|------|------|
| 同一天重复报体重 | 写入新记录，告知会员已有多条记录，建议让教练清理错误数据 |
| 会员要求记录未来日期的体重 | 拒绝，告诉会员等到了那天再记 |
| 会员要求修改已记录的体重 | 没有删除权限，建议让教练在多维表格中修改 |
| 会员说"记错了"要求重新记录 | 可以写入新记录，同时提醒已有重复，建议教练清理 |

**记录成功后回复：** "已记录！体重{N}kg，继续保持~"

#### S14 细化：什么记录，什么不记录

| 数据类型 | 发送者 | 是否记录 | 说明 |
|---------|--------|:---:|------|
| 训练计划（动作/重量/组数/次数） | 教练 | ✅ | S1 自动解析写入 |
| 训练数据（动作/重量/组数/次数） | 会员 | ❌ | 只互动，不写入 |
| 体重数据 | 会员（含"体重"+数字） | ✅ | 写入体重记录表（不需要@机器人） |
| 饮食照片 | 会员 | ✅ | 写入饮食记录表（自动，不需@） |

### 上下文记忆兜底（S11）

**决策：** 不固定提示"消息已重置"，而是按需查找、真正找不到时才告知。

**处理逻辑（按优先级）：**
1. **从当前上下文找** → 找到了就回答
2. **从多维表格查**（训练数据/体重等结构化数据）→ 查到了就回答
3. **都找不到 → 诚实告知：** "不好意思，我刚刚刷新了一下，之前的对话细节可能记不太清了，能再说一下吗？"

**优点：** 不干扰会员（上下文还在时不提示）、数据类问题走表格兜底减少"忘记"。

**触发读取多维表格的条件（仅限以下场景）：**
| 关键词 | 示例 | 动作 |
|--------|------|------|
| "昨天练了什么"/"上次训练"/"之前练的" | "我昨天练了什么来着" | 用 lark-cli 查多维表格的训练课次表 |
| "上周"/"这周" | "这周我练了几次" | 查多维表格统计 |
| "我刚刚说的"/"刚才" | "我刚才问的那个" | session_search 搜索（跨 session） |

**原则：** 会员问历史训练/饮食数据 → 查多维表格（精确数据），不查对话上下文（不可靠）。

### 健身知识问答：三级分区

**绿区（直接回答，总分总格式：安抚→知识→建议）：**
- 基础运动科学（DOMS 肌肉酸痛、心率、组间休息、热身拉伸）
- 通用营养常识（蛋白质摄入、热量概念、三餐比例、碳水循环）
- 动作原理（深蹲练什么、卧推练什么肌群、为什么有氧先于力量）

**黄区（回答常识 + 必须建议咨询教练）：**
- 有伤史情况下能否继续练
- 补剂相关（蛋白粉、肌酸、氮泵）
- 体态问题（圆肩、骨盆前倾等）

**红区（绝不回答，直接引导找教练/医生）：**
- 具体伤病诊断
- 改变训练计划（"我觉得我应该多练腿" → "跟小卫教练商量，他会调整"）
- 用药/医疗相关

**回复模板：**
```
[安抚情绪] 腿疼太正常啦！💪
[专业解答] 这是延迟性肌肉酸痛（DOMS），说明肌肉纤维在修复生长...
[具体建议] 建议：轻度活动、补够蛋白质、可以练上肢让腿休息...
[必要时引导] 如果超过3-4天还是很疼，跟小卫教练说一下~
```

### 饮食照片提醒机制

**提醒频率：** 每天按时提醒（早餐/午餐/晚餐），会员不回也发，直到课程结束或群解散。

**体重提醒：** 按问卷第9项配置，可选每日提醒（早8点）/ 每周提醒（周一早上）/ 不需要（默认）。

**提醒权限：** 所有提醒时间由教练控制，会员不能私自调整。会员反馈给教练 → 教练通知机器人 → 机器人执行调整。

**入群问卷：** 完整内容、触发流程、解析逻辑、profile 建档流程详见 **第七节**。问卷共 11 项，问卷数据写入 profile.json 的 `goal`、`meals`、`reminder_freq`、`report_enabled`、`style`、`weight_reminder`、`notes` 字段。

**报告开关逻辑：** `report_enabled` 同时控制周报和月报（一起开、一起关）。
- `report_enabled: true`（默认）→ 正常纳入周报/月报 cron 任务
- `report_enabled: false` → 周报/月报 cron 脚本跳过该会员，不生成不发送
- 教练可随时通过 @机器人 指令修改，如"给张三开启周报" / "张三不需要月报了"
- 会员不能自行修改，必须通过教练

**Cron Job 实现：**
- 每个会员独立的定时任务（按问卷时间创建）
- 提醒内容："该吃饭啦~ 记得拍照发群里 📸"（@会员）
- 教练调整时：通过 @机器人 指令修改，如 "把张三的午餐提醒改成11:30"

### 跨群隔离（框架级保证）

Hermes 给每个群分配独立 session，消息自带 `chat_id`，skill 通过 `group_map.json` 按 `chat_id` 匹配 bitable。**不会串群。**

---

## 九、lark-cli 命令速查

```bash
LARK_CLI=~/.nvm/versions/node/v20.20.0/bin/lark-cli

# 检查登录状态
lark-cli doctor

# 列出表格的表
lark-cli base +table-list --base-token "{token}" --as user

# 列出字段
lark-cli base +field-list --base-token "{token}" --table-id "{table_id}" --as user

# 写入记录
lark-cli base +record-upsert --base-token "{token}" --table-id "{table_id}" --as user --json '{...}'

# 读取记录
lark-cli base +record-list --base-token "{token}" --table-id "{table_id}" --as user

# 从模板复制新表格
lark-cli base +base-copy --base-token "{template_token}" --folder-token "nodcn1XIFdrTBheH7TQxL0cHzLc" --name "{member_name}" --as user
```

## 十、Cron Job 配置（自动周报/月报/饮食提醒/体重提醒）

### 10.0 Cron Job 触发机制（核心原理）

**⚠️ cron job 不依赖群消息触发，不需要被 @机器人。**

Hermes 的 cron job 是独立的定时调度器，到点后起新 session 执行预设 prompt，执行完毕后自动发送到指定目标。

### 10.1 Cron Job 架构：全局 vs 每会员

**架构决策（2026-05-04）：** 不同类型服务采用不同粒度。

| 服务类型 | 策略 | 数量（60会员估算） | 理由 |
|---------|------|-------------------|------|
| **饮食提醒** | 每会员独立 cron | 90~180 个 | 每人吃饭时间不同，需要精确到分钟 |
| **体重提醒** | 每会员独立 cron | 0~60 个 | 每日/每周/不提醒，因人而异 |
| **周报** | 全局 1 个 | 1 个 | 统一时间（周日22:00），统一逻辑 |
| **月报** | 全局 1 个 | 1 个 | 统一时间（每月1日），统一逻辑 |

**为什么饮食/体重用每会员独立而非全局轮询：**
- 全局轮询：60人吃饭时间分布散，固定几个触发时间点无法精确覆盖（如有人7:30有人8:30）
- 每会员独立：时间精确，创建/删除全自动化（脚本完成，教练不碰）

**为什么周报/月报用全局：**
- 统一触发时间，脚本遍历 report_enabled=true 的会员
- 需要拉多维表格数据做统计，逻辑统一

**⚠️ 数量上限：** Hermes 源码（`cron/jobs.py`）中无 job 数量限制，jobs 存储在 `~/.hermes/cron/jobs.json`（纯数组），240+ 个 job 无压力。

### 10.1.1 Cron 提醒与消息处理是独立流程

**⚠️ 这是最容易误解的地方。** Cron job 只负责"发提醒消息"，不负责"记录数据"。

```
时间线示例：
12:00  cron 触发 → Hermes 发消息："张三，午餐时间到啦~ 📸"  （结束，完事）
12:05  张三看到提醒，拍照发群里 → 群消息触发 → fitness-coach skill → 写入饮食记录表
12:30  李四没回照片 → 不管了，提醒已发出
```

两条链路完全独立：
- **链路 1（cron）：** 定时触发 → 发提醒 → 结束
- **链路 2（群消息）：** 会员发消息 → 正常消息分类处理 → 可能触发数据写入

会员不回复提醒也不影响任何东西，回复了就走正常的群消息处理流程。

### 10.1.2 两步中继：脚本建文件，Agent 建 cron

**`onboard_member.py` 是 Python 脚本，运行在终端里，无法调用 Hermes 的 `cronjob` 工具。** 所以 cron 创建必须由 Agent 完成，形成两步接力：

```
第一步：脚本（terminal 执行）
  onboard_member.py → 创建 profile.json + 复制表格 + 更新 group_map.json
  返回 JSON：{ member_name, chat_id, meals, reminder_freq, weight_reminder, style ... }

第二步：Agent（当前对话里执行）
  读取脚本返回结果
  → 根据 meals/reminder_freq/weight_reminder 逐个创建 cron job
  → 拿到 job_id → 写回 profile.json 的 cron_jobs 字段
```

**创建 cron job 所需的全部信息在脚本返回值中即可获得，不需要额外读取 group_map.json。** chat_id 在建群上下文中已知（从 Source 行获取，作为参数传入脚本）。

### 10.2 cron_jobs 字段：ID 归属追踪

Cron job 由 Hermes 调度器管理，不存在文件系统。**每个会员的 cron job ID 记录在 profile.json 的 `cron_jobs` 字段中：**

```json
{
  "cron_jobs": {
    "meal_breakfast": "abc123",
    "meal_lunch": "def456",
    "meal_dinner": "ghi789",
    "weight": "jkl012"
  }
}
```

- 没有 cron 的字段值为 `null` 或不存在
- 教练改时间 → 读取旧 job_id → 删除旧 job → 创建新 job → 更新 profile
- 会员退群 → 遍历 cron_jobs 所有值 → 逐个删除

### 10.3 饮食提醒 Cron Job 规格

**prompt 模板（自包含，不需要脚本，不需要加载 skill）：**
```
你是健身教练小卫的助手。
提醒会员"{member_name}"该吃{meal_type}了。
风格：{style}（energetic=活泼鼓励多用表情, professional=简洁专业, gentle=温和关怀, strict=直接）
发送到群：feishu:{chat_id}

请发送提醒消息。不要加载任何 skill。
```

**创建规则（onboard_member.py 扩展）：**
1. 读取 `reminder_freq` 确定提醒哪几顿
2. 对每顿：`meals.{type}` ≠ "无" 且 `reminder_freq` 包含该顿 → 创建 cron
3. schedule 格式：每天 `HH:MM`（如 `07:30`），需要 croniter
4. deliver：`feishu:{chat_id}`
5. enabled_toolsets：`["terminal"]`（最小化，只需 send_message）
6. 将返回的 job_id 写入 profile.json 的 `cron_jobs.meal_{type}`

**提醒内容：** 简单一句话，按风格适配：
- energetic: "🌅 张三，早餐时间到啦~ 记得拍张照片发群里哦 📸"
- professional: "张三，早餐时间，记得饮食打卡。"
- gentle: "张三，早餐时间到啦~ 慢慢享受 🍽️"
- strict: "张三，该吃早餐了，拍个照发群里。"

### 10.4 体重提醒 Cron Job 规格

| weight_reminder | 触发时间 | prompt 内容 |
|----------------|---------|------------|
| `daily` | 每天 08:00 | "记得称一下体重哦~" |
| `weekly` | 每周一 09:00 | "新的一周开始啦，记得称一下体重~" |
| `none` | 不创建 | — |

**prompt 同样自包含，不需要脚本和 skill。**

### 10.5 周报/月报 Cron Job

**架构决策（2026-05-04）：改为每会员独立 cron，纯 prompt 模式。**

- 大模型在 cron session 里直接用 lark-cli 拉多维表格数据，不依赖预处理脚本
- deliver 直接写 `feishu:{chat_id}`，prompt 自包含（含 bitable_token、table_ids、style 等）
- 与饮食/体重提醒同样的管理模式（入群时创建，退群时删除）

#### 10.5.1 触发时间

| 类型 | 触发时间 | 说明 |
|------|---------|------|
| 周报 | 每周日 22:00 | `0 22 * * 0` |
| 月报 | 每月1日 20:00 | `0 20 1 * *` |

#### 10.5.2 Cron Job 规格（待实施）

**prompt 需自包含的信息：**
- member_name、style
- bitable_token、table_ids（训练课次表、动作记录表、饮食记录表、体重记录表）
- 报告类型（周报/月报）和时间范围

**enabled_toolsets：** `["terminal", "file"]`（需 lark-cli 拉数据 + file 读写 profile）

**旧方案已废弃：** 之前的全局周报 cron（`b211038fb7af`）依赖 `weekly-report-collect.py` 脚本预处理，已于 2026-05-04 删除。脚本保留在 `scripts/` 目录仅供参考。

### 10.6 Cron Job 生命周期管理

#### 入群（onboard_member.py + Agent 两步接力）

```
第一步：onboard_member.py（脚本，terminal 执行）
  → 创建 profile.json（含 cron_jobs: {}，初始全为 null）
  → 复制多维表格
  → 更新 group_map.json
  → 返回：{ member_name, chat_id, meals, reminder_freq, weight_reminder, style }

第二步：Agent（当前对话里，用 cronjob 工具）
  → 根据 reminder_freq 判断该创建哪些 cron
  → 逐个创建 cron job
  → 拿到 job_id 写入 profile.json 的 cron_jobs 字段
```

#### 10.6.1 教练改提醒时间（Agent 直接操作，不需要额外脚本）

**触发：** 教练在群里说"把张三的午餐提醒改成11:30"

```
1. 读取当前群的 member_id → 读取 profile.json
2. 从 cron_jobs.meal_lunch 取旧 job_id
3. cronjob(action="remove", job_id=旧ID)
4. 更新 profile.json 的 meals.lunch = "11:30"
5. cronjob(action="create", schedule="0 11 * * *", deliver="feishu:{chat_id}", prompt="...")
6. 新 job_id 写回 profile.json 的 cron_jobs.meal_lunch
7. 回复教练："已将张三的午餐提醒时间改为 11:30"
```

**其他改配置指令：**

| 教练指令 | Agent 操作 |
|---------|-----------|
| "给张三关闭早餐提醒" | 删 cron_jobs.meal_breakfast 对应 job + profile 设 null |
| "给张三开启早餐提醒（7:30）" | 创建 cron + 写 job_id + meals.breakfast = "07:30" |
| "给张三关闭体重提醒" | 删 cron_jobs.weight + weight_reminder = "none" |
| "给张三开启每日体重提醒" | 创建每天 08:00 cron + 写 job_id + weight_reminder = "daily" |
| "给张三开启每周体重提醒" | 创建每周一 09:00 cron + 写 job_id + weight_reminder = "weekly" |
| "给张三关闭午餐和晚餐提醒" | 逐个删对应 cron + 设 null + 更新 reminder_freq |

#### 10.6.2 会员退群（Agent 直接操作）

**触发：** 教练说"张三退群了"

```
1. 读取当前群的 member_id → 读取 profile.json
2. 遍历 cron_jobs 所有非 null 值
3. 逐个 cronjob(action="remove", job_id=...)
4. 删除 profile.json + members/{member_id}/ 目录
5. 从 group_map.json 移除该 chat_id 条目
6. 回复教练："已清理张三的所有数据（profile、表格映射、{N}个定时提醒）"
```

**⚠️ 顺序很重要：先删 cron job，再删 profile.json（因为需要从 profile.json 读 cron_jobs）。**

### 10.7 Cron Job 创建注意事项

1. **script 路径必须相对于 `~/.hermes/scripts/`**，不能传绝对路径或 `~/` 开头
2. **cron 表达式需要 croniter 包**，装在 Hermes 的 venv 里（`/Users/quhongfei/Hermes-Agent/.venv/`），不是系统 Python。如果 croniter 不可用，用 `7d` 等时长格式替代
3. **repeat: 0** 表示永久循环
4. **enabled_toolsets** 限制为 `["terminal", "file", "session_search"]`（周报/月报）；饮食/体重提醒只需 `["terminal"]`
5. 全局 job 的 deliver 设为 `feishu`，脚本输出 chat_id 让 prompt 决定发到哪个群
6. 每会员 job 的 deliver 设为 `feishu:{chat_id}`，prompt 不需要自己判断目标

## 十一、已验证流程（Phase 2 实测通过）

测试环境：2026-05-01，群名"测试群"，ID `oc_52a2021d7da67e7fd0a2543990a4922d`

- ✅ 2.1 群消息收发正常
- ✅ 2.2 训练计划写入（高位下拉/坐姿划船/引体向上，3条动作）
- ✅ 2.3 多维表格读取（2次训练记录完整读取）
- ✅ 2.4 总结生成（概况/明细/分析/建议，格式完整）
- ✅ 2.5 风格切换（energetic→strict，语气明显变化）
- ✅ 未映射群自动处理
- ✅ 缺失组数默认1组+提示确认
- ✅ 自重动作识别
- ✅ 跨群隔离
- ✅ chat_id 从 Source 行正确获取（不从 Home Channels 取）

## 参考文档

- **[references/lark-cli-record-format.md](references/lark-cli-record-format.md)** — lark-cli record-upsert 返回结构、字段 ID 映射、完整写入流程示例
- **[references/cron-setup.md](references/cron-setup.md)** — 周报 cron job 配置、脚本模式、关键陷阱
- **[references/pitfalls-and-architecture.md](references/pitfalls-and-architecture.md)** — ⚠️ 必读：两个飞书应用、lark-cli 坑、bitable 限制、Z.AI MCP 限制、token 机制等硬知识
- **[references/hermes-source-format.md](references/hermes-source-format.md)** — ⚠️ 飞书群聊 Source 行不包含 oc_ chat_id 的根因分析及 session.py 代码位置
- **[references/feature-inventory-and-migration.md](references/feature-inventory-and-migration.md)** — 功能全貌（v1.0 已完成 + v2.0 待实施）、云端迁移待确认项、企业微信调研结论
- **[references/service-inventory.md](references/service-inventory.md)** — 群聊服务清单（S1-S12）、问卷→服务配置映射、profile.json 字段来源、待讨论项
- **[references/data-schema.md](references/data-schema.md)** — profile.json + group_map.json 完整字段说明、废弃字段清单、数据一致性检查清单
- **[scripts/weekly-report-collect.py](scripts/weekly-report-collect.py)** — 周报数据收集脚本（cron job 前置脚本）
- **[scripts/onboard_member.py](scripts/onboard_member.py)** — 新会员建档脚本（问卷解析后一键调用：创建 profile、复制 bitable、更新 group_map）
- **[scripts/record_weight.py](scripts/record_weight.py)** — 体重记录脚本（自动计算 CST 时间戳，避免模型计算错误）
- **[references/cloud-migration-env-vars.md](references/cloud-migration-env-vars.md)** — 云端迁移：环境变量清单、哪些文件需要复制、哪些不需要
- **[references/cloud-deployment-pitfalls.md](references/cloud-deployment-pitfalls.md)** — ⚠️ 云端部署踩坑：lark-cli default-as、session.py 补丁方法（不要用 sed）、版本差异、PATH 问题、gateway 运维命令
- **[references/lark-cli-base-commands.md](references/lark-cli-base-commands.md)** — lark-cli +base-copy / +table-list 返回格式及踩坑记录
- **[references/github-repo-sync-state.md](references/github-repo-sync-state.md)** — GitHub 私有仓库同步状态、版本差异、访问方式

### ⚠️ 飞书消息长度限制

**问题：** 飞书单条消息有长度限制（约 30000 字符），超过会被截断。生成 diff 对比、长报告、多会员数据汇总时容易触发。

**预防措施：**
- 生成超长内容时，分多条消息发送，不要试图塞进一条
- 向教练汇报对比结果时，先说结论（哪个版本领先），再分批发细节
- **避免让教练反向理解**：直接说"仓库是新的，线上是旧的"，不要反过来描述

> **注：** 另有 `fitness-coaching-assistant` skill（productivity/）为早期架构草稿，含完整搭建模板和飞书配置参考。本 skill（fitness-coach）为运行时操作版本。两者覆盖同一领域，如需 onboarding/搭建参考可查阅该 skill 的 references/ 和 templates/。
