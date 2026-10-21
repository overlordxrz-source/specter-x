"""DI-188 calibration: nominal profiles, measured fits, round-tripping."""
import json
import os

import pytest

from specter.sensors.di188.calibration import (CalibrationSet, ChannelCalibration,
                                               fit_linear)


def test_nominal_di188_profile_maps_full_scale_to_ten_volts():
    cal = CalibrationSet.nominal("di188_pm10v", [0, 1, 2, 3])
    ch = cal.for_channel(0)
    assert ch.basis == "nominal"
    assert not ch.calibrated
    assert ch.to_volts(32768) == pytest.approx(10.0)
    assert ch.to_volts(-32768) == pytest.approx(-10.0)
    assert cal.basis_label() == "UNCALIBRATED (nominal)"


def test_nominal_xiao_profile_maps_full_scale_to_3v3():
    cal = CalibrationSet.nominal("xiao_0_3v3", [0])
    assert cal.for_channel(0).to_volts(32767) == pytest.approx(3.3, rel=1e-6)


def test_unknown_profile_claims_no_volts():
    cal = CalibrationSet.nominal("unknown", [0])
    assert cal.to_volts(0, 1000) is None


def test_fit_linear_is_exact_on_a_straight_line():
    gain, offset, rms = fit_linear([(0.0, 0.0), (1000.0, 0.5), (2000.0, 1.0)])
    assert gain == pytest.approx(0.0005)
    assert offset == pytest.approx(0.0, abs=1e-12)
    assert rms == pytest.approx(0.0, abs=1e-12)


def test_fit_linear_needs_two_distinct_levels():
    with pytest.raises(ValueError):
        fit_linear([(10.0, 1.0)])
    with pytest.raises(ValueError):
        fit_linear([(10.0, 1.0), (10.0, 2.0)])


def test_measured_calibration_is_labelled_and_round_trips(tmp_path):
    cal = CalibrationSet.nominal("di188_pm10v", [0, 1])
    cal.channels[0] = ChannelCalibration(
        gain=0.000305, offset=0.001, basis="measured",
        method="least-squares", reference="1.500 V cell", uncertainty_v=0.002,
        points=[(0.0, 0.0), (4918.0, 1.5)])
    path = os.path.join(tmp_path, "di188.json")
    cal.save(path)
    loaded = CalibrationSet.load(path)
    assert loaded.channels[0].basis == "measured"
    assert loaded.channels[0].calibrated
    assert loaded.channels[0].gain == pytest.approx(0.000305)
    assert loaded.basis_label() == "CALIBRATED"
    with open(path) as fh:
        raw = json.load(fh)
    assert "channels" in raw and "0" in raw["channels"]
