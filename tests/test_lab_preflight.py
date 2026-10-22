"""The preflight must be able to say FAIL, and must not say PASS by accident.

The tool in ``tools/esp32_lab_preflight.py`` is run once, on hardware, at a
moment when a wrong answer is expensive. Its scoring logic is therefore
tested here against observations that are built by hand: a healthy link, a
link whose callback never fires (the SoftAP question), a link with a USB
stall, and a link with the wrong subcarrier map.
"""
from __future__ import annotations

import importlib.util
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location(
    "esp32_lab_preflight", os.path.join(REPO, "tools", "esp32_lab_preflight.py"))
preflight = importlib.util.module_from_spec(_spec)
# dataclasses resolves the module by name, so it has to be registered first
sys.modules[_spec.name] = preflight
_spec.loader.exec_module(preflight)

Observation = preflight.Observation
evaluate = preflight.evaluate
verdict = preflight.verdict


def _healthy(**over):
    st0 = {"csi_callbacks": 1000, "printed": 990, "dropped_old": 0,
           "dropped_new": 0, "channel": 6, "rssi": -55}
    st1 = {"csi_callbacks": 2200, "printed": 2190, "dropped_old": 0,
           "dropped_new": 0, "channel": 6, "rssi": -56}
    obs = Observation(
        seconds=60.0, csi_count=1200, malformed=0, status_lines=60,
        first_status=st0, last_status=st1,
        rssi=[-55.0] * 1200, noise_floor=[-96.0] * 1200,
        channels=[6] * 1200, rate_histogram={"11": 1200},
        used_carrier_ok=1200, used_carrier_checked=1200,
        max_gap_s=0.05, seq_gaps=0, usb_bytes=1_000_000,
        console_bytes=1_000_500, expected_rate_hz=20.0)
    for k, v in over.items():
        setattr(obs, k, v)
    return obs


def test_a_healthy_link_passes():
    results = evaluate(_healthy())
    assert verdict(results) == "PASS"
    assert not [r for r in results if r.status == "FAIL"]


def test_the_softap_question_fails_loudly_when_the_callback_never_fires():
    """If csi_cb does not move, the tool must say FAIL, not 'no data'."""
    obs = _healthy(first_status={"csi_callbacks": 0, "printed": 0,
                                 "dropped_old": 0, "dropped_new": 0},
                   last_status={"csi_callbacks": 0, "printed": 0,
                                "dropped_old": 0, "dropped_new": 0},
                   csi_count=0, rssi=[], noise_floor=[], channels=[],
                   used_carrier_checked=0, used_carrier_ok=0,
                   rate_histogram={}, max_gap_s=0.0)
    results = evaluate(obs)
    by = {r.name: r for r in results}
    assert by["csi callback fires at all"].status == "FAIL"
    assert by["csi callback activity"].status == "FAIL"
    assert verdict(results) == "FAIL"


def test_a_usb_stall_fails_on_the_gap_not_on_silence():
    results = evaluate(_healthy(max_gap_s=3.5, csi_count=600))
    by = {r.name: r for r in results}
    assert by["longest inter-packet gap"].status == "FAIL"
    assert by["packet continuity"].status == "FAIL"   # 10/s against 20/s
    assert verdict(results) == "FAIL"


def test_device_queue_loss_fails_even_when_the_stream_looks_fine():
    st1 = {"csi_callbacks": 2200, "printed": 2190, "dropped_old": 12,
           "dropped_new": 0}
    results = evaluate(_healthy(last_status=st1))
    by = {r.name: r for r in results}
    assert by["device queue drops"].status == "FAIL"


def test_a_wrong_subcarrier_map_fails():
    results = evaluate(_healthy(used_carrier_checked=1200,
                                used_carrier_ok=0))
    by = {r.name: r for r in results}
    assert by["subcarrier map"].status == "FAIL"


def test_a_silent_console_fails_the_dual_path_check():
    results = evaluate(_healthy(console_bytes=0))
    by = {r.name: r for r in results}
    assert by["usb vs console byte drift"].status == "FAIL"


def test_missing_status_lines_is_unknown_not_pass():
    results = evaluate(_healthy(first_status=None, last_status=None))
    by = {r.name: r for r in results}
    assert by["csi callback activity"].status == "UNKNOWN"
    assert verdict(results) == "INCONCLUSIVE"


def test_supervisor_telemetry_is_deferred_and_never_fails_the_run():
    results = evaluate(_healthy())
    by = {r.name: r for r in results}
    assert by["supervisor telemetry"].status == "DEFERRED"
    assert verdict(results) == "PASS"
