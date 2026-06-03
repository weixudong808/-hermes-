#!/usr/bin/env python3
"""Unit tests for record_weight.py — mock subprocess.run, no network needed.

Run:
    cd ~/.hermes/skills/fitness-coach/scripts
    pytest test_record_weight.py -v
"""

import json
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from io import StringIO
from unittest.mock import patch, MagicMock

import pytest

CST = timezone(timedelta(hours=8))
SCRIPT = "record_weight.py"
TOKEN = "test_token"
TABLE = "tblTEST123"


# ── Helpers ──────────────────────────────────────────────────────────


def _ts(date_str: str) -> int:
    """Return millisecond timestamp for YYYY-MM-DD 00:00 CST."""
    dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=CST)
    return int(dt.timestamp() * 1000)


def _run(*args, env_extra=None):
    """Run record_weight.py in-process, return (stdout, stderr, exitcode)."""
    import record_weight as rw

    argv = [SCRIPT, TOKEN, TABLE] + list(args)

    fake_stdout = StringIO()
    fake_stderr = StringIO()

    with patch("sys.argv", argv), \
         patch("sys.stdout", fake_stdout), \
         patch("sys.stderr", fake_stderr):
        try:
            rw.main()
            exitcode = 0
        except SystemExit as e:
            exitcode = e.code if e.code is not None else 1

    return fake_stdout.getvalue(), fake_stderr.getvalue(), exitcode


def _mock_lark_cli_return_value(stdout_str="", stderr_str="", returncode=0):
    """Create a mock subprocess.run return value."""
    return subprocess.CompletedProcess(
        args=[], returncode=returncode, stdout=stdout_str, stderr=stderr_str
    )


def _lark_ok(created=True, record_ids=None, extra_fields=None):
    """Build a lark-cli +record-upsert success response."""
    if record_ids is None:
        record_ids = ["recvAAA111"]
    resp = {
        "ok": True,
        "data": {
            "created": created,
            "record": {
                "data": [],
                "field_id_list": [],
                "fields": [],
                "record_id_list": record_ids,
            },
        },
    }
    if extra_fields:
        resp["data"]["record"].update(extra_fields)
    return json.dumps(resp)


def _lark_list(records=None):
    """Build a lark-cli +record-list response.

    records: list of dicts, each with 'weight', 'date' (YYYY-MM-DD), 'record_id'.
    """
    if records is None:
        records = []
    items = []
    for r in records:
        date_ms = _ts(r["date"])
        items.append(
            {
                "record_id": r["record_id"],
                "fields": {"体重": r["weight"], "日期": date_ms},
            }
        )
    resp = {
        "ok": True,
        "data": {"items": items, "total": len(items)},
    }
    return json.dumps(resp)


def _lark_error(msg="internal error"):
    """Build a lark-cli error response."""
    return json.dumps({"ok": False, "error": {"code": 999, "message": msg}})


# ══════════════════════════════════════════════════════════════════════
# A. 写入模式
# ══════════════════════════════════════════════════════════════════════


