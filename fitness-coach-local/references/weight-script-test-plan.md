# record_weight.py 单元测试方案

> 2026-05-21 制定，配合体重脚本重构使用。mock subprocess.run，不依赖网络/飞书。

## 目标规格

1. **单位统一公斤**：脚本只认公斤，不转换。斤由模型提示会员纠正，走删除+重录
2. **写入**：当天 / `--date YYYY-MM-DD`，用 `+record-upsert`（体重总是新建，不更新已有记录）
3. **删除**：`--delete --date YYYY-MM-DD`（先查后删）/ `--delete --record-id recvXXX`（直接删）
4. **查询**：`--query --date YYYY-MM-DD`
5. **趋势**：`--trend --days N`，返回 `{trend, change, start_weight, end_weight, data}`
6. **同一天记两次不去重**
7. **脚本不关心发送者身份**

## 硬性规则

- stdout → 合法 JSON `{ok: bool, ...}`
- 失败 → stderr + exit code ≠ 0
- flat 对象，不用 `{fields:{...}}` 包裹
- 体重写入用 `+record-upsert`（新建），不涉及更新已有记录
- 删除用 `+record-delete --record-id XXX --yes`
- 查询用 `+record-list`

## 命令格式

```bash
# 写入
python3 record_weight.py <token> <table_id> 65.0
python3 record_weight.py <token> <table_id> 65.0 --date 2026-05-19

# 删除
python3 record_weight.py <token> <table_id> --delete --date 2026-05-20
python3 record_weight.py <token> <table_id> --delete --record-id recvXXX

# 查询
python3 record_weight.py <token> <table_id> --query --date 2026-05-20

# 趋势
python3 record_weight.py <token> <table_id> --trend --days 7
```

## 测试用例矩阵（30 个）

### A. 写入模式

| ID | 场景 | 命令 | 验证点 |
|----|------|------|--------|
| A1 | 记录当天体重 | `record_weight.py TOKEN TBL 65.0` | 调 `+record-upsert`，payload `{"体重":65.0,"日期":今天时间戳}`，stdout `{ok:true, weight:65.0, date:今天}` |
| A2 | 指定日期写入 | `... 65.0 --date 2026-05-19` | payload 日期时间戳对应 2026-05-19 00:00 CST |
| A3 | 体重带多小数 | `... 65.123` | 不截断，原值传入 |
| A4 | 整数体重 | `... 70` | payload 中 `体重:70` |
| A5 | 体重为0或负数 | `... 0` / `... -5` | 不拦截，正常写入（边界由模型/教练把控） |

### B. 删除模式（--delete）

| ID | 场景 | 命令 | 验证点 |
|----|------|------|--------|
| B1 | 按日期删除 | `... --delete --date 2026-05-20` | ① 调 `+record-list` 查该日期 ② 逐条调 `+record-delete` ③ stdout `{ok:true, deleted:[], count:N}` |
| B2 | 按日期删除无记录 | mock list 返回空 | stdout `{ok:true, deleted:[], count:0}` |
| B3 | 按 record_id 删除 | `... --delete --record-id recvXXX` | 直接调 `+record-delete`，跳过 list |
| B4 | --delete 无 --date 无 --record-id | `... --delete` | stderr 错误，exit 1 |
| B5 | --date 和 --record-id 同时给 | `... --delete --date 2026-05-20 --record-id recvXXX` | stderr 错误（二选一） |
| B6 | 删除时 lark-cli 失败 | mock 返回非 0 | stderr 含 lark 错误，exit 1 |

### C. 查询模式（--query）

| ID | 场景 | 命令 | 验证点 |
|----|------|------|--------|
| C1 | 按日期查询有数据 | `... --query --date 2026-05-20` | 调 `+record-list`，stdout `{ok:true, records:[{weight,date,record_id},...], count:N}` |
| C2 | 按日期查询无数据 | mock list 返回空 | stdout `{ok:true, records:[], count:0}` |
| C3 | --query 无 --date | `... --query` | stderr 错误，exit 1 |

### D. 趋势模式（--trend）

| ID | 场景 | 命令 | 验证点 |
|----|------|------|--------|
| D1 | 7天趋势下降 | `... --trend --days 7` | stdout `{ok:true, trend:"down", change:-2.2, ...}` |
| D2 | 趋势稳定（变化<0.5kg） | 同上 | `trend:"stable"` |
| D3 | 趋势上升 | 同上 | `trend:"up"` |
| D4 | 数据不足（1条） | mock 返回1条 | `trend:"insufficient_data"` |
| D5 | 无数据 | mock 返回空 | `trend:"no_data"` |
| D6 | --trend 无 --days | `... --trend` | 默认 --days 7 |
| D7 | --days 30 | `... --trend --days 30` | 查询30天范围 |

### E. 错误处理

| ID | 场景 | 验证点 |
|----|------|--------|
| E1 | 体重非数字（"abc"） | stderr `{ok:false, error:"Invalid weight..."}`，exit 1 |
| E2 | 缺少参数（只传 token + table_id） | stderr 错误，exit 1 |
| E3 | --date 格式错误（"abc"） | stderr 错误，exit 1 |
| E4 | lark-cli 超时 | stderr 含 timeout，exit 1 |

### F. 输出格式统一

| ID | 验证点 |
|----|--------|
| F1 | 成功 stdout 是合法 JSON，`ok:true` |
| F2 | 失败 stderr 是合法 JSON，`ok:false` |
| F3 | flat 对象，无 `{fields:{...}}` 嵌套 |
| F4 | 成功 exit 0，失败 exit ≠ 0 |
| F5 | 正常时 stderr 为空 |

## lark-cli 命令选择

| 操作 | 命令 | 理由 |
|------|------|------|
| 写入 | `+record-upsert` | 体重总是新建 |
| 删除 | `+record-delete --record-id XXX --yes` | |
| 查询 | `+record-list` + 过滤 | |
