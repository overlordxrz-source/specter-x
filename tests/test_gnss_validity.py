"""GNSS receiver-validity contract for the localization EKF.

Synthetic and physical inputs use the same Measurement shape, but a valid
physical fix must be explicit: fix type 3, at least four satellites, finite
coordinates and uncertainty, an explicit altitude datum, a nonnegative
confidence and a compatible host timestamp. Invalid input must be rejected
before it can anchor or change the mode.
"""

import math
import time

import numpy as np
import pytest

from specter.localization.ekf import PoseEKF
from specter.sensors.gnss.neom9n import (
    Neom9nDriver,
    SyntheticGnss,
    build_nav_pvt,
    parse_nav_pvt,
    pvt_to_measurement,
)


def _valid_fix(*, t_host=1000.0, lat=47.0, lon=8.0, alt=400.0,
               fix_type=3, num_sv=12, h_acc_mm=2500, v_acc_mm=4200):
    pvt = parse_nav_pvt(
        build_nav_pvt(
            lat_deg=lat,
            lon_deg=lon,
            height_m=alt,
            fix_type=fix_type,
            num_sv=num_sv,
            h_acc_mm=h_acc_mm,
            v_acc_mm=v_acc_mm,
        )[6:98]
    )
    return pvt_to_measurement(pvt, sensor_id="neom9n-test", t_host=t_host)


def _state(ekf):
    return {
        "anchor": ekf.anchor,
        "mode": ekf.mode,
        "t": ekf._t,
        "started": ekf._started,
        "last_gnss_t": ekf._last_gnss_t,
        "measurement_ids": list(ekf.measurement_ids),
        "x": ekf.x.copy(),
        "P": ekf.P.copy(),
    }


def _assert_state_equal(actual, expected):
    assert actual["anchor"] == expected["anchor"]
    assert actual["mode"] == expected["mode"]
    assert actual["t"] == expected["t"]
    assert actual["started"] == expected["started"]
    assert actual["last_gnss_t"] == expected["last_gnss_t"]
    assert actual["measurement_ids"] == expected["measurement_ids"]
    np.testing.assert_array_equal(actual["x"], expected["x"])
    np.testing.assert_array_equal(actual["P"], expected["P"])


def _assert_rejected_without_mutation(ekf, measurement):
    before = _state(ekf)
    with pytest.raises(ValueError):
        ekf.update_gnss(measurement)
    _assert_state_equal(_state(ekf), before)


def test_valid_fix_anchors_and_switches_mode():
    ekf = PoseEKF("A")
    pose = ekf.update_gnss(_valid_fix())
    assert pose.anchor == (47.0, 8.0, 400.0)
    assert pose.mode == "GNSS"
    assert pose.measurement_ids


@pytest.mark.parametrize("fix_type", [0, 1, 2, 4, 5, 99])
def test_non_3d_fix_types_cannot_anchor(fix_type):
    ekf = PoseEKF("A")
    _assert_rejected_without_mutation(ekf, _valid_fix(fix_type=fix_type))
    assert ekf.pose().mode == "REL"


@pytest.mark.parametrize("num_sv", [0, 1, 3, 65, 99])
def test_invalid_satellite_counts_cannot_anchor(num_sv):
    ekf = PoseEKF("A")
    _assert_rejected_without_mutation(ekf, _valid_fix(num_sv=num_sv))


@pytest.mark.parametrize(
    "field,value",
    [
        ("lat_deg", 91.0),
        ("lat_deg", -91.0),
        ("lon_deg", 181.0),
        ("lon_deg", -181.0),
        ("alt_m", 20_001.0),
        ("alt_m", -1_001.0),
    ],
)
def test_out_of_range_geography_cannot_anchor(field, value):
    ekf = PoseEKF("A")
    fix = _valid_fix()
    fix.value[field] = value
    _assert_rejected_without_mutation(ekf, fix)


@pytest.mark.parametrize(
    "field,value",
    [
        ("lat_deg", float("nan")),
        ("lon_deg", float("inf")),
        ("alt_m", float("-inf")),
        ("h_acc_m", float("nan")),
        ("v_acc_m", float("inf")),
    ],
)
def test_nonfinite_values_cannot_anchor(field, value):
    ekf = PoseEKF("A")
    fix = _valid_fix()
    fix.value[field] = value
    _assert_rejected_without_mutation(ekf, fix)