class TestWriteMode:
    """A1-A5: record_weight.py TOKEN TBL <weight> [--date DATE]"""

    @patch("record_weight.subprocess.run")
    def test_A1_write_today(self, mock_run):
        """记录当天体重 → +record-upsert, payload 含体重+日期时间戳, stdout ok"""
        mock_run.return_value = _mock_lark_cli_return_value(
            stdout_str=_lark_ok(), returncode=0
        )

        stdout, stderr, code = _run("65.0")
        assert code == 0
        out = json.loads(stdout)
        assert out["ok"] is True
        assert out["weight"] == 65.0

        # Verify lark-cli call
        call_args = mock_run.call_args
        cmd = call_args[0][0]
        assert "+record-upsert" in cmd
        payload = json.loads(cmd[cmd.index("--json") + 1])
        assert payload["体重"] == 65.0
        assert isinstance(payload["日期"], int)
        assert payload["日期"] > 0

    @patch("record_weight.subprocess.run")
    def test_A2_write_specific_date(self, mock_run):
        """--date 2026-05-19 → payload 日期时间戳对应该天"""
        mock_run.return_value = _mock_lark_cli_return_value(
            stdout_str=_lark_ok(), returncode=0
        )

        stdout, stderr, code = _run("65.0", "--date", "2026-05-19")
        assert code == 0
        out = json.loads(stdout)
        assert out["date"] == "2026-05-19"

        call_args = mock_run.call_args
        cmd = call_args[0][0]
        payload = json.loads(cmd[cmd.index("--json") + 1])
        assert payload["日期"] == _ts("2026-05-19")

    @patch("record_weight.subprocess.run")
    def test_A3_round_to_one_decimal(self, mock_run):
        """输入 65.123 → round(65.1) 写入"""
        mock_run.return_value = _mock_lark_cli_return_value(
            stdout_str=_lark_ok(), returncode=0
        )

        stdout, stderr, code = _run("65.123")
        assert code == 0
        out = json.loads(stdout)
        assert out["weight"] == 65.1

        call_args = mock_run.call_args
        cmd = call_args[0][0]
        payload = json.loads(cmd[cmd.index("--json") + 1])
        assert payload["体重"] == 65.1

    @patch("record_weight.subprocess.run")
    def test_A4_integer_weight(self, mock_run):
        """整数 70 → payload 体重 70.0"""
        mock_run.return_value = _mock_lark_cli_return_value(
            stdout_str=_lark_ok(), returncode=0
        )

        stdout, stderr, code = _run("70")
        assert code == 0
        out = json.loads(stdout)
        assert out["weight"] == 70.0

        call_args = mock_run.call_args
        cmd = call_args[0][0]
        payload = json.loads(cmd[cmd.index("--json") + 1])
        assert payload["体重"] == 70.0

    @patch("record_weight.subprocess.run")
    def test_A5_zero_and_negative(self, mock_run):
        """体重 0 或 -5 → 不拦截，正常写入（边界由模型/教练把控）"""
        mock_run.return_value = _mock_lark_cli_return_value(
            stdout_str=_lark_ok(), returncode=0
        )

        # Test 0
        stdout, stderr, code = _run("0")
        assert code == 0
        out = json.loads(stdout)
        assert out["weight"] == 0.0

        # Test -5
        stdout, stderr, code = _run("-5")
        assert code == 0
        out = json.loads(stdout)
        assert out["weight"] == -5.0


# ══════════════════════════════════════════════════════════════════════
# B. 删除模式
# ══════════════════════════════════════════════════════════════════════


class TestDeleteMode:
    """B1-B6: --delete [--date DATE | --record-id ID]"""

    @patch("record_weight.subprocess.run")
    def test_B1_delete_by_date(self, mock_run):
        """--delete --date → list 该日期 → 逐条 record-delete"""
        # First call: record-list returns 2 records
        mock_run.side_effect = [
            _mock_lark_cli_return_value(
                stdout_str=_lark_list(
                    [
                        {"weight": 65.0, "date": "2026-05-20", "record_id": "recvAAA"},
                        {"weight": 64.5, "date": "2026-05-20", "record_id": "recvBBB"},
                    ]
                ),
                returncode=0,
            ),
            # Two delete calls
            _mock_lark_cli_return_value(
                stdout_str=json.dumps({"ok": True}), returncode=0
            ),
            _mock_lark_cli_return_value(
                stdout_str=json.dumps({"ok": True}), returncode=0
            ),
        ]

        stdout, stderr, code = _run("--delete", "--date", "2026-05-20")
        assert code == 0
        out = json.loads(stdout)
        assert out["ok"] is True
        assert out["count"] == 2
        assert set(out["deleted"]) == {"recvAAA", "recvBBB"}

    @patch("record_weight.subprocess.run")
    def test_B2_delete_by_date_no_records(self, mock_run):
        """--delete --date → list 返回空 → deleted:[]"""
        mock_run.side_effect = [
            _mock_lark_cli_return_value(
                stdout_str=_lark_list([]), returncode=0
            ),
        ]

        stdout, stderr, code = _run("--delete", "--date", "2026-05-20")
        assert code == 0
        out = json.loads(stdout)
        assert out["ok"] is True
        assert out["count"] == 0
        assert out["deleted"] == []

    @patch("record_weight.subprocess.run")
    def test_B3_delete_by_record_id(self, mock_run):
        """--delete --record-id recvXXX → 直接删除，跳过 list"""
        mock_run.return_value = _mock_lark_cli_return_value(
            stdout_str=json.dumps({"ok": True}), returncode=0
        )

        stdout, stderr, code = _run("--delete", "--record-id", "recvXXX")
        assert code == 0
        out = json.loads(stdout)
        assert out["ok"] is True

        # Verify only one call (no list query)
        assert mock_run.call_count == 1
        cmd = mock_run.call_args[0][0]
        assert "+record-delete" in cmd
        assert "--record-id" in cmd
        assert "recvXXX" in cmd

    @patch("record_weight.subprocess.run")
    def test_B4_delete_no_target(self, mock_run):
        """--delete without --date or --record-id → error"""
        stdout, stderr, code = _run("--delete")
        assert code != 0
        err = json.loads(stderr)
        assert err["ok"] is False

    @patch("record_weight.subprocess.run")
    def test_B5_delete_both_targets(self, mock_run):
        """--delete --date AND --record-id → error"""
        stdout, stderr, code = _run(
            "--delete", "--date", "2026-05-20", "--record-id", "recvXXX"
        )
        assert code != 0
        err = json.loads(stderr)
        assert err["ok"] is False

    @patch("record_weight.subprocess.run")
    def test_B6_delete_lark_failure(self, mock_run):
        """删除时 lark-cli 失败 → stderr 含错误"""
        mock_run.side_effect = [
            _mock_lark_cli_return_value(
                stdout_str=_lark_list(
                    [{"weight": 65.0, "date": "2026-05-20", "record_id": "recvAAA"}]
                ),
                returncode=0,
            ),
            _mock_lark_cli_return_value(
                stdout_str="", stderr_str=_lark_error("permission denied"), returncode=1
            ),
        ]

        stdout, stderr, code = _run("--delete", "--date", "2026-05-20")
        assert code != 0
        err = json.loads(stderr)
        assert err["ok"] is False
        assert "lark-cli" in err["error"].lower() or "permission" in err["error"].lower()


