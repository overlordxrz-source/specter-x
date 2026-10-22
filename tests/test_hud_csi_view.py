"""Tests for the redesigned CSI view, the theme, and the guided experiment."""
from __future__ import annotations

import json
import os

import numpy as np
import pytest

from specter.hud import theme
from specter.hud.csi_views import draw_csi_dashboard
from specter.hud.renderer import HUD_H, HUD_W, HudState, render
from specter.sensors.esp32.csi_analysis import (CsiViewState, complex_subcarriers,
                                                 subcarrier_amplitudes_np)
from specter.sensors.esp32.dispatcher import CsiRecord
from specter.sensors.esp32.experiment import (GuidedExperiment, TrialSpec,
                                               analyse_offline, condition_test,
                                               f_sf, one_way_f, per_carrier_screen,
                                               trials_from_json, verdict_from)

NULL = (0,) + tuple(range(27, 38))


def make_record(seq: int, amps, rssi: int = -70, mac: str = "aa:bb:cc:dd:ee:ff",
                channel: int = 11) -> CsiRecord:
    """A CSI record whose complex samples produce the wanted amplitudes."""
    iq = []
    for a in amps:
        iq.extend([int(round(a)), 0])
    return CsiRecord(seq=seq, mac=mac, rssi=rssi, rate=9, noise_floor=-96,
                      channel=channel, local_timestamp=1000 * seq, sig_len=109,
                      iq=iq)


def profile(used_value: float = 20.0) -> np.ndarray:
    amps = np.full(64, used_value, dtype=np.float32)
    for c in NULL:
        amps[c] = 0.0
    return amps


# --- the theme -------------------------------------------------------------

def test_health_colour_never_claims_ok_for_an_unknown_word():
    assert theme.health_color("OK") == theme.OK
    assert theme.health_color("OFFLINE") == theme.FAULT
    assert theme.health_color("DEGRADED") == theme.WARN
    # an unknown word must not read as healthy
    assert theme.health_color("WAT") != theme.OK
    assert theme.health_color(None) == theme.TEXT_DIM


def test_health_colour_never_uses_an_accent_colour():
    accents = {theme.CRIMSON, theme.ROSE, theme.ROSE_DIM, theme.BURGUNDY}
    for word in ("OK", "DEGRADED", "STALLED", "OFFLINE", "ERROR", "SIMULATED"):
        assert theme.health_color(word) not in accents


def test_waterfall_lut_is_monotonic_in_lightness():
    lut = theme.waterfall_lut()
    lum = lut.astype(float).sum(axis=1)
    # the ramp must never get darker as it climbs, and must cover a wide
    # range so the picture can be read without relying on hue
    assert np.all(np.diff(lum) >= 0), "the ramp must not get darker"
    assert lum[-1] > lum[0] * 8.0, "the ramp must cover a wide range"


# --- the CSI analysis state ------------------------------------------------

def test_complex_samples_are_read_as_i_q_pairs():
    c = complex_subcarriers([3, 4, 6, 8])
    assert c.shape == (2, 2)
    assert c[0].tolist() == [3.0, 4.0]
    amps = subcarrier_amplitudes_np([3, 4, 6, 8])
    assert amps.tolist() == [5.0, 10.0]


def test_an_odd_trailing_sample_is_not_silently_made_into_a_carrier():
    # 5 samples: two carriers and one orphan
    c = complex_subcarriers([1, 1, 2, 2, 3])
    assert c.shape == (2, 2)


def test_the_unused_carriers_are_detected_from_the_data():
    st = CsiViewState(columns=64, carriers=64)
    for i in range(10):
        st.push(make_record(i, profile()))
    assert st.null_indices() == list(NULL)
    assert int(st.used_mask().sum()) == 64 - len(NULL)


def test_the_baseline_locks_and_the_change_metric_starts_near_zero():
    st = CsiViewState(columns=64, carriers=64, baseline_s=5.0)
    for i in range(200):
        st.push(make_record(i, profile() * (1.0 + 0.01 * np.random.randn())))
    assert st.view()["baseline_ready"]
    assert st.view()["change"] < 0.02


def test_a_body_in_the_path_moves_the_change_metric():
    st = CsiViewState(columns=64, carriers=64, baseline_s=5.0)
    for i in range(200):
        st.push(make_record(i, profile()))
    quiet = st.view()["change"]
    for i in range(200, 240):
        moved = profile()
        for c in (38, 39, 40, 48, 49):
            moved[c] *= 0.3
        st.push(make_record(i, moved))
    assert st.view()["change"] > quiet * 2.0, \
        "a perturbed channel must move the change metric"


def test_the_waterfall_and_the_trace_are_bounded_and_aligned():
    st = CsiViewState(columns=64, carriers=64)
    for i in range(500):
        st.push(make_record(i, profile()))
    wf = st.waterfall()
    tr = st.trace()
    assert wf.shape == (64, 64)
    assert tr.shape == (64,)
    # the trace has one value per column, so the two views share a time base
    assert wf.shape[1] == tr.shape[0]


