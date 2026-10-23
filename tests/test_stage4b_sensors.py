"""Pinmap, GNSS, IMU and SenXor thermal: drivers + synthetic sources for CI."""
import numpy as np
import pytest

from specter.hw.pinmap import PINMAP_PATH, PinmapError, load_pinmap
from specter.sensors.gnss.neom9n import (
    Neom9nDriver, SyntheticGnss, build_nav_pvt, parse_nav_pvt, parse_nmea_gga,
)
from specter.sensors.imu import ImuLayer
from specter.sensors.imu.bno085 import Bno085Driver, SyntheticBno085
from specter.sensors.imu.lsm9ds1 import (
    MahonyFilter, SyntheticLsm9ds1, raw_counts_to_physical,
)
from specter.sensors.thermal.senxor import SyntheticSenxor, frame_dict_to_celsius


def test_pinmap_loads_and_pins_roles():
    pm = load_pinmap()
    assert pm.uwb_spi.startswith("spi")
    assert "serial" in pm.gnss_uart
    assert pm.imu_bus == "i2c-1"
    assert pm.raw["sockets"]["socket_1"]["role"] == "uwb"
    assert pm.raw["sockets"]["socket_2"]["role"] == "gnss"


def test_pinmap_rejects_bad_roles(tmp_path):
    bad = PINMAP_PATH.read_text().replace("role: uwb", "role: gnss")
    p = tmp_path / "pinmap.yaml"
    p.write_text(bad)
    with pytest.raises(PinmapError):
        load_pinmap(p)


def test_ubx_roundtrip_and_measurement_provenance():
    raw = build_nav_pvt(lon_deg=8.5417, lat_deg=47.3769, height_m=410.0,
                        h_acc_mm=2500, v_acc_mm=4200, fix_type=3, num_sv=14)
    drv = Neom9nDriver()
    ms = drv.feed(raw)
    assert len(ms) == 1
    m = ms[0]
    assert (m.sensor, m.kind, m.frame_id) == ("gnss", "gnss_fix", "wgs84")
    assert m.value["lat_deg"] == pytest.approx(47.3769, abs=1e-6)
    assert m.value["fix_label"] == "FIX_3D" and m.value["num_sv"] == 14
    np.testing.assert_allclose(m.covariance[0][0], 2.5**2, rtol=1e-6)
    assert m.hud_tag.startswith("SRC: GNSS conf")
    assert m.provenance.frame_index == 1


def test_ubx_no_fix_is_honest_not_precise():
    drv = Neom9nDriver()
    m = drv.feed(build_nav_pvt(fix_type=0))[0]
    assert m.confidence == 0.0 and m.covariance[0][0] > 1000.0


def test_ubx_corrupt_checksum_dropped():
    raw = bytearray(build_nav_pvt())
    raw[-1] ^= 0xFF
    assert Neom9nDriver().feed(bytes(raw)) == []


def test_nmea_gga_fallback():
    m = Neom9nDriver().feed_nmea("$GPGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,*47")
    assert m is not None and m.kind == "gnss_fix" and m.value["num_sv"] == 8
    assert Neom9nDriver().feed_nmea("$GPGSV,1,1,01,02,,,45*00") is None


def test_synthetic_gnss_sim_labelled():
    g = SyntheticGnss()
    a, b = g.read(), g.read()
    assert b.value["lat_deg"] > a.value["lat_deg"]  # walks north
    assert a.provenance.algorithm.endswith("-sim") and a.value["sim"] is True
    assert a.confidence <= 0.9


def test_lsm9ds1_counts_and_mahony_converges():
    a, g, m = raw_counts_to_physical([0, 0, 16384], [0, 0, 0], [0, 0, 0])
    np.testing.assert_allclose(a, [0, 0, 1.0], atol=1e-3)
    np.testing.assert_allclose(g, [0, 0, 0], atol=1e-9)
    f = MahonyFilter()
    for _ in range(400):
        q = f.update([0, 0, 0], [0, 0, 1.0], [0.5, 0, 0], dt=0.01)
    np.testing.assert_allclose(np.linalg.norm(q), 1.0, atol=1e-9)
    assert abs(q[0]) > 0.9  # level -> near-identity quaternion


def test_imu_layer_accepts_either_driver():
    for which in ("lsm9ds1", "bno085"):
        layer = ImuLayer(which=which)
        assert layer.active == which
    with pytest.raises(ValueError):
        ImuLayer(which="xsens")
    raw, quat = SyntheticLsm9ds1().read()
    assert (quat.sensor, quat.kind, quat.frame_id) == ("imu", "imu_quat", "body")
    assert quat.provenance.parents == (raw.id,)  # quat cites its raw sample
    qb = SyntheticBno085().read()
    assert qb.kind == "imu_quat" and qb.value["sim"] is True
    assert Bno085Driver().report([1, 0, 0, 0]).confidence == 0.9


def test_senxor_unverified_and_sim():
    from specter.sensors.thermal.senxor import SenxorDriver, VERIFIED

    assert VERIFIED is False
    c, m = SyntheticSenxor().read()
    assert c.shape == (120, 160) and c.dtype == np.float32
    assert (m.sensor, m.kind) == ("thermal", "thermal_frame")
    assert m.value["sim"] is True and m.value["verified"] is False
    assert m.confidence is None and m.covariance is None
    assert "UNVERIFIED" in (m.provenance.notes or "")
    assert m.hud_tag.startswith("SRC: THERMAL conf")
    c2 = frame_dict_to_celsius({"temperature": c})
    np.testing.assert_array_equal(c, c2)
    with pytest.raises(ValueError):
        SenxorDriver().ingest(np.zeros((60, 80), np.float32))
