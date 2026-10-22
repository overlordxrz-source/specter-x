"""The motion features must see payload frames only.

On the SoftAP link the receiver hears two frame populations: the phone's
payload frames (the ping, ~138 B) and its null-data frames (~28 B) that keep
the association alive. They arrive at different PHY rates, and checkpoint 011
established that the CSI amplitude scale follows the rate. Mixing them would
put a rate-dependent amplitude difference into the features - a difference
that has nothing to do with a person moving.

These tests pin the selection: the boundary is explicit, the null frames are
dropped, a recording made before ``sig_len`` existed is passed through and
flagged rather than silently emptied, and the features of a filtered mixed
trial are identical to the features of a trial that only ever held payload
frames.
"""
from __future__ import annotations

import importlib.util
import math
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location(
    "esp32_csi_motion", os.path.join(REPO, "tools", "esp32_csi_motion.py"))
motion = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = motion
_spec.loader.exec_module(motion)

from specter.sensors.esp32.analysis import extract_features          # noqa: E402
from specter.sensors.esp32.experiment import trials_from_json        # noqa: E402


def _sample(i: int, sig_len: int, base: int) -> dict:
    return {
        "t": round(i * 0.1, 4), "id": 1000 + i, "rssi": -48, "channel": 6,
        "local_timestamp": 100000 + i * 100000, "sig_len": sig_len,
        "amplitudes": [float(base + (j % 7)) for j in range(64)],
    }


def _trial(label: str, samples: list) -> dict:
    return {"label": label, "actual_s": 3.0, "packets": len(samples),
            "samples": samples}


def test_the_boundary_between_null_and_payload_is_explicit():
    samples = [_sample(0, 28, 100), _sample(1, 32, 100),
               _sample(2, 33, 100), _sample(3, 138, 100)]
    out, split = motion.payload_only([_trial("hand", samples)])
    kept = [s["sig_len"] for s in out[0]["samples"]]
    assert kept == [33, 138]
    assert split["payload"] == 2
    assert split["null"] == 2


def test_the_trial_keeps_its_provenance_after_filtering():
    samples = [_sample(i, 28, 100) for i in range(4)] + \
              [_sample(i, 138, 100) for i in range(4, 9)]
    out, split = motion.payload_only([_trial("still", samples)])
    t = out[0]
    assert t["frames_total"] == 9
    assert t["payload_frames"] == 5
    assert t["packets"] == 5
    assert len(t["samples"]) == 5


def test_a_recording_without_sig_len_is_passed_through_and_flagged():
    """Old recordings must not silently become empty trials."""
    old = _trial("stationary", [
        {"t": 0.1, "id": 1, "rssi": -50, "channel": 6,
         "amplitudes": [1.0] * 64},
    ])
    out, split = motion.payload_only([old])
    assert out[0] is old
    assert len(out[0]["samples"]) == 1
    assert split["trials_without_sig_len"] == 1
    assert split["payload"] == 0 and split["null"] == 0


def test_filtering_removes_the_null_population_from_the_features():
    """The decisive property: a mixed trial and a payload-only trial give
    the same features once the filter has run."""
    payload = [_sample(i, 138, 100) for i in range(12)]
    null = [_sample(i, 28, 900) for i in range(12)]
    mixed = _trial("hand", payload + null)
    only = _trial("hand", payload)

    filtered, _ = motion.payload_only([mixed])
    f_mixed = extract_features(trials_from_json({"trials": [filtered[0]]}))[0]
    f_only = extract_features(trials_from_json({"trials": [only]}))[0]

    for name in ("roughness_used", "amp_volatility"):
        a, b = f_mixed[name], f_only[name]
        assert not math.isnan(a) and not math.isnan(b)
        assert math.isclose(a, b, rel_tol=1e-12), (name, a, b)

    # and the unfiltered trial really would have differed, so the filter is
    # doing something rather than being a no-op in this construction
    f_raw = extract_features(trials_from_json({"trials": [mixed]}))[0]
    assert not math.isclose(f_raw["amp_volatility"],
                            f_only["amp_volatility"], rel_tol=1e-3)
