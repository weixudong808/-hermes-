# 数据录入脚本测试指南

> 2026-05-21 建立，基于 record_weight.py 的 TDD 实战经验。

## 核心策略：单元测试 + mock subprocess.run

数据录入脚本（record_weight.py、record_diet.py 等）本质是**模型和飞书之间的翻译层**。测试目标是验证：

- 参数解析对不对
- 调用的 lark-cli 命令对不对（upsert vs batch-update vs delete）
- 传的 JSON payload 对不对
- 错误情况处理对不对

**不需要集成测试/端到端测试。** Mock 掉 subprocess.run，不依赖网络/飞书/真实表格，随时跑，秒出结果。

## TDD 红绿灯流程

1. 🔴 先写测试代码 → 跑 pytest，全部失败（脚本还没改）
2. 🟢 改脚本代码 → 跑 pytest，让测试一个个通过
3. 🔧 全部通过后，检查有无优化空间

## 测试文件位置

```
~/.hermes/skills/fitness-coach/scripts/
├── record_weight.py          ← 脚本
└── test_record_weight.py     ← 对应测试（长期保留）
```

**测试代码是长期资产，不是一次性的。** 改脚本后跑 `pytest test_record_weight.py -v` 验证没改坏。

## 跑测试命令

```bash
cd ~/.hermes/skills/fitness-coach/scripts
# pytest 路径（macOS 本地，pip install --user 安装的）
/Users/quhongfei/Library/Python/3.9/bin/pytest test_record_weight.py -v
```

## ⚠️ 踩坑记录（2026-05-21 实战）

### 坑 1：不要用 argparse

**问题：** argparse 在参数错误时自己往 stderr 写用法信息（如 `usage: record_weight.py ...`），混在我们的 JSON 输出前面，导致 JSON 解析失败。且 argparse 遇到错误会调 `sys.exit(2)`，被 `try/except SystemExit` 吞掉后返回 exitcode=0。

**解决：** 手动解析参数（`_parse_args()` 函数）。这些脚本参数很少（2 个位置参数 + 几个 flag），argparse 是过度工程。

### 坑 2：不要用 try/except SystemExit 包裹 main()

**问题：** `fail()` 函数用 `sys.exit(1)` 报错。如果 `main()` 被 `try/except SystemExit: return` 包裹，所有 `fail()` 调用都会被静默吞掉，exitcode 变成 0。

**解决：** 让 `fail()` 的 `SystemExit(1)` 正常冒泡。`main()` 不要 try/except SystemExit。

### 坑 3：测试中必须 patch sys.argv

**问题：** 直接 import 脚本并调用 `main()` 时，脚本读的是 pytest 自身的 `sys.argv`（如 `-v --tb=short`），不是测试构造的参数。

**解决：** 测试 helper 中同时 patch `sys.argv`：
```python
with patch("sys.argv", [SCRIPT, TOKEN, TABLE] + list(args)), \
     patch("sys.stdout", fake_stdout), \
     patch("sys.stderr", fake_stderr):
    rw.main()
```

### 坑 4：subprocess.TimeoutExpired 需要在 _run_lark 中捕获

**问题：** `subprocess.run(timeout=30)` 超时抛 `subprocess.TimeoutExpired` 异常，如果不捕获会导致脚本 crash 而非输出 JSON 错误。

**解决：** 在 `_run_lark()` 中 try/except：
```python
try:
    result = subprocess.run(args, capture_output=True, text=True, timeout=30)
except subprocess.TimeoutExpired:
    fail("lark-cli timed out after 30 seconds")
```

### 坑 5：函数名不能包含点号

**问题：** 测试 helper 函数名写成 `_mock_lark_cli.return_value_factory()`，Python 语法错误。

**解决：** 用下划线：`_mock_lark_cli_return_value()`。

### 坑 6：context compaction 后不要假设上轮指令仍有效

**问题：** 上轮对话说"确认后开始写代码"，但上下文 compaction 后直接开始写代码，用户未给出新指令就被执行了。

**解决：** compaction 是状态断裂点。即使 compacted summary 里写了 Active Task，也必须在回复中重新确认再动手。

### 坑 7：_mock_run 参数名要与 CompletedProcess 构造函数一致

**问题：** helper 写成 `_mock_run(stdout_str="", stderr_str="", returncode=0)`，虽然关键字传参不影响运行，但命名跟 `subprocess.CompletedProcess(stdout=, stderr=)` 不一致，容易混淆。

**解决：** 统一用 `stdout`/`stderr`，与 `CompletedProcess` 签名保持一致。

### 坑 8：_extract_payload 等命令解析 helper 需要防御性编程

**问题：** `_extract_payload(mock_call)` 直接 `cmd.index("--json")`，如果某个 mock 调用没传 `--json` 会抛 `ValueError`，pytest 报的是测试基础设施的错误而非业务断言失败，难以定位。

**解决：** 加 try/except，转换为 `AssertionError` 并附带 cmd 信息。

### 坑 9：测试文件中不留无用 import 和过时注释

**问题：** `import record_training as rt` 在函数内重复 import（`_run` helper 已 import），旁边的注释 `# Replace _run_lark to use mock directly` 是草稿遗留，都增加了阅读负担。

**解决：** 每次 review 测试时检查并清理未使用的 import 和过时注释。

## 测试用例设计模式

### Mock helper 模板

```python
def _mock_run(stdout="", stderr="", returncode=0):
    return subprocess.CompletedProcess(
        args=[], returncode=returncode, stdout=stdout, stderr=stderr
    )
```

### lark-cli 响应 mock

```python
# record-upsert 成功
def _lark_ok(record_ids=None):
    resp = {
        "ok": True,
        "data": {
            "created": True,
            "record": {
                "data": [], "field_id_list": [], "fields": [],
                "record_id_list": record_ids or ["recvAAA111"],
            },
        },
    }
    return json.dumps(resp)

# record-list
def _lark_list(records=None):
    items = [{"record_id": r["record_id"], "fields": r["fields"]} for r in records or []]
    return json.dumps({"ok": True, "data": {"items": items, "total": len(items)}})
```

### 测试分类

| 类别 | 关注点 |
|------|--------|
| 正常写入 | payload 正确、时间戳正确、round 行为 |
| 删除 | 按日期先 list 再逐条 delete、按 record_id 直接 delete |
| 查询 | 返回 records 数组、空结果处理 |
| 趋势 | up/down/stable 阈值、数据不足处理 |
| 错误处理 | 非数字体重、无效日期、lark-cli 失败、超时 |
| 输出格式 | stdout 合法 JSON ok:true、stderr 合法 JSON ok:false、exit code |
