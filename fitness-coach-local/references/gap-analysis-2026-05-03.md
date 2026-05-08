# Skill Gap Analysis & Implementation Plan

> 2026-05-03 对比 services-and-permissions.md vs SKILL.md

## ✅ 已覆盖（不需要改动）

S1 训练计划记录 / S2 训练数据查询 / S7 风格适配 / S8 日常互动鼓励 /
S9 知识问答 / S10 隐私保护 / S11 上下文记忆兜底 / S12 教练权限 /
S13 跨群隔离 / S14 会员不记录 / 体重记录触发 / 饮食照片触发 /
问卷11项 / Cron 触发机制 / 问卷→服务映射

## ⚠️ Skill 有规则但 cron 未创建

| 需求 | 状态 | 差距 |
|------|------|------|
| S3 周报 | 有旧cron，脚本只读2张表 | 脚本需增加读饮食表+体重表 |
| S4 月报 | 未创建 | 需创建 cron + 脚本 |
| S5 饮食提醒 | 未创建 | 需为每个会员创建 1-3 个 cron |
| S6 体重提醒 | 未创建 | 需按 weight_reminder 创建 cron |

## ❌ Skill 缺失（需新增规则）

### Phase 1: 教练指令扩展（消息分类规则）

| 指令关键词 | 动作 |
|-----------|------|
| "称呼改成/改称呼" | 更新 profile `basic_info.name` + group_map `member_name` |
| "提醒改成/调整提醒/改成XX点" | 更新 profile `meals` + 重建 cron job |
| "关闭周报/开启周报/关闭月报/开启月报" | 更新 profile + group_map `report_enabled` |
| "退群/移除" | 删 profile + 移除 group_map + 删 cron jobs |
| "张三这周练了什么"（跨群） | 读目标会员多维表格返回数据 |

⚠️ 以上指令仅 coach_user_id 可执行，会员发的一律拒绝。

### Phase 1: 饮食照片写入命令模板

```bash
lark-cli base +record-upsert \
  --base-token "{bitable_token}" \
  --table-id "{table_ids.饮食记录表}" \
  --as user \
  --json '{"是否打卡":"有"}'
```

### Phase 1: 问卷建档后创建 cron job

问卷完成后（7.3 第3步后）新增第4步：
- meals 非"无" → 创建 S5 饮食提醒 cron
- weight_reminder = "daily"/"weekly" → 创建 S6 体重提醒 cron
- report_enabled = true → 加入周报/月报扫描范围

### Phase 2: 多维表格新增 2 张表

**饮食记录表：** 日期(自动同步当天) + 是否打卡(文本"有")
**体重记录表：** 日期(自动同步当天) + 体重kg(数字)

建完后更新 group_map table_ids。

### Phase 3: Cron Job 创建

- 更新周报脚本读4张表（+饮食+体重）
- 创建月报 cron（每月1日 20:00）
- 创建饮食提醒 cron（per-member，按 meals 配置）
- 创建体重提醒 cron（per-member，按 weight_reminder）

## 完整文档

详细实施计划见：`/Users/quhongfei/.hermes/plans/skill-gap-analysis.md`
