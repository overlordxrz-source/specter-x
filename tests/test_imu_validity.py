"""Offline BNO085 input boundary; no device import or operation."""
import numpy as np
import pytest

from specter.sensors.imu.bno085 import Bno085Driver, quat_measurement


@pytest.mark.parametrize("q", [[], [1, 0, 0], [1, 0, 0, 0, 0],
    [[1, 0], [0, 0]], [0, 0, 0, 0], [float("nan"), 0, 0, 1],
    [float("inf"), 0, 0, 1], [float("-inf"), 0, 0, 1], None])
def test_invalid_quaternion_is_rejected(q):
    with pytest.raises(ValueError):
        quat_measurement(q)


@pytest.mark.parametrize("scale", [1., 1e308, 1e-320])
def test_extreme_finite_quaternion_normalizes_without_overflow(scale):
    m = quat_measurement([scale, scale, 0, 0])
    np.testing.assert_allclose(m.value["quat_wxyz"],
        [2**-.5, 2**-.5, 0, 0], rtol=1e-12)


def test_rejected_report_does_not_consume_frame_index():
    driver = Bno085Driver()
    with pytest.raises(ValueError):
        driver.report([float("nan"), 0, 0, 1])
    assert driver._i == 0
    m = driver.report([1, 0, 0, 0])
    assert driver._i == 1
    assert m.provenance.frame_index == 1