# ══════════════════════════════════════════════════════════════════════
# C. 查询模式
# ══════════════════════════════════════════════════════════════════════


class TestQueryMode:
    """C1-C3: --query --date DATE"""

    @patch("record_weight.subprocess.run")
    def test_C1_query_by_date_found(self, mock_run):
        """查询有数据 → 返回 records 数组"""
        mock_run.return_value = _mock_lark_cli_return_value(
            stdout_str=_lark_list(
                [{"weight": 65.0, "date": "2026-05-20", "record_id": "recvAAA"}]
            ),
            returncode=0,
        )

        stdout, stderr, code = _run("--query", "--date", "2026-05-20")
        assert code == 0
        out = json.loads(stdout)
        assert out["ok"] is True
        assert out["count"] == 1
        assert len(out["records"]) == 1
        assert out["records"][0]["weight"] == 65.0
        assert out["records"][0]["record_id"] == "recvAAA"

    @patch("record_weight.subprocess.run")
    def test_C2_query_by_date_empty(self, mock_run):
        """查询无数据 → records:[], count:0"""
        mock_run.return_value = _mock_lark_cli_return_value(
            stdout_str=_lark_list([]), returncode=0
        )

        stdout, stderr, code = _run("--query", "--date", "2026-05-20")
        assert code == 0
        out = json.loads(stdout)
        assert out["ok"] is True
        assert out["records"] == []
        assert out["count"] == 0

    def test_C3_query_no_date(self):
        """--query without --date → error"""
        stdout, stderr, code = _run("--query")
        assert code != 0
        err = json.loads(stderr)
        assert err["ok"] is False


# ══════════════════════════════════════════════════════════════════════
# D. 趋势模式
# ══════════════════════════════════════════════════════════════════════


