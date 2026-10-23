"""Forensic checks for the Alpha 002-C raw-stream gate.

These tests exist to show that the correction which allowed the accepted
session's first startup torn line did **not** weaken any other INVALID
condition. They call the frozen ``validate_raw`` directly; they do not change
the analysis, the session or its result.
"""
from __future__ import annotations

import importlib.util
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location(
    "alpha002c_motion_v2_forensic",
    os.path.join(REPO, "tools", "alpha002c_motion_v2.py"))
v2 = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = v2
_spec.loader.exec_module(v2)

IQ = ",".join(["0", "0"] * 64)


def _line(seq: int) -> bytes:
    return (f'CSI_DATA,{seq},aa:bb:cc:dd:ee:ff,-50,11,1,6,0,1,1,0,0,0,1,'
            f'-94,0,6,0,{1000000 + seq},0,138,1,128,0,"[{IQ}]"\n').encode()


def _session(tmp_path, raw: bytes, *, malformed=0):
    p = tmp_path / "raw.bin"
    p.write_bytes(raw)
    return {"raw": str(p), "malformed": malformed,
            "clock_resets": 0, "late_frames": {}}


def test_clean_raw_is_accepted(tmp_path):
    s = _session(tmp_path, b"".join(_line(i) for i in range(3)))
    assert v2.validate_raw(s, []) == []


def test_first_startup_torn_line_is_allowed(tmp_path):
    raw = _line(1)[:50] + _line(2) + b"".join(_line(i) for i in range(3, 6))
    s = _session(tmp_path, raw, malformed=1)
    assert v2.validate_raw(s, []) == []


def test_malformed_line_after_a_valid_record_is_rejected(tmp_path):
    raw = b"".join(_line(i) for i in range(3))
    raw += (b'CSI_DATA,9,aa:bb:cc:dd:ee:ff,-50,11,1,6,0,1,1,0,0,0,1,-94,0,'
            b'SPECTER_STAT,role=softap\n')
    s = _session(tmp_path, raw)
    assert any("malformed" in p for p in v2.validate_raw(s, []))


def test_second_torn_line_is_rejected(tmp_path):
    raw = _line(1)[:50] + _line(2) + _line(3)[:50] + _line(4)
    s = _session(tmp_path, raw, malformed=1)
    assert any("malformed" in p for p in v2.validate_raw(s, []))


def test_recorder_malformed_counter_above_one_is_rejected(tmp_path):
    s = _session(tmp_path, b"".join(_line(i) for i in range(3)),
                 malformed=2)
    assert any("recorder counted" in p for p in v2.validate_raw(s, []))


def test_clock_reset_is_rejected(tmp_path):
    s = _session(tmp_path, b"".join(_line(i) for i in range(3)))
    s["clock_resets"] = 1
    assert any("clock" in p for p in v2.validate_raw(s, []))


def test_late_frame_is_rejected(tmp_path):
    s = _session(tmp_path, b"".join(_line(i) for i in range(3)))
    s["late_frames"] = {"0": 1}
    assert any("late" in p for p in v2.validate_raw(s, []))


def test_missing_raw_is_rejected(tmp_path):
    s = {"raw": str(tmp_path / "absent.bin"), "malformed": 0,
         "clock_resets": 0, "late_frames": {}}
    assert any("missing" in p for p in v2.validate_raw(s, []))


def test_empty_raw_is_rejected(tmp_path):
    s = _session(tmp_path, b"")
    assert any("empty" in p for p in v2.validate_raw(s, []))


def test_payload_shortage_is_rejected(tmp_path):
    s = _session(tmp_path, _line(1))
    trials = [{"samples": [{"sig_len": 33}] * 5}]
    assert any("CSI records" in p for p in v2.validate_raw(s, trials))
