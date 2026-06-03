#!/usr/bin/env python3
"""Unit tests for record_training.py — mock subprocess.run, no network needed.

Run:
    cd ~/.hermes/skills/fitness-coach/scripts
    pytest test_record_training.py -v
"""

import json
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from io import StringIO
from unittest.mock import patch

import pytest

CST = timezone(timedelta(hours=8))
SCRIPT = "record_training.py"
TOKEN = "test_token"
STBL = "tblSESSION"
ETBL = "tblEXERCISE"
SESSION_ID = "recvSESSION01"

EXERCISE_FIELDS = ["动作名称", "重量", "组数", "次数", "备注", "关联课次"]


# ── Helpers ──────────────────────────────────────────────────────────────


def _ts(date_str: str) -> int:
    """Millisecond timestamp for YYYY-MM-DD 00:00 CST."""
    dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=CST)
    return int(dt.timestamp() * 1000)


def _run(*args):
    """Run record_training.py in-process, return (stdout, stderr, exitcode)."""
    import record_training as rt

    argv = [SCRIPT, TOKEN, STBL, ETBL] + list(args)

    fake_stdout = StringIO()
    fake_stderr = StringIO()

    with patch("sys.argv", argv), \
         patch("sys.stdout", fake_stdout), \
         patch("sys.stderr", fake_stderr):
        try:
            rt.main()
            exitcode = 0
        except SystemExit as e:
            exitcode = e.code if e.code is not None else 1

    return fake_stdout.getvalue(), fake_stderr.getvalue(), exitcode


def _mock_run(stdout="", stderr="", returncode=0):
    """Create a mock subprocess.run return value."""
    return subprocess.CompletedProcess(
        args=[], returncode=returncode,
        stdout=stdout, stderr=stderr,
    )


# ── lark-cli response builders ──────────────────────────────────────────


def _lark_field_list(fields):
    """+field-list response. fields: list of field dicts."""
    return json.dumps({"ok": True, "data": {"fields": fields}})


def _session_field_list(theme_options=None):
    """+field-list for session table with standard fields."""
    return _lark_field_list([
        {"id": "fldTheme", "name": "训练主题", "type": "select",
         "multiple": True, "options": theme_options or []},
        {"id": "fldName", "name": "会员姓名", "type": "text"},
        {"id": "fldDate", "name": "训练日期", "type": "datetime"},
        {"id": "fldNotes", "name": "教练备注", "type": "text"},
    ])


def _exercise_field_list(exercise_options=None):
    """+field-list for exercise table with standard fields."""
    return _lark_field_list([
        {"id": "fldExName", "name": "动作名称", "type": "select",
         "options": exercise_options or []},
        {"id": "fldWeight", "name": "重量", "type": "number"},
        {"id": "fldSets", "name": "组数", "type": "number"},
        {"id": "fldReps", "name": "次数", "type": "number"},
        {"id": "fldNotes", "name": "备注", "type": "text"},
        {"id": "fldLink", "name": "关联课次", "type": "link"},
    ])


def _lark_field_update_ok():
    """+field-update success response."""
    return json.dumps({"ok": True})


def _lark_upsert_ok(record_id=None):
    """+record-upsert success response."""
    return json.dumps({
        "ok": True,
        "data": {
            "created": True,
            "record": {
                "data": [], "field_id_list": [], "fields": [],
                "record_id_list": [record_id or "recvEX01"],
            },
        },
    })


def _lark_delete_ok():
    """+record-delete success response."""
    return json.dumps({"ok": True})


def _lark_record_list(records=None, fields=None):
    """+record-list response.

    records: list of dicts with values keyed by field name + "record_id".
    fields: column names (default EXERCISE_FIELDS).
    """
    if fields is None:
        fields = EXERCISE_FIELDS
    if records is None:
        records = []
    rows = []
    rids = []
    for r in records:
        rows.append([r.get(f, "") for f in fields])
        rids.append(r.get("record_id", ""))
    return json.dumps({
        "ok": True,
        "data": {
            "data": rows, "fields": fields,
            "record_id_list": rids,
        },
    })


def _lark_error(msg="internal error"):
    """lark-cli error response (non-zero returncode or ok:false)."""
    return json.dumps({"ok": False, "error": {"code": 999, "message": msg}})