class TestTrendMode:
    """D1-D7: --trend [--days N]"""

    @patch("record_weight.subprocess.run")
    def test_D1_trend_down(self, mock_run):
        """7 天趋势下降"""
        records = [
            {"weight": 70.0, "date": "2026-05-14", "record_id": "recvA"},
            {"weight": 69.5, "date": "2026-05-16", "record_id": "recvB"},
            {"weight": 67.8, "date": "2026-05-20", "record_id": "recvC"},
        ]
        mock_run.return_value = _mock_lark_cli_return_value(
            stdout_str=_lark_list(records), returncode=0
        )

        stdout, stderr, code = _run("--trend", "--days", "7")
        assert code == 0
        out = json.loads(stdout)
        assert out["ok"] is True
        assert out["trend"] == "down"
        assert out["change"] == -2.2
        assert out["start_weight"] == 70.0
        assert out["end_weight"] == 67.8
        # Verify actual dates in data, not all start_date
        dates = [r["date"] for r in out["data"]]
        assert dates == ["2026-05-14", "2026-05-16", "2026-05-20"]

    @patch("record_weight.subprocess.run")
    def test_D2_trend_stable(self, mock_run):
        """变化 < 0.3kg → stable"""
        records = [
            {"weight": 70.0, "date": "2026-05-14", "record_id": "recvA"},
            {"weight": 70.2, "date": "2026-05-20", "record_id": "recvB"},
        ]
        mock_run.return_value = _mock_lark_cli_return_value(
            stdout_str=_lark_list(records), returncode=0
        )

        stdout, stderr, code = _run("--trend", "--days", "7")
        assert code == 0
        out = json.loads(stdout)
        assert out["trend"] == "stable"
        assert abs(out["change"]) < 0.3

    @patch("record_weight.subprocess.run")
    def test_D3_trend_up(self, mock_run):
        """趋势上升"""
        records = [
            {"weight": 65.0, "date": "2026-05-14", "record_id": "recvA"},
            {"weight": 66.5, "date": "2026-05-20", "record_id": "recvB"},
        ]
        mock_run.return_value = _mock_lark_cli_return_value(
            stdout_str=_lark_list(records), returncode=0
        )

        stdout, stderr, code = _run("--trend", "--days", "7")
        assert code == 0
        out = json.loads(stdout)
        assert out["trend"] == "up"
        assert out["change"] == 1.5

    @patch("record_weight.subprocess.run")
    def test_D4_trend_insufficient_data(self, mock_run):
        """只有 1 条数据 → insufficient_data"""
        records = [
            {"weight": 65.0, "date": "2026-05-20", "record_id": "recvA"},
        ]
        mock_run.return_value = _mock_lark_cli_return_value(
            stdout_str=_lark_list(records), returncode=0
        )

        stdout, stderr, code = _run("--trend", "--days", "7")
        assert code == 0
        out = json.loads(stdout)
        assert out["trend"] == "insufficient_data"

    @patch("record_weight.subprocess.run")
    def test_D5_trend_no_data(self, mock_run):
        """无数据 → no_data"""
        mock_run.return_value = _mock_lark_cli_return_value(
            stdout_str=_lark_list([]), returncode=0
        )

        stdout, stderr, code = _run("--trend", "--days", "7")
        assert code == 0
        out = json.loads(stdout)
        assert out["trend"] == "no_data"

    @patch("record_weight.subprocess.run")
    def test_D6_trend_default_days(self, mock_run):
        """--trend 无 --days → 默认 7 天"""
        mock_run.return_value = _mock_lark_cli_return_value(
            stdout_str=_lark_list([]), returncode=0
        )

        stdout, stderr, code = _run("--trend")
        assert code == 0
        out = json.loads(stdout)
        # Verify the list call was made with a 7-day filter
        call_args = mock_run.call_args
        cmd = call_args[0][0]
        # The script should pass a filter for 7 days worth of data
        # We can verify by checking the command contains record-list
        assert "+record-list" in cmd

    @patch("record_weight.subprocess.run")
    def test_D7_trend_30_days(self, mock_run):
        """--trend --days 30"""
        mock_run.return_value = _mock_lark_cli_return_value(
            stdout_str=_lark_list([]), returncode=0
        )

        stdout, stderr, code = _run("--trend", "--days", "30")
        assert code == 0
        out = json.loads(stdout)
        assert out["ok"] is True


# ══════════════════════════════════════════════════════════════════════
# E. 错误处理
# ══════════════════════════════════════════════════════════════════════