def test_a_change_of_csi_source_is_recorded_not_smoothed_over():
    st = CsiViewState(columns=16, carriers=64)
    for i in range(6):
        st.push(make_record(i, profile(), mac="aa:aa:aa:aa:aa:aa"))
    for i in range(6, 12):
        st.push(make_record(i, profile(), mac="bb:bb:bb:bb:bb:bb", channel=1))
    v = st.view()
    assert v["source_mac"] == "bb:bb:bb:bb:bb:bb"
    assert v["source_changes"] == 1
    assert v["source_history"], "the change must be recorded"


def test_replaying_amplitudes_matches_the_live_path():
    live = CsiViewState(columns=32, carriers=64)
    replay = CsiViewState(columns=32, carriers=64)
    for i in range(20):
        live.push(make_record(i, profile()))
    for i in range(20):
        replay.push_amplitudes(profile())
    assert np.allclose(live.waterfall(), replay.waterfall())


# --- the guided experiment -------------------------------------------------

def test_the_f_distribution_matches_the_standard_critical_values():
    # the standard F(2,6) quantiles
    assert f_sf(5.1433, 2, 6) == pytest.approx(0.05, abs=1e-4)
    assert f_sf(7.26, 2, 6) == pytest.approx(0.025, abs=1e-4)
    assert f_sf(10.92, 2, 6) == pytest.approx(0.01, abs=1e-4)
    assert f_sf(4.2564, 2, 9) == pytest.approx(0.05, abs=1e-4)
    # an F of 1 is the smallest the ratio can be: it must not read as a find
    assert f_sf(1.0, 2, 6) > 0.3


def test_an_unseparated_result_never_claims_a_detection():
    trials = [{"label": "stationary", "amplitudes": np.ones((50, 4)) * 20},
              {"label": "hand", "amplitudes": np.ones((50, 4)) * 20}]
    test = condition_test(trials)
    v = verdict_from(trials, test)
    assert v["verified_human_detection"] is False
    assert "NO VERIFIED HUMAN DETECTION" in v["claim"]


def _noisy_trial(label: str, sigma: float, seed: int) -> Dict:
    """A trial whose channel is quiet or disturbed, as a body in the path
    would make it. The discriminator is the *temporal* structure, so the
    two conditions differ in how much the profile moves between packets."""
    rng = np.random.default_rng(seed)
    base = np.full((60, 4), 20.0)
    walk = np.cumsum(rng.normal(0.0, sigma, (60, 4)), axis=0)
    return {"label": label, "amplitudes": base + walk}


def test_a_separated_result_with_a_control_is_a_verified_detection():
    trials = []
    for i in range(4):
        trials.append(_noisy_trial("stationary", 0.02, 100 + i))
        trials.append(_noisy_trial("hand", 1.5, 200 + i))
    test = condition_test(trials)
    v = verdict_from(trials, test)
    assert v["verified_human_detection"] is True
    assert "VERIFIED HUMAN DETECTION" in v["claim"]


def test_a_separated_result_without_a_control_is_not_a_verified_detection():
    trials = [_noisy_trial("a", 0.02, 300), _noisy_trial("b", 1.5, 301),
              _noisy_trial("a", 0.02, 302), _noisy_trial("b", 1.5, 303)]
    test = condition_test(trials)
    v = verdict_from(trials, test)
    assert v["verified_human_detection"] is False
    assert "NO STATIONARY CONTROL" in v["claim"]


def test_the_per_carrier_screen_excludes_the_unused_carriers():
    rng = np.random.default_rng(6)
    trials = []
    for label, level in (("stationary", 20.0), ("hand", 26.0)):
        for _ in range(3):
            amps = np.full((40, 8), level)
            amps[:, 3] = 0.0          # an unused carrier
            noisy = amps.copy()
            noisy[:, [0, 1, 2, 4, 5, 6, 7]] += rng.normal(0, 0.1, (40, 7))
            trials.append({"label": label, "amplitudes": noisy})
    screen = per_carrier_screen(trials)
    assert screen["null_carriers"] == [3]
    assert screen["carriers_used"] == screen["carriers"] - 1


def test_the_trial_machine_walks_the_phases_and_records_a_trial():
    exp = GuidedExperiment([TrialSpec("stationary", 0.2, "stand still"),
                             TrialSpec("hand", 0.2, "wave")],
                            consent="subject: test; informed: yes")
    now = 1000.0
    exp.start(now)
    assert exp.phase == "LEAD-IN"
    exp.tick(now + 5.0)
    assert exp.phase == "RECORDING"
    for i in range(10):
        exp.feed(make_record(i, profile()), t=now)
    exp.tick(now + 5.5)
    assert exp.phase in ("LEAD-IN", "ANALYSIS", "DONE")
    assert len(exp.trials) == 1
    assert exp.trials[0]["label"] == "stationary"
    assert exp.trials[0]["packets"] == 10