def _extract_payload(mock_call):
    """Extract --json payload from a mock subprocess.run call."""
    cmd = mock_call[0][0]
    try:
        idx = cmd.index("--json") + 1
        return json.loads(cmd[idx])
    except (ValueError, IndexError):
        raise AssertionError(f"Mock call has no --json argument: {cmd}")


# ══════════════════════════════════════════════════════════════════════════
# A. Write mode (14 tests)
# ══════════════════════════════════════════════════════════════════════════


class TestWriteMode:
    """A1-A14: record_training.py TOKEN STBL ETBL name date theme exercises"""

    @patch("record_training.subprocess.run")
    def test_A1_single_exercise_existing_theme(self, mock_run):
        """1 action, theme already in options → payload correct."""
        mock_run.side_effect = [
            # 1. field-list session (theme exists)
            _mock_run(stdout=_session_field_list([{"name": "胸", "hue": "Red"}])),
            # 2. upsert session
            _mock_run(stdout=_lark_upsert_ok(SESSION_ID)),
            # 3. field-list exercise (action exists)
            _mock_run(stdout=_exercise_field_list([{"name": "卧推", "hue": "Blue"}])),
            # 4. upsert exercise
            _mock_run(stdout=_lark_upsert_ok("recvEX01")),
        ]

        exercises = json.dumps([{"name": "卧推", "weight": 100, "reps": 15, "sets": 5}])
        stdout, stderr, code = _run("张三", "2026-05-24", "胸", exercises)
        assert code == 0
        out = json.loads(stdout)
        assert out["ok"] is True
        assert out["session_id"] == SESSION_ID
        assert out["exercises_written"] == 1
        assert out["exercises_failed"] == 0

        # Verify session payload
        sp = _extract_payload(mock_run.call_args_list[1])
        assert sp["会员姓名"] == "张三"
        assert sp["训练日期"] == _ts("2026-05-24")
        assert sp["训练主题"] == ["胸"]

        # Verify exercise payload
        ep = _extract_payload(mock_run.call_args_list[3])
        assert ep["动作名称"] == "卧推"
        assert ep["重量"] == 100
        assert ep["组数"] == 5
        assert ep["次数"] == 15
        assert ep["关联课次"] == SESSION_ID

    @patch("record_training.subprocess.run")
    def test_A2_multiple_exercises(self, mock_run):
        """3 actions, all existing options → 3 exercise upserts."""
        mock_run.side_effect = [
            _mock_run(stdout=_session_field_list([{"name": "上肢", "hue": "Blue"}])),
            _mock_run(stdout=_lark_upsert_ok(SESSION_ID)),
            _mock_run(stdout=_exercise_field_list([
                {"name": "高位下拉", "hue": "Blue"},
                {"name": "坐姿划船", "hue": "Blue"},
                {"name": "二头弯举", "hue": "Blue"},
            ])),
            _mock_run(stdout=_lark_upsert_ok("recvEX01")),
            _mock_run(stdout=_lark_upsert_ok("recvEX02")),
            _mock_run(stdout=_lark_upsert_ok("recvEX03")),
        ]

        exercises = json.dumps([
            {"name": "高位下拉", "weight": 45, "sets": 4, "reps": 12},
            {"name": "坐姿划船", "weight": 56, "sets": 4, "reps": 12},
            {"name": "二头弯举", "weight": 12, "sets": 3, "reps": 15},
        ])
        stdout, _, code = _run("李四", "2026-05-24", "上肢", exercises)
        assert code == 0
        out = json.loads(stdout)
        assert out["exercises_written"] == 3
        assert out["exercises_failed"] == 0
        assert len(out["results"]) == 3

        # Verify all 3 exercises linked to same session
        for i in range(3):
            ep = _extract_payload(mock_run.call_args_list[3 + i])
            assert ep["关联课次"] == SESSION_ID

    @patch("record_training.subprocess.run")
    def test_A3_explicit_theme_passthrough(self, mock_run):
        """Theme passed directly → no inference, write as-is."""
        mock_run.side_effect = [
            _mock_run(stdout=_session_field_list([{"name": "上肢", "hue": "Blue"}])),
            _mock_run(stdout=_lark_upsert_ok(SESSION_ID)),
            _mock_run(stdout=_exercise_field_list([{"name": "卧推", "hue": "Blue"}])),
            _mock_run(stdout=_lark_upsert_ok("recvEX01")),
        ]

        exercises = json.dumps([{"name": "卧推", "weight": 100, "sets": 4, "reps": 12}])
        stdout, _, code = _run("张三", "2026-05-24", "上肢", exercises)
        assert code == 0
        out = json.loads(stdout)
        assert out["theme"] == "上肢"

        sp = _extract_payload(mock_run.call_args_list[1])
        assert sp["训练主题"] == ["上肢"]

    @patch("record_training.subprocess.run")
    def test_A4_new_theme_auto_add(self, mock_run):
        """Theme '肩膀' not in options → field-update then upsert."""
        mock_run.side_effect = [
            # 1. field-list session (肩膀 not found)
            _mock_run(stdout=_session_field_list([{"name": "胸", "hue": "Red"}])),
            # 2. field-update session (add 肩膀)
            _mock_run(stdout=_lark_field_update_ok()),
            # 3. upsert session
            _mock_run(stdout=_lark_upsert_ok(SESSION_ID)),
            # 4. field-list exercise
            _mock_run(stdout=_exercise_field_list([{"name": "推肩", "hue": "Blue"}])),
            # 5. upsert exercise
            _mock_run(stdout=_lark_upsert_ok("recvEX01")),
        ]

        exercises = json.dumps([{"name": "推肩", "weight": 20, "sets": 4, "reps": 12}])
        stdout, _, code = _run("张三", "2026-05-24", "肩膀", exercises)
        assert code == 0

        # Verify field-update payload preserves existing options
        update_payload = _extract_payload(mock_run.call_args_list[1])
        option_names = [o["name"] for o in update_payload["options"]]
        assert "胸" in option_names
        assert "肩膀" in option_names

    @patch("record_training.subprocess.run")
    def test_A5_new_exercise_auto_add(self, mock_run):
        """Exercise '龙门架夹胸' not in options → field-update then write."""
        mock_run.side_effect = [
            _mock_run(stdout=_session_field_list([{"name": "胸", "hue": "Red"}])),
            _mock_run(stdout=_lark_upsert_ok(SESSION_ID)),
            # 3. field-list exercise (龙门架夹胸 missing)
            _mock_run(stdout=_exercise_field_list([{"name": "卧推", "hue": "Blue"}])),
            # 4. field-update exercise (add 龙门架夹胸)
            _mock_run(stdout=_lark_field_update_ok()),
            # 5. upsert exercise
            _mock_run(stdout=_lark_upsert_ok("recvEX01")),
        ]

        exercises = json.dumps([{"name": "龙门架夹胸", "weight": 30, "sets": 3, "reps": 15}])
        stdout, _, code = _run("张三", "2026-05-24", "胸", exercises)
        assert code == 0
        out = json.loads(stdout)
        assert out["exercises_written"] == 1

        # Verify field-update payload preserves existing and adds new
        update_payload = _extract_payload(mock_run.call_args_list[3])
        option_names = [o["name"] for o in update_payload["options"]]
        assert "卧推" in option_names
        assert "龙门架夹胸" in option_names

    @patch("record_training.subprocess.run")
    def test_A6_mixed_old_new_exercises(self, mock_run):
        """卧推 (existing) + 龙门架夹胸 (new) → only add new option."""
        mock_run.side_effect = [
            _mock_run(stdout=_session_field_list([{"name": "胸", "hue": "Red"}])),
            _mock_run(stdout=_lark_upsert_ok(SESSION_ID)),
            # field-list exercise: 卧推 exists, 龙门架夹胸 missing
            _mock_run(stdout=_exercise_field_list([{"name": "卧推", "hue": "Blue"}])),
            # field-update: add only 龙门架夹胸
            _mock_run(stdout=_lark_field_update_ok()),
            # upsert 卧推
            _mock_run(stdout=_lark_upsert_ok("recvEX01")),
            # upsert 龙门架夹胸
            _mock_run(stdout=_lark_upsert_ok("recvEX02")),
        ]

        exercises = json.dumps([
            {"name": "卧推", "weight": 100, "sets": 4, "reps": 12},
            {"name": "龙门架夹胸", "weight": 30, "sets": 3, "reps": 15},
        ])
        stdout, _, code = _run("张三", "2026-05-24", "胸", exercises)
        assert code == 0
        out = json.loads(stdout)
        assert out["exercises_written"] == 2

        # Verify only 龙门架夹胸 added (卧推 not duplicated)
        update_payload = _extract_payload(mock_run.call_args_list[3])
        names = [o["name"] for o in update_payload["options"]]
        assert names.count("卧推") == 1  # original only
        assert "龙门架夹胸" in names

    @patch("record_training.subprocess.run")
    def test_A7_bodyweight_exercise(self, mock_run):
        """自重动作 (引体向上) without weight → payload weight=0, no error."""
        mock_run.side_effect = [
            _mock_run(stdout=_session_field_list([{"name": "上肢", "hue": "Blue"}])),
            _mock_run(stdout=_lark_upsert_ok(SESSION_ID)),
            _mock_run(stdout=_exercise_field_list([{"name": "引体向上", "hue": "Blue"}])),
            _mock_run(stdout=_lark_upsert_ok("recvEX01")),
        ]

        exercises = json.dumps([{"name": "引体向上", "sets": 3, "reps": 10}])
        stdout, _, code = _run("张三", "2026-05-24", "上肢", exercises)
        assert code == 0
        out = json.loads(stdout)
        assert out["exercises_written"] == 1

        ep = _extract_payload(mock_run.call_args_list[3])
        assert ep["重量"] == 0

    @patch("record_training.subprocess.run")
    def test_A8_specific_date(self, mock_run):
        """--date 2026-05-20 → timestamp matches, returned date correct."""
        mock_run.side_effect = [
            _mock_run(stdout=_session_field_list([{"name": "胸", "hue": "Red"}])),
            _mock_run(stdout=_lark_upsert_ok(SESSION_ID)),
            _mock_run(stdout=_exercise_field_list([{"name": "卧推", "hue": "Blue"}])),
            _mock_run(stdout=_lark_upsert_ok("recvEX01")),
        ]

        exercises = json.dumps([{"name": "卧推", "weight": 100, "sets": 4, "reps": 12}])
        stdout, _, code = _run("张三", "2026-05-20", "胸", exercises)
        assert code == 0
        out = json.loads(stdout)
        assert out["date"] == "2026-05-20"

        sp = _extract_payload(mock_run.call_args_list[1])
        assert sp["训练日期"] == _ts("2026-05-20")

    @patch("record_training.subprocess.run")
    def test_A9_with_coach_notes(self, mock_run):
        """--coach-notes '今天状态不错' → payload contains 教练备注."""
        mock_run.side_effect = [
            _mock_run(stdout=_session_field_list([{"name": "胸", "hue": "Red"}])),
            _mock_run(stdout=_lark_upsert_ok(SESSION_ID)),
            _mock_run(stdout=_exercise_field_list([{"name": "卧推", "hue": "Blue"}])),
            _mock_run(stdout=_lark_upsert_ok("recvEX01")),
        ]

        exercises = json.dumps([{"name": "卧推", "weight": 100, "sets": 4, "reps": 12}])
        stdout, _, code = _run("张三", "2026-05-24", "胸", exercises,
                                "--coach-notes", "今天状态不错")
        assert code == 0

        sp = _extract_payload(mock_run.call_args_list[1])
        assert sp["教练备注"] == "今天状态不错"

    @patch("record_training.subprocess.run")
    def test_A10_with_exercise_notes(self, mock_run):
        """Exercise notes='自重1分钟' → payload contains 备注."""
        mock_run.side_effect = [
            _mock_run(stdout=_session_field_list([{"name": "核心", "hue": "Blue"}])),
            _mock_run(stdout=_lark_upsert_ok(SESSION_ID)),
            _mock_run(stdout=_exercise_field_list([{"name": "平板支撑", "hue": "Blue"}])),
            _mock_run(stdout=_lark_upsert_ok("recvEX01")),
        ]

        exercises = json.dumps([{"name": "平板支撑", "sets": 3, "reps": 1, "notes": "自重1分钟"}])
        stdout, _, code = _run("张三", "2026-05-24", "核心", exercises)
        assert code == 0

        ep = _extract_payload(mock_run.call_args_list[3])
        assert ep["备注"] == "自重1分钟"

    @patch("record_training.subprocess.run")
    def test_A11_partial_failure(self, mock_run):
        """2nd exercise fails → written=1, failed=1, first succeeds."""
        mock_run.side_effect = [
            _mock_run(stdout=_session_field_list([{"name": "胸", "hue": "Red"}])),
            _mock_run(stdout=_lark_upsert_ok(SESSION_ID)),
            _mock_run(stdout=_exercise_field_list([
                {"name": "卧推", "hue": "Blue"},
                {"name": "夹胸", "hue": "Blue"},
            ])),
            # 1st exercise OK
            _mock_run(stdout=_lark_upsert_ok("recvEX01")),
            # 2nd exercise FAIL (lark-cli returns non-zero)
            _mock_run(stdout="", stderr=_lark_error("permission denied"), returncode=1),
        ]

        exercises = json.dumps([
            {"name": "卧推", "weight": 100, "sets": 4, "reps": 12},
            {"name": "夹胸", "weight": 30, "sets": 3, "reps": 15},
        ])
        stdout, _, code = _run("张三", "2026-05-24", "胸", exercises)
        assert code == 0
        out = json.loads(stdout)
        assert out["exercises_written"] == 1
        assert out["exercises_failed"] == 1
        assert out["results"][0]["ok"] is True
        assert out["results"][0]["record_id"] == "recvEX01"
        assert out["results"][1]["ok"] is False
        assert "error" in out["results"][1]

    @patch("record_training.subprocess.run")
    def test_A12_ten_exercises(self, mock_run):
        """10 exercises → all written successfully."""
        mock_run.side_effect = [
            _mock_run(stdout=_session_field_list([{"name": "胸", "hue": "Red"}])),
            _mock_run(stdout=_lark_upsert_ok(SESSION_ID)),
            _mock_run(stdout=_exercise_field_list([
                {"name": f"动作{i}", "hue": "Blue"} for i in range(10)
            ])),
        ] + [
            _mock_run(stdout=_lark_upsert_ok(f"recvEX{i:02d}"))
            for i in range(10)
        ]

        exercises = json.dumps([
            {"name": f"动作{i}", "weight": 10 * i, "sets": 4, "reps": 12}
            for i in range(10)
        ])
        stdout, _, code = _run("张三", "2026-05-24", "胸", exercises)
        assert code == 0
        out = json.loads(stdout)
        assert out["exercises_written"] == 10
        assert out["exercises_failed"] == 0
        assert len(out["results"]) == 10
        for r in out["results"]:
            assert r["ok"] is True
            assert "record_id" in r

    @patch("record_training.subprocess.run")
    def test_A13_coach_notes_empty_omitted(self, mock_run):
        """--coach-notes '' → payload does NOT contain 教练备注 field."""
        mock_run.side_effect = [
            _mock_run(stdout=_session_field_list([{"name": "胸", "hue": "Red"}])),
            _mock_run(stdout=_lark_upsert_ok(SESSION_ID)),
            _mock_run(stdout=_exercise_field_list([{"name": "卧推", "hue": "Blue"}])),
            _mock_run(stdout=_lark_upsert_ok("recvEX01")),
        ]

        exercises = json.dumps([{"name": "卧推", "weight": 100, "sets": 4, "reps": 12}])
        # Pass empty string for coach-notes
        stdout, _, code = _run("张三", "2026-05-24", "胸", exercises,
                                "--coach-notes", "")
        assert code == 0

        sp = _extract_payload(mock_run.call_args_list[1])
        assert "教练备注" not in sp

    @patch("record_training.subprocess.run")
    def test_A14_future_date_rejected(self, mock_run):
        """--date 2027-01-01 → error, no lark-cli calls."""
        exercises = json.dumps([{"name": "卧推", "weight": 100, "sets": 4, "reps": 12}])
        stdout, stderr, code = _run("张三", "2027-01-01", "胸", exercises)
        assert code != 0
        err = json.loads(stderr)
        assert err["ok"] is False
        assert "未来" in err["error"] or "日期" in err["error"]
        # No lark-cli calls should have been made
        mock_run.assert_not_called()