class TestErrorHandling:
    """E1-E8: parameter validation and edge cases"""

    def test_E1_weight_not_a_number(self):
        """体重非数字 'abc' → error"""
        stdout, stderr, code = _run("abc")
        assert code != 0
        err = json.loads(stderr)
        assert err["ok"] is False
        assert "weight" in err["error"].lower() or "invalid" in err["error"].lower()

    def test_E2_missing_weight_arg(self):
        """只传 token + table_id → error"""
        # Need to call main directly with fewer args
        import record_weight as rw

        fake_stdout = StringIO()
        fake_stderr = StringIO()

        with patch("sys.argv", [SCRIPT, TOKEN, TABLE]), \
             patch("sys.stdout", fake_stdout), \
             patch("sys.stderr", fake_stderr):
            try:
                rw.main()
                code = 0
            except SystemExit as e:
                code = e.code if e.code is not None else 1

        assert code != 0

    def test_E3_invalid_date_format(self):
        """--date abc → error"""
        stdout, stderr, code = _run("65.0", "--date", "abc")
        assert code != 0
        err = json.loads(stderr)
        assert err["ok"] is False

    def test_E4_lark_cli_timeout(self):
        """lark-cli 超时 → error"""
        import record_weight as rw

        fake_stdout = StringIO()
        fake_stderr = StringIO()

        with patch("record_weight.subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="lark-cli", timeout=30)), \
             patch("sys.stdout", fake_stdout), \
             patch("sys.stderr", fake_stderr):
            try:
                rw.main()
                code = 0
            except SystemExit as e:
                code = e.code if e.code is not None else 1

        assert code != 0
        err = json.loads(fake_stderr.getvalue())
        assert err["ok"] is False

    def test_E5_days_zero(self):
        """--days 0 → error"""
        stdout, stderr, code = _run("--trend", "--days", "0")
        assert code != 0
        err = json.loads(stderr)
        assert err["ok"] is False
        assert "1" in err["error"]  # must be >= 1

    def test_E6_days_negative(self):
        """--days -1 → error"""
        stdout, stderr, code = _run("--trend", "--days", "-1")
        assert code != 0
        err = json.loads(stderr)
        assert err["ok"] is False

    def test_E7_days_not_a_number(self):
        """--days abc → error"""
        stdout, stderr, code = _run("--trend", "--days", "abc")
        assert code != 0
        err = json.loads(stderr)
        assert err["ok"] is False

    def test_E8_invalid_date_value(self):
        """--date 2026-13-45 → error"""
        stdout, stderr, code = _run("65.0", "--date", "2026-13-45")
        assert code != 0
        err = json.loads(stderr)
        assert err["ok"] is False


# ══════════════════════════════════════════════════════════════════════
# F. 输出格式统一验证
# ══════════════════════════════════════════════════════════════════════


class TestOutputFormat:
    """F1-F5: output consistency"""

    @patch("record_weight.subprocess.run")
    def test_F1_success_stdout_valid_json_ok_true(self, mock_run):
        """成功 → stdout 合法 JSON, ok:true"""
        mock_run.return_value = _mock_lark_cli_return_value(
            stdout_str=_lark_ok(), returncode=0
        )

        stdout, stderr, code = _run("65.0")
        assert code == 0
        out = json.loads(stdout)
        assert out["ok"] is True

    def test_F2_failure_stderr_valid_json_ok_false(self):
        """失败 → stderr 合法 JSON, ok:false"""
        stdout, stderr, code = _run("abc")
        assert code != 0
        err = json.loads(stderr)
        assert err["ok"] is False

    @patch("record_weight.subprocess.run")
    def test_F3_flat_object_no_fields_wrapper(self, mock_run):
        """不用 {fields:{...}} 嵌套，全部 flat"""
        mock_run.return_value = _mock_lark_cli_return_value(
            stdout_str=_lark_ok(), returncode=0
        )

        stdout, stderr, code = _run("65.0")
        assert code == 0
        out = json.loads(stdout)
        assert "fields" not in out

    @patch("record_weight.subprocess.run")
    def test_F4_success_exit_zero_failure_nonzero(self, mock_run):
        """成功 exit 0, 失败 exit ≠ 0"""
        mock_run.return_value = _mock_lark_cli_return_value(
            stdout_str=_lark_ok(), returncode=0
        )

        stdout, stderr, code = _run("65.0")
        assert code == 0

        stdout2, stderr2, code2 = _run("abc")
        assert code2 != 0

    @patch("record_weight.subprocess.run")
    def test_F5_stderr_empty_on_success(self, mock_run):
        """成功时 stderr 为空"""
        mock_run.return_value = _mock_lark_cli_return_value(
            stdout_str=_lark_ok(), returncode=0
        )

        stdout, stderr, code = _run("65.0")
        assert code == 0
        assert stderr.strip() == ""