def test_the_experiment_exports_metrics_json_a_packet_file_and_a_csv(tmp_path):
    exp = GuidedExperiment([TrialSpec("stationary", 0.2),
                             TrialSpec("hand", 0.2)], consent="c")
    now = 1000.0
    exp.start(now)
    exp.tick(now + 5.0)
    for i in range(20):
        exp.feed(make_record(i, profile()), t=now)
    exp.tick(now + 10.0)      # closes trial 1, opens the lead-in for trial 2
    exp.tick(now + 20.0)      # trial 2 records
    for i in range(20):
        exp.feed(make_record(100 + i, profile()), t=now)
    exp.tick(now + 30.0)      # closes trial 2, analyses
    exp.tick(now + 31.0)
    assert exp.phase == "DONE"
    out = str(tmp_path / "exp.json")
    csv = str(tmp_path / "exp.csv")
    summary = exp.export(out, csv)
    assert os.path.exists(out)
    assert os.path.exists(str(tmp_path / "exp_packets.npz"))
    assert os.path.exists(csv)
    with open(out) as fh:
        loaded = json.load(fh)
    assert loaded["consent"] == "c"
    assert len(loaded["trials"]) == 2
    assert "verdict" in loaded and "claim" in loaded["verdict"]
    assert "roughness" in summary["features"][0]
    with open(csv) as fh:
        rows = fh.read().strip().split("\n")
    assert len(rows) == 3          # a header and two trials


def test_the_offline_analysis_reads_a_recorded_session():
    data = {
        "trials": [
            {"label": "stationary", "packets": 3, "samples": [
                {"t": 0.0, "id": 1, "rssi": -70, "amplitudes": [20, 20, 0, 20]},
                {"t": 1.0, "id": 2, "rssi": -70, "amplitudes": [21, 19, 0, 22]},
                {"t": 2.0, "id": 3, "rssi": -71, "amplitudes": [19, 21, 0, 20]},
            ]},
            {"label": "hand", "packets": 3, "samples": [
                {"t": 0.0, "id": 4, "rssi": -60, "amplitudes": [26, 25, 0, 27]},
                {"t": 1.0, "id": 5, "rssi": -60, "amplitudes": [25, 26, 0, 24]},
                {"t": 2.0, "id": 6, "rssi": -61, "amplitudes": [27, 24, 0, 26]},
            ]},
        ]
    }
    trials = trials_from_json(data)
    assert len(trials) == 2
    assert trials[0]["amplitudes"].shape == (3, 4)
    out = analyse_offline(data)
    assert "test" in out and "verdict" in out and "screen" in out


# --- the drawing -----------------------------------------------------------

def _view():
    st = CsiViewState(columns=64, carriers=64)
    for i in range(120):
        st.push(make_record(i, profile()))
    v = st.view()
    v["waterfall"] = st.waterfall()
    v["trace"] = st.trace()
    v["used_mask"] = st.used_mask()
    v["link_state"] = "CONNECTED"
    v["packets"] = 120
    v["packets_per_s"] = 178.0
    v["history_s"] = 4.0
    return v


def test_the_csi_dashboard_draws_without_a_view():
    canvas = np.zeros((HUD_H, HUD_W, 3), np.uint8)
    draw_csi_dashboard(canvas, None, 0, 44, HUD_W - 270, HUD_H - 44)
    assert canvas.shape == (HUD_H, HUD_W, 3)


def test_the_csi_mode_renders_the_whole_frame():
    st = HudState(mode="CSI")
    st.csi = _view()
    img = np.zeros((720, 1280, 3), np.uint8)
    frame = render(img, st)
    assert frame.shape == (HUD_H, HUD_W, 3)
    # the waterfall region must not be empty
    region = frame[140:380, 40:950]
    assert region.std() > 5.0, "the waterfall must actually draw something"


def test_the_raw_spectrum_is_a_secondary_view_not_the_default():
    st = HudState(mode="CSI")
    st.csi = _view()
    img = np.zeros((720, 1280, 3), np.uint8)
    default = render(img, st)
    st.csi_spectrum = True
    spectrum = render(img, st)
    assert not np.array_equal(default, spectrum), \
        "the spectrum must be a different view"


def test_every_mode_still_renders():
    img = np.zeros((720, 1280, 3), np.uint8)
    for mode in ("OPTICAL", "NIGHT-GREEN", "ANALOG", "CSI"):
        st = HudState(mode=mode)
        st.csi = _view()
        assert render(img, st).shape == (HUD_H, HUD_W, 3)


def test_the_honest_absence_of_supervisor_telemetry_is_still_shown():
    from specter.sensors.base import Health, SensorStatus
    st = HudState(mode="CSI")
    st.csi = _view()
    st.sensors = [SensorStatus("supervisor", "SUPERVISOR ESP32",
                                Health.NOT_INSTALLED, "telemetry not available")]
    img = np.zeros((720, 1280, 3), np.uint8)
    frame = render(img, st)
    assert frame.shape == (HUD_H, HUD_W, 3)
