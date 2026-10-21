"""DI-188 monitoring: statistics, honesty labels, recording and stability."""
import os

import pytest

from specter.sensors.di188.calibration import CalibrationSet
from specter.sensors.di188.recorder import CsvRecorder, build_provenance
from specter.sensors.di188.stability import StabilityReport
from specter.sensors.di188.stats import (ChannelMonitor, ChannelSpec, ChannelState,
                                         ChannelStats, default_specs)


def test_channel_stats_math():
    st = ChannelStats()
    for v in (1.0, 2.0, 3.0, 4.0):
        st.add(v)
    assert st.n == 4
    assert st.mean == pytest.approx(2.5)
    assert st.variance == pytest.approx(1.25)
    assert st.std == pytest.approx(1.25 ** 0.5)
    assert st.minimum == 1.0
    assert st.maximum == 4.0
    assert st.peak_to_peak == 3.0
    assert st.rms == pytest.approx(((1 + 4 + 9 + 16) / 4) ** 0.5)


def test_undeclared_channel_is_never_reported_as_a_measurement():
    specs = default_specs(4)
    monitor = ChannelMonitor(specs)
    monitor.add([1.0, 2.0, 3.0, 4.0])
    reports = monitor.report()
    assert all(r.state is ChannelState.UNDECLARED for r in reports)
    assert not any(r.state.is_measurement for r in reports)
    for r in reports:
        assert "not a measurement" in r.note


def test_declared_floating_channel_says_so():
    specs = default_specs(2)
    specs[0].connected = False
    monitor = ChannelMonitor(specs)
    monitor.add([5.0, 6.0])
    reports = monitor.report()
    assert reports[0].state is ChannelState.FLOATING
    assert "not a measurement" in reports[0].note


def test_connected_channel_is_a_measurement_but_still_flags_nominal_volts():
    specs = default_specs(1)
    specs[0].connected = True
    specs[0].source = "1.500 V cell"
    cal = CalibrationSet.nominal("di188_pm10v", [0])
    monitor = ChannelMonitor(specs)
    monitor.add([4918])
    report = monitor.report(cal)[0]
    assert report.state is ChannelState.CONNECTED
    assert report.state.is_measurement
    assert report.volts is not None
    assert "nominal/uncertified" in report.note


def test_report_serialises_every_field():
    specs = default_specs(2)
    monitor = ChannelMonitor(specs)
    monitor.add([1.0, 2.0])
    payload = monitor.report()[0].as_dict()
    for key in ("index", "label", "terminal", "state", "is_measurement",
                "counts", "volts", "calibration_basis", "note"):
        assert key in payload
    assert payload["counts"]["n"] == 1


def test_recording_header_carries_full_provenance(tmp_path):
    from specter.sensors.di188.driver import DeviceCalibration, DI188Identity
    ident = DI188Identity(port="/dev/cu.usbmodem101", usb_product="Seeed XIAO M0",
                          usb_vid=0x2846, usb_pid=0x8037, model="188",
                          vendor_tag="DATAQ", serial_number="022D9B0B",
                          firmware_rev="0", hardware_rev="0")
    dev_cal = DeviceCalibration(read_ok=True, scale=[[18850] * 4] * 8,
                                 offset=[[-78, 0, 0, 0]] * 8, last_cal_date="6214F19E")
    cal = CalibrationSet.nominal("di188_pm10v", [0, 1, 2, 3],
                                 device_serial="022D9B0B", device_model="DI-188")
    specs = default_specs(4)
    reports = ChannelMonitor(specs).report(cal)
    header = build_provenance(ident, dev_cal, cal, [0, 1, 2, 3], 500.0, reports)
    text = "\n".join(header)
    assert "# calibration_basis: UNCALIBRATED (nominal)" in text
    assert "# device: DI-188 (DATAQ)" in text
    assert "0x2846:0x8037" in text
    assert "# sample_rate_hz: 500" in text
    for i in range(4):
        assert f"# channel_state ch{i}" in text
        assert "UNDECLARED" in text


def test_csv_rows_carry_counts_and_volts(tmp_path):
    cal = CalibrationSet.nominal("di188_pm10v", [0, 1])
    path = os.path.join(tmp_path, "r.csv")
    rec = CsvRecorder(path, [0, 1], ["# test"])
    rec.write(0.0, 0, [10, 20], [cal.to_volts(0, 10), cal.to_volts(1, 20)])
    rec.close()
    lines = open(path).read().strip().split("\n")
    assert lines[0] == "# test"
    assert lines[1].startswith("t_s,frame,ch0_counts,ch0_volts,ch1_counts,ch1_volts")
    assert lines[2].startswith("0.000000,0,10,")


def test_stability_report_flags_a_shortfall():
    rep = StabilityReport(duration_s=10.0, realised_rate=100.0, frames_received=900,
                           frames_expected=1000, frames_shortfall=100,
                           stall_events=2, worst_stall_s=0.4, malformed_lines=1)
    payload = rep.as_dict()
    assert payload["frames_shortfall"] == 100
    assert payload["stall_events"] == 2
    assert payload["ok"] is False
    assert "PASS" not in rep.summary()


def test_stability_report_passes_when_clean():
    rep = StabilityReport(duration_s=1800.0, realised_rate=500.0, frames_received=900000,
                           frames_expected=900000, frames_shortfall=0)
    assert rep.ok
    assert "PASS" in rep.summary()


def test_a_small_stable_rate_offset_is_not_called_frame_loss():
    from specter.sensors.di188.stability import _classify
    rep = StabilityReport(duration_s=1800.0, realised_rate=500.0,
                           frames_received=892800, frames_expected=900000,
                           frames_shortfall=7200, achieved_rate_hz=496.0,
                           rate_offset_pct=-0.8, window_rate_std_pct=0.05)
    assert _classify(rep) == ("SYSTEMATIC RATE OFFSET (device timer quantisation) "
                              "- not frame loss")


def test_a_wobbling_rate_is_called_frame_loss():
    from specter.sensors.di188.stability import _classify
    rep = StabilityReport(duration_s=1800.0, realised_rate=500.0,
                           frames_received=800000, frames_expected=900000,
                           frames_shortfall=100000, achieved_rate_hz=444.0,
                           rate_offset_pct=-11.2, window_rate_std_pct=8.0)
    assert "FRAME LOSS" in _classify(rep)


def test_a_dropped_link_is_reported_as_a_link_error():
    from specter.sensors.di188.stability import _classify
    rep = StabilityReport(serial_errors=1, disconnects=1)
    assert "LINK ERROR" in _classify(rep)