# ══════════════════════════════════════════════════════════════════════════
# B. Delete mode (7 tests)
# ══════════════════════════════════════════════════════════════════════════


class TestDeleteMode:
    """B1-B7: --delete / --delete-exercise"""

    @patch("record_training.subprocess.run")
    def test_B1_delete_session_cascade(self, mock_run):
        """Delete session with 3 linked exercises → delete all."""
        mock_run.side_effect = [
            # 1. record-list: find linked exercises
            _mock_run(stdout=_lark_record_list([
                {"动作名称": "卧推", "关联课次": SESSION_ID, "record_id": "recvEX01"},
                {"动作名称": "夹胸", "关联课次": SESSION_ID, "record_id": "recvEX02"},
                {"动作名称": "飞鸟", "关联课次": SESSION_ID, "record_id": "recvEX03"},
            ])),
            # 2-4. delete 3 exercises
            _mock_run(stdout=_lark_delete_ok()),
            _mock_run(stdout=_lark_delete_ok()),
            _mock_run(stdout=_lark_delete_ok()),
            # 5. delete session
            _mock_run(stdout=_lark_delete_ok()),
        ]

        stdout, _, code = _run("--delete", "--session-id", SESSION_ID)
        assert code == 0
        out = json.loads(stdout)
        assert out["ok"] is True
        assert out["deleted_session"] == SESSION_ID
        assert out["deleted_exercises"] == 3
        assert set(out["deleted_exercise_ids"]) == {"recvEX01", "recvEX02", "recvEX03"}

    @patch("record_training.subprocess.run")
    def test_B2_delete_nonexistent_session(self, mock_run):
        """Session not found (no linked exercises) → still attempt delete."""
        mock_run.side_effect = [
            # record-list: no linked exercises
            _mock_run(stdout=_lark_record_list([])),
            # delete session
            _mock_run(stdout=_lark_delete_ok()),
        ]

        stdout, _, code = _run("--delete", "--session-id", "recvNOTEXIST")
        assert code == 0
        out = json.loads(stdout)
        assert out["deleted_exercises"] == 0
        assert out["deleted_exercise_ids"] == []

    @patch("record_training.subprocess.run")
    def test_B3_delete_missing_session_id(self, mock_run):
        """--delete without --session-id → error."""
        stdout, stderr, code = _run("--delete")
        assert code != 0
        err = json.loads(stderr)
        assert err["ok"] is False
        mock_run.assert_not_called()

    @patch("record_training.subprocess.run")
    def test_B4_delete_lark_failure(self, mock_run):
        """+record-delete fails → stderr error."""
        mock_run.side_effect = [
            _mock_run(stdout=_lark_record_list([
                {"动作名称": "卧推", "关联课次": SESSION_ID, "record_id": "recvEX01"},
            ])),
            _mock_run(stdout="", stderr="permission denied", returncode=1),
        ]

        stdout, stderr, code = _run("--delete", "--session-id", SESSION_ID)
        assert code != 0
        err = json.loads(stderr)
        assert err["ok"] is False

    @patch("record_training.subprocess.run")
    def test_B5_delete_single_exercise(self, mock_run):
        """--delete-exercise --record-id → direct delete, no cascade."""
        mock_run.return_value = _mock_run(stdout=_lark_delete_ok())

        stdout, _, code = _run("--delete-exercise", "--record-id", "recvEX01")
        assert code == 0
        out = json.loads(stdout)
        assert out["ok"] is True
        assert out["deleted_exercise"] == "recvEX01"

        # Only 1 call (no record-list or session delete)
        assert mock_run.call_count == 1
        cmd = mock_run.call_args[0][0]
        assert "+record-delete" in cmd
        assert "recvEX01" in cmd

    @patch("record_training.subprocess.run")
    def test_B6_delete_nonexistent_exercise(self, mock_run):
        """--delete-exercise with non-existent record_id → lark error."""
        mock_run.return_value = _mock_run(
            stdout=_lark_error("record not found"), returncode=1
        )

        stdout, stderr, code = _run("--delete-exercise", "--record-id", "recvNOTEXIST")
        assert code != 0
        err = json.loads(stderr)
        assert err["ok"] is False

    def test_B7_delete_flags_conflict(self):
        """--delete AND --delete-exercise → error, no lark calls."""
        stdout, stderr, code = _run("--delete", "--session-id", "recv01",
                                     "--delete-exercise", "--record-id", "recv02")
        assert code != 0
        err = json.loads(stderr)
        assert err["ok"] is False
        assert "二选一" in err["error"]