def test_invalid_covariance_cannot_anchor():
    ekf = PoseEKF("A")
    for cov in (
        None,
        [[math.nan, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
        [[1.0, 0.0, 0.0], [0.0, -1.0, 0.0], [0.0, 0.0, 1.0]],
        [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
    ):
        fix = _valid_fix()
        fix.covariance = cov
        _assert_rejected_without_mutation(ekf, fix)


@pytest.mark.parametrize(
    "field,value",
    [
        ("sim", None),
        ("sim", 0),
        ("sim", "false"),
        ("alt_datum", None),
        ("alt_datum", ""),
        ("alt_datum", "unspecified"),
        ("fix_type", 3.0),
        ("fix_type", True),
        ("num_sv", True),
    ],
)
def test_unspecified_or_wrongly_typed_fields_are_rejected(field, value):
    ekf = PoseEKF("A")
    fix = _valid_fix()
    if value is None:
        fix.value.pop(field, None)
    else:
        fix.value[field] = value
    _assert_rejected_without_mutation(ekf, fix)


def test_synthetic_fix_requires_explicit_allowance():
    sim = SyntheticGnss().read()
    _assert_rejected_without_mutation(PoseEKF("A"), sim)
    ekf = PoseEKF("A", allow_simulated=True)
    pose = ekf.update_gnss(sim)
    assert pose.anchor is not None and pose.mode == "GNSS"


@pytest.mark.parametrize("tau", [float("nan"), float("inf"), -1.0])
def test_nonfinite_or_negative_timestamp_is_rejected(tau):
    ekf = PoseEKF("A")
    fix = _valid_fix()
    fix.t_host = tau
    _assert_rejected_without_mutation(ekf, fix)


def test_backwards_and_far_future_timestamps_are_rejected():
    ekf = PoseEKF("A")
    ekf.update_gnss(_valid_fix(t_host=1000.0))
    for tau in (999.0, 1002.0):
        _assert_rejected_without_mutation(ekf, _valid_fix(t_host=tau))
    assert ekf.pose().mode == "GNSS"


def test_valid_fix_after_invalid_report_still_works():
    ekf = PoseEKF("A")
    invalid = _valid_fix(fix_type=0)
    _assert_rejected_without_mutation(ekf, invalid)
    pose = ekf.update_gnss(_valid_fix(t_host=1000.0))
    assert pose.anchor == (47.0, 8.0, 400.0) and pose.mode == "GNSS"


def test_nmea_msl_fix_is_explicit_and_accepted():
    m = Neom9nDriver().feed_nmea(
        "$GPGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,*47"
    )
    assert m is not None and m.value["alt_datum"] == "msl"
    pose = PoseEKF("A").update_gnss(m)
    assert pose.mode == "GNSS" and pose.anchor is not None


def test_altitude_datum_cannot_change_after_anchor():
    ekf = PoseEKF("A")
    ekf.update_gnss(_valid_fix(t_host=1000.0))
    nmea = Neom9nDriver().feed_nmea(
        "$GPGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,*47"
    )
    nmea.t_host = 1001.0
    _assert_rejected_without_mutation(ekf, nmea)
    assert ekf.anchor == (47.0, 8.0, 400.0)


def test_missing_altitude_datum_is_rejected():
    ekf = PoseEKF("A")
    fix = _valid_fix()
    fix.value.pop("alt_datum")
    _assert_rejected_without_mutation(ekf, fix)


def test_first_gnss_fix_can_establish_wall_clock_after_prediction():
    ekf = PoseEKF("A")
    ekf.predict(0.2)
    pose = ekf.update_gnss(_valid_fix(t_host=time.time()))
    assert pose.mode == "GNSS" and pose.anchor == (47.0, 8.0, 400.0)


def test_wrong_sensor_or_frame_cannot_anchor():
    ekf = PoseEKF("A")
    wrong_sensor = _valid_fix()
    wrong_sensor.sensor = "synthetic"
    _assert_rejected_without_mutation(ekf, wrong_sensor)
    wrong_frame = _valid_fix()
    wrong_frame.frame_id = "local"
    _assert_rejected_without_mutation(ekf, wrong_frame)


def test_unspecified_confidence_cannot_anchor():
    ekf = PoseEKF("A")
    fix = _valid_fix()
    fix.confidence = None
    _assert_rejected_without_mutation(ekf, fix)
