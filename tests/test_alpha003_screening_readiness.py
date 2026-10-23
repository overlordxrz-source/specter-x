"""Software-only rehearsal for the frozen Alpha 003 screening.

The real screening is not run here. A fake serial source drives the real
recorder for short trials so the plan, cue order, empty-trial accounting and
evidence files are exercised without touching hardware or a subject.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys
import time
import types
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from specter.sensors.esp32.presence import trial_qc  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "alpha003_motion_recorder", REPO / "tools" / "esp32_csi_motion.py")
motion = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = motion
_spec.loader.exec_module(motion)


def _line(seq: int, ts_us: int) -> bytes:
    iq = ",".join(["0", "0", "3", "4"] * 32)
    return (f'CSI_DATA,{seq},de:1c:7e:d8:26:70,-50,11,1,6,0,1,1,0,0,0,1,'
            f'-94,0,6,0,{ts_us},0,138,1,128,0,"[{iq}]"\n').encode()


class FakeSerial:
    """A pyserial-shaped source emitting one deterministic frame every 20 ms."""

    def __init__(self, *args, **kwargs):
        self.start = time.monotonic()
        self.next = self.start
        self.seq = 0
        self.closed = False

    @property
    def in_waiting(self) -> int:
        return 1 if time.monotonic() >= self.next else 0

    def read(self, n: int) -> bytes:
        if time.monotonic() < self.next:
            return b""
        now = time.monotonic()
        self.next = now + 0.02
        ts = int((now - self.start) * 1e6) + 1_000_000
        line = _line(self.seq, ts)
        self.seq += 1
        return line

    def close(self) -> None:
        self.closed = True


def _fake_serial_module() -> types.ModuleType:
    mod = types.ModuleType("serial")

    def serial_factory(*args, **kwargs):
        return FakeSerial()

    mod.Serial = serial_factory
    return mod


def test_screening_plan_accounting_cues_empty_trials_and_evidence(tmp_path,
                                                                  monkeypatch):
    calls = []
    busy = False

    def fake_speak(text: str, *, wait: bool) -> None:
        nonlocal busy
        if wait:
            assert not busy, "blocking cue overlapped an active cue"
            busy = True
            calls.append((text, "block"))
            busy = False
        else:
            assert not busy, "go overlapped the explanation"
            calls.append((text, "go"))

    monkeypatch.setattr(motion, "_speak", fake_speak)
    monkeypatch.setitem(sys.modules, "serial", _fake_serial_module())

    out = tmp_path / "session.json"
    args = SimpleNamespace(
        port="fake", trial=["empty:0.2", "stationary:0.2", "walking:0.2"],
        repeats=6, shuffle=True, seed=20261024, lead_in=0.0, cue=True,
        guard=0.10, max_gap=0.5, consent="rehearsal; no human subject",
        raw_out=str(out) + ".raw", out=str(out), prompt=False,
        announce=False)
    assert motion.cmd_record(args) == 0

    session = json.loads(out.read_text())
    trials = session["trials"]
    assert len(trials) == 18
    assert len(session["design"]["trial_order"]) == 18
    assert session["design"]["seed"] == 20261024
    assert session["design"]["repeats"] == 6
    assert session["design"]["lead_in_s"] == 0.0
    assert session["design"]["blocks"] == [b for b in range(6) for _ in range(3)]
    counts = {label: sum(1 for t in trials if t["label"] == label)
              for label in ("empty", "stationary", "walking")}
    assert counts == {"empty": 6, "stationary": 6, "walking": 6}
    for block in range(6):
        labels = [t["label"] for t in trials if t["block"] == block]
        assert sorted(labels) == ["empty", "stationary", "walking"]
    assert all(t["requested_s"] == 0.2 for t in trials)

    # Cue sequence: one blocking explanation, one go, one blocking stop per
    # trial; no async go during an explanation.
    assert len(calls) == 54
    assert all(kind == "block" for _, kind in calls[0::3])
    assert all(kind == "go" for _, kind in calls[1::3])
    assert all(kind == "block" for _, kind in calls[2::3])
    assert any("Leave the room" in text for text, _ in calls)
    assert any("Walk" in text for text, _ in calls)

    # Evidence is written and self-describing; no file is silently empty.
    raw = Path(session["raw"])
    jsonl = Path(session["trials_jsonl"])
    assert raw.exists() and raw.stat().st_size > 0
    assert jsonl.exists() and len(jsonl.read_text().splitlines()) == 18
    assert raw.read_bytes().count(b"CSI_DATA") >= 18
    hashes = {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in (out, raw, jsonl)}
    assert all(len(h) == 64 for h in hashes.values())
    assert hashes[str(out)] == hashlib.sha256(out.read_bytes()).hexdigest()


def test_screening_trial_qc_uses_the_twenty_second_gate():
    good = {
        "label": "empty", "active_s": 20.0, "max_sensor_gap_s": 0.1,
        "boundary_uncertainty_s": 0.03, "clock_resets": 0,
        "late_frames": 0, "valid": True,
        "samples": [{"sig_len": 138}] * 180,
    }
    assert trial_qc(good, requested_s=20.0, min_payload=180) == []
    bad = dict(good)
    bad["samples"] = [{"sig_len": 138}] * 179
    assert any("payload" in p for p in
               trial_qc(bad, requested_s=20.0, min_payload=180))