# ══════════════════════════════════════════════════════════════════════════
# C. Query mode (3 tests)
# ══════════════════════════════════════════════════════════════════════════


class TestQueryMode:
    """C1-C3: --query --session-id"""

    @patch("record_training.subprocess.run")
    def test_C1_query_with_results(self, mock_run):
        """Session has 2 linked exercises → return both."""
        mock_run.return_value = _mock_run(stdout=_lark_record_list([
            {"动作名称": "卧推", "重量": 100, "组数": 4, "次数": 12,
             "备注": "", "关联课次": SESSION_ID, "record_id": "recvEX01"},
            {"动作名称": "夹胸", "重量": 30, "组数": 3, "次数": 15,
             "备注": "慢放", "关联课次": SESSION_ID, "record_id": "recvEX02"},
            {"动作名称": "深蹲", "重量": 60, "组数": 4, "次数": 10,
             "备注": "", "关联课次": "recvOTHER", "record_id": "recvEX99"},
        ]))

        stdout, _, code = _run("--query", "--session-id", SESSION_ID)
        assert code == 0
        out = json.loads(stdout)
        assert out["ok"] is True
        assert out["session_id"] == SESSION_ID
        assert out["exercise_count"] == 2
        assert len(out["exercises"]) == 2
        # Verify correct exercises returned (not 深蹲 which belongs to other session)
        names = [e["name"] for e in out["exercises"]]
        assert "卧推" in names
        assert "夹胸" in names
        assert "深蹲" not in names
        # Verify notes preserved
        jiaxiong = [e for e in out["exercises"] if e["name"] == "夹胸"][0]
        assert jiaxiong["notes"] == "慢放"

    @patch("record_training.subprocess.run")
    def test_C2_query_no_results(self, mock_run):
        """Session has no linked exercises → empty list."""
        mock_run.return_value = _mock_run(stdout=_lark_record_list([
            {"动作名称": "深蹲", "重量": 60, "组数": 4, "次数": 10,
             "备注": "", "关联课次": "recvOTHER", "record_id": "recvEX99"},
        ]))

        stdout, _, code = _run("--query", "--session-id", SESSION_ID)
        assert code == 0
        out = json.loads(stdout)
        assert out["exercise_count"] == 0
        assert out["exercises"] == []

    def test_C3_query_missing_session_id(self):
        """--query without --session-id → error."""
        stdout, stderr, code = _run("--query")
        assert code != 0
        err = json.loads(stderr)
        assert err["ok"] is False


