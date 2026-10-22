"""The preflight must be able to say FAIL, and must not say PASS by accident.

The tool in ``tools/esp32_lab_preflight.py`` is run once, on hardware, at a
moment when a wrong answer is expensive. Its scoring logic is therefore
tested here against observations that are built by hand: a healthy link, a
link whose callback never fires (the SoftAP question), a link with a USB
stall, and a link with the wrong subcarrier map.
"""
from __future__ import annotations

import importlib.util
import json
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
ACTIVE_CARRIERS = preflight.ACTIVE_CARRIERS
NULL_CARRIERS = preflight.NULL_CARRIERS


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
        null_ok=1200, null_checked=1200,
        active_seen=sorted(ACTIVE_CARRIERS),
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
                   null_checked=0, null_ok=0,
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


def test_a_null_that_carries_energy_fails():
    """The property v2 protects: a required null must be silent."""
    by = {r.name: r for r in evaluate(_healthy(null_checked=1200, null_ok=1199))}
    assert by["subcarrier nulls"].status == "FAIL"
    assert verdict(evaluate(_healthy(null_ok=1199))) == "FAIL"


def test_zero_valued_active_subcarriers_are_not_failures():
    """Regression for the 79.7% score: int8 truncation is not corruption."""
    by = {r.name: r for r in evaluate(_healthy(null_ok=1200, null_checked=1200))}
    assert by["subcarrier nulls"].status == "PASS"
    assert by["active subcarrier coverage"].status == "PASS"


def test_active_coverage_is_judged_across_the_capture():
    partial = sorted(ACTIVE_CARRIERS)[:40]
    by = {r.name: r for r in evaluate(_healthy(active_seen=partial))}
    assert by["subcarrier nulls"].status == "PASS"
    assert by["active subcarrier coverage"].status == "FAIL"


def test_v1_observations_do_not_silently_upgrade_to_pass():
    obs = _healthy(null_checked=0, null_ok=0,
                   used_carrier_checked=1200, used_carrier_ok=1200)
    by = {r.name: r for r in evaluate(obs)}
    assert by["subcarrier nulls"].status == "UNKNOWN"
    assert by["active subcarrier coverage"].status == "UNKNOWN"


def test_too_few_frames_to_verify_the_map_is_unknown_not_pass():
    by = {r.name: r for r in evaluate(_healthy(null_checked=5, null_ok=5))}
    assert by["active subcarrier coverage"].status == "UNKNOWN"


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


# --- hardware regression -----------------------------------------------------
# Real 20 MHz LLTF records from the 2026-10-22 phone-station capture. Two of
# them have an active subcarrier truncated to (0, 0) by int8 quantisation,
# which is exactly what v1 scored as a broken subcarrier map.

FIXTURE = os.path.join(REPO, "tests", "fixtures", "esp32_csi",
                       "phone_station_lltf.jsonl")


def _fixture_records():
    out = []
    with open(FIXTURE, encoding="utf-8") as fh:
        for raw in fh:
            rec = json.loads(raw)
            iq = [int(x) for x in rec["line"].split(',"', 1)[1]
                  .rstrip('"').strip("[]").split(",")]
            out.append((rec["label"], iq))
    return out


def test_captured_records_with_truncated_active_slots_are_not_failures():
    labels = [label for label, _ in _fixture_records()]
    assert "exact" in labels
    assert any(label.startswith("truncated") for label in labels)
    for label, iq in _fixture_records():
        nulls_ok, active, slots = preflight._analyse_subcarriers(iq)
        assert slots == 64, label
        assert nulls_ok, f"{label}: a required null carried energy"
        if label.startswith("truncated"):
            assert len(active) < 52, f"{label}: expected a truncated slot"
        else:
            assert active == set(ACTIVE_CARRIERS), label


def _synthetic_iq(zero_slots=()):
    iq = [3, 4] * 64
    for slot in zero_slots:
        iq[2 * slot] = iq[2 * slot + 1] = 0
    return iq


def test_synthetic_energy_in_any_null_slot_is_a_violation():
    for slot in sorted(NULL_CARRIERS):
        iq = _synthetic_iq(zero_slots=NULL_CARRIERS - {slot})
        nulls_ok, _, slots = preflight._analyse_subcarriers(iq)
        assert slots == 64
        assert not nulls_ok, f"slot {slot} carried energy and was not caught"


def test_synthetic_all_zero_record_has_clean_nulls_but_no_coverage():
    nulls_ok, active, slots = preflight._analyse_subcarriers([0] * 128)
    assert slots == 64
    assert nulls_ok            # every required null is zero
    assert active == frozenset()   # and nothing was covering the active slots


def test_synthetic_short_record_is_not_accepted_as_an_lltf_capture():
    nulls_ok, _, slots = preflight._analyse_subcarriers([1, 1] * 32)
    assert slots == 32
    assert not nulls_ok


def test_synthetic_ht40_width_is_not_silently_scored_as_lltf():
    nulls_ok, _, slots = preflight._analyse_subcarriers([1, 1] * 128)
    assert slots == 128
    assert not nulls_ok
