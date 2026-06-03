# Skill Authoring Best Practices（官方指南精要）

> 来源：Claude 官方 anthropic-best-practices.md + superpowers writing-skills SKILL.md
> 用途：指导 fitness-coach SKILL.md 的重构和日常维护

## 核心红线

### SKILL.md 不超过 500 行
官方明确标准。超过就要拆文件到 references/。高频加载的 skill 目标 < 200 词正文。

### 假设 Claude 已经很聪明
> "Default assumption: Claude is already very smart. Only add context Claude doesn't already have."

每段内容都要问：
- "Claude 真的需要这个解释吗？"
- "能不能假设 Claude 已经知道？"
- "这段话值得它消耗的 token 吗？"

### Description = When to Use，NOT What the Skill Does
> ⚠️ 如果 description 里总结了工作流，Claude 会直接按摘要做，跳过正文。

```yaml
# ❌ BAD: 总结了工作流
description: Processes messages - dispatches training to bitable, sends style-adapted responses

# ✅ GOOD: 只写触发条件
description: Use when processing Feishu group/DM messages for fitness coaching workflows
```

## 渐进式披露（Progressive Disclosure）

SKILL.md 是**目录页**，不是百科全书。

### 第一层：SKILL.md（目录页）
- 概览和核心原则（1-2 句）
- 触发条件 / When to Use
- 关键决策流程（用 checklist 或简短步骤）
- **硬性红线**（必须遵守的规则，用 MUST/NEVER/⚠️ 标记）
- 指向详细内容的引用（一行一个）

### 第二层：references/（按需加载）
Claude 只有在需要时才读取，不读就不消耗 token。
- API 用法和命令详情
- 边界案例和特殊格式处理
- 踩坑记录和排障手册
- 运维细节和部署流程

### 引用深度：只允许一层
```markdown
# ✅ GOOD: SKILL.md → reference/xxx.md（一层）
**饮食记录写入流程**: 详见 references/data-entry-paths.md

# ❌ BAD: SKILL.md → reference/xxx.md → reference/yyy.md（两层）
```

## 文件组织模式

### 模式 1：高层指南 + 引用文件（最常见）
```
fitness-coach/
├── SKILL.md              # 概览 + 工作流 + 红线 + 索引
├── references/
│   ├── data-entry-paths.md    # 饮食/训练/体重写入流程
│   ├── pitfalls-and-architecture.md  # 踩坑记录
│   ├── style-guide.md            # 风格适配详细规则
│   ├── system-self-healing.md    # 健康检查运维流程
│   └── member-management.md      # 建档和管理流程
├── scripts/
│   ├── record_training.py
│   ├── record_weight.py
│   └── ...
└── templates/
```

### 模式 2：按领域分 reference
当 reference 文件很多时，可以按领域分：
```
reference/
├── training.md
├── diet.md
├── weight.md
└── ops.md
```

## Token 效率技巧

### 用 cross-reference 代替重复内容
> "50-100x context savings" — superpowers

```markdown
# ❌ BAD: 在 SKILL.md 里展开 20 行流程
When recording diet, dispatch subagent with template...
[20 lines of detailed instructions]

# ✅ GOOD: 一行引用
**饮食记录**: 用 record_diet.py 脚本，详见 references/data-entry-paths.md
```

### 压缩示例
```markdown
# ❌ BAD: 42 词的详细示例
your human partner: "How did we handle authentication errors before?"
You: I'll search past conversations for authentication patterns...
[Dispatch subagent with search query: "..."]

# ✅ GOOD: 20 词的最小示例
Partner: "How did we handle auth errors?"
You: Searching...
[Dispatch subagent → synthesis]
```

### 工具文档用 --help 代替内联
```markdown
# ❌ BAD
record_training supports --date, --exercise, --sets, --reps, --weight, --member

# ✅ GOOD
record_training.py: 运行 python scripts/record_training.py --help 查看参数
```

## 自由度匹配

| 任务类型 | 自由度 | 指导方式 |
|---------|--------|---------|
| 灵活任务（鼓励、互动） | 高 | 文字指导，给方向 |
| 有偏好的任务（数据格式） | 中 | 模板 + 参数 |
| 脆弱任务（多维表格写入） | 低 | 精确脚本，不许改参数 |

> 类比：窄桥两边是悬崖 → 精确指令；开阔草原 → 给方向就好。

## 反模式清单

| 反模式 | 正确做法 |
|--------|---------|
| description 总结工作流 | 只写触发条件和场景 |
| SKILL.md > 500 行 | 拆到 references/ |
| 叙事式描述（"2026-05-22 我们发现..."） | 规则式描述（"⚠️ bitable copy 会报 800004011，必须用 update"） |
| 给太多选项 | 给一个默认 + 一个 escape hatch |
| 重复引用文件内容 | 一行引用 + "详见 xxx" |
| 引用超过一层 | 保持一层 |
| 时间敏感信息 | 放在 "旧模式" 折叠区 |
| 术语不一致 | 统一用一个词 |

## 评估和迭代

### 评估驱动开发
1. 不带 skill 跑任务，记录失败点
2. 写最小化的 skill 解决这些失败
3. 带 skill 再跑，验证改进
4. 发现新的失败点 → 补充 → 再验证

### 观察 Claude 如何使用 skill
- 是否走了你没预料到的阅读路径？→ 结构可能不够直观
- 是否反复读同一个文件？→ 内容应该提升到 SKILL.md
- 是否忽略某个 reference？→ 可能不需要，或者引用不够明显

## Skill 维护纪律（针对 fitness-coach）

> 以下规则写入 SKILL.md 头部，引导 Hermes 的 review agent 正确维护。

### 新增内容的分类处理
- **工作流步骤变更**（新增/修改意图判断、写入流程）→ patch SKILL.md
- **风格/规则变更**（新增风格类型、修改确认逻辑）→ patch SKILL.md
- **Pitfall / 踩坑记录** → `references/pitfalls-and-architecture.md`
- **工具/脚本 API 用法** → 对应 `references/xxx-api.md`
- **运维/部署细节** → `references/pitfalls-and-architecture.md`
- **边界案例和特殊格式** → `references/data-entry-paths.md`

### 写入 references 后
- 在 SKILL.md 对应位置加一行 `> 详见 references/xxx.md`
- 不要在 SKILL.md 中展开 reference 内容
