# Skill 测试方法论（Prompt 重构回归保障）

> 适用场景：对 SKILL.md 进行结构拆分、章节合并、内容精简等改造时，确保改造前后 AI 助手的行为不退化。

## 核心问题

Skill 是 prompt 而非代码，传统单元测试（import + assert）不适用。真正要防的是：**改了结构后，助手在某些场景下"忘了规则"或"做错了决策"**。

## 三层测试架构

### 第一层：关键行为回归（最核心）

准备一组标准输入 → 期望行为的测试用例，改造前后各跑一遍，比对结果。

**场景分类覆盖：**

| 类别 | 核心关注点 |
|------|-----------|
| 身份识别 | 教练 vs 会员 vs 陌生人的权限和行为差异 |
| 意图判断 | 训练/体重/饮食/打卡/查询/建议 各意图的识别准确性 |
| 训练解析 | 7+ 种格式变体、歧义格式、有氧/时间类动作 |
| 多维表格 | 课次+动作写入顺序、Select 选项补充、JSON 格式 |
| 风格适配 | energetic/strict/gentle/professional + 人设覆写 |
| 边界情况 | 越界拦截、伤病引导、减脂饮食诱惑立场、上下文丢失、图片识别、周报、TDEE |
| Onboarding | 问卷建档、教练跳过、重复问卷、多群映射 |
| Cron 生命周期 | 健康检查、退群清理、修改时间、执行失败 |
| 记忆更新 | habits 写入、injuries 替换、临时信息不记、超限清理 |
| 数据边界 | 体重极端值、饮食去重/追加、历史补记 |
| 跨群隔离 | 并发不混淆、教练跨群查询 |
| 自愈备份 | GitHub 备份失败、cron 丢失恢复、孤儿目录 |

**执行方式：** 写成 markdown 场景清单（每个场景 = 模拟输入 + 期望行为 + 判定标准），手动复制粘贴跑。不需要自动化。

**判定标准：** 核心行为（是否写入、是否确认、工具调用序列）必须一致；措辞可因风格适配合理变化，不算 regression。

### 第二层：端到端冒烟测试

改造完成后，在真实群里走一遍完整流程：
1. 教练发训练计划 → 验证写入多维表格
2. 会员发训练数据 → 验证确认式流程
3. 会员发饮食 → 验证记录流程
4. 会员查"最近训练" → 验证查询返回数据
5. 发边界问题（系统配置、伤病） → 验证拒绝/引导

### 第三层：结构完整性检查（自动化）

用 pytest 脚本自动验证：
- SKILL.md 存在、非空、YAML frontmatter 完整
- 10 个必要章节（前置步骤、意图判断、数据解析、多维表格、风格、异常、问卷、设计决策、Cron、自愈）
- 所有引用的 references/scripts/templates 文件存在
- 无孤儿文件（存在但未被引用的文件）
- reference 之间的交叉引用有效（排除 xxx.md 等占位符）
- group_map.json 中每个会员都有对应 profile.json
- SKILL.md 描述的脚本参数与脚本实际支持参数一致
- 关键业务规则存在（不套 fields、record_id_list 提取、不带 --as user 等）
- SKILL.md 行数告警（>500 行提示改造）

## 执行顺序

```
1. 改造前：跑行为回归建立 baseline（约 30 分钟）
2. 改造 SKILL.md
3. 跑结构完整性 pytest（秒级）
4. 跑行为回归第二轮，对比 baseline
5. 端到端冒烟测试（真实环境）
6. 上线观察
```

## 注意事项

- 行为回归测试**不要试图写成 pytest**：prompt 工程的输出依赖 LLM，无法 import 和 assert
- 场景清单建议分两批：第一批（改造前必跑）约 29 条核心场景，第二批（改造后抽检）约 24 条
- 结构完整性脚本发现孤儿文件时，不要误报——检查 reference 之间的交叉引用和占位符模式
- `skill-authoring-best-practices.md` 中可能包含 `data-entry-workflow.md` 等过时引用（应为 `data-entry-paths.md`），结构测试能捕获这类问题

## 已有测试资产

- 行为回归场景清单：`/Users/quhongfei/Documents/code/Hermes skill/test-scenarios.md`（46 场景）
- 结构完整性 pytest：`/Users/quhongfei/Documents/code/Hermes skill/test_skill_structure.py`（37 检查项）
- 脚本单元测试：`scripts/test_record_weight.py`（34 用例）、`scripts/test_record_training.py`（30 用例）