# ══════════════════════════════════════════════════════════════════════════
# D. Error handling (6 tests)
# ══════════════════════════════════════════════════════════════════════════


class TestErrorHandling:
    """D1-D6: various error conditions"""

    def test_D1_invalid_exercises_json(self):
        """Exercises param is not valid JSON."""
        stdout, stderr, code = _run("张三", "2026-05-24", "胸", "not-json{{{")
        assert code != 0
        err = json.loads(stderr)
        assert err["ok"] is False
        assert "JSON" in err["error"]

    def test_D2_empty_exercises_list(self):
        """Exercises is '[]' → error."""
        stdout, stderr, code = _run("张三", "2026-05-24", "胸", "[]")
        assert code != 0
        err = json.loads(stderr)
        assert err["ok"] is False

    def test_D3_invalid_date(self):
        """Date 'abc' → error."""
        stdout, stderr, code = _run("张三", "abc", "胸",
                                     '[{"name":"卧推","weight":100,"sets":4,"reps":12}]')
        assert code != 0
        err = json.loads(stderr)
        assert err["ok"] is False
        assert "日期" in err["error"] or "date" in err["error"].lower()

    @patch("record_training.subprocess.run")
    def test_D4_lark_timeout(self, mock_run):
        """lark-cli times out → stderr error."""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="lark-cli", timeout=30)

        exercises = json.dumps([{"name": "卧推", "weight": 100, "sets": 4, "reps": 12}])
        stdout, stderr, code = _run("张三", "2026-05-24", "胸", exercises)
        assert code != 0
        err = json.loads(stderr)
        assert err["ok"] is False
        assert "timed" in err["error"].lower()

    def test_D5_missing_required_args(self):
        """Only token, missing table_ids and write args."""
        # _run always prepends TOKEN STBL ETBL, so test with fewer positional
        stdout, stderr, code = _run()
        assert code != 0
        err = json.loads(stderr)
        assert err["ok"] is False

    @patch("record_training.subprocess.run")
    def test_D6_field_list_bad_format(self, mock_run):
        """+field-list returns fields as non-list → error."""
        mock_run.return_value = _mock_run(
            stdout=json.dumps({"ok": True, "data": {"fields": "not_a_list"}})
        )

        exercises = json.dumps([{"name": "卧推", "weight": 100, "sets": 4, "reps": 12}])
        stdout, stderr, code = _run("张三", "2026-05-24", "胸", exercises)
        assert code != 0
        err = json.loads(stderr)
        assert err["ok"] is False
        assert "field-list" in err["error"].lower() or "format" in err["error"].lower()


