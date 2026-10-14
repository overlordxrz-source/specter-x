"""UWB ranging + EKF pose: protocol, simulator honesty, ENU anchoring."""
import numpy as np

from specter.localization.ekf import PoseEKF, latlon_to_enu
from specter.sensors.gnss.neom9n import build_nav_pvt, parse_nav_pvt, pvt_to_measurement
from specter.sensors.uwb.dw1000 import (
    Dw1000Driver, UwbSimulator, decode_frame, ds_twr_tof,
    encode_final, encode_poll, encode_response, tof_to_distance_m,
)


def _fix(lat, lon):
    pvt = parse_nav_pvt(build_nav_pvt(lat_deg=lat, lon_deg=lon, height_m=400.0)[6:98])
    return pvt_to_measurement(pvt, sensor_id="neom9n-test")


def test_ds_twr_recovers_distance():
    import pytest

    d_true, c = 12.34, 299_702_547.0
    tof = d_true / c
    # symmetric case is exact: equal replies cancel clock offsets
    est2 = ds_twr_tof(2 * tof + 1e-3, 1e-3, 2 * tof + 1e-3, 1e-3)
    assert tof_to_distance_m(est2) == pytest.approx(d_true, abs=1e-6)
    # asymmetric replies still recover ToF to <1 mm here
    est = ds_twr_tof(2 * tof + 1e-3, 1e-3, 2 * tof + 1.1e-3, 1.1e-3)
    assert tof_to_distance_m(est) == pytest.approx(d_true, abs=1e-3)
    with pytest.raises(ValueError):
        ds_twr_tof(0.0, 0.0, 0.0, 0.0)


def test_protocol_roundtrip():
    assert decode_frame(encode_poll(1, 7)) == ("poll", 1, 7)
    assert decode_frame(encode_response(7, 1, 0.001))[0] == "response"
    assert decode_frame(encode_final(1, 7, 1, 2, 3, 4))[0] == "final"


def test_driver_exchange_provenance():
    import pytest

    drv = Dw1000Driver(unit_id="A")
    m = drv.exchange("B", 2 * 5.0 / 299_702_547.0 + 1e-3, 1e-3,
                     2 * 5.0 / 299_702_547.0 + 1e-3, 1e-3)
    assert (m.sensor, m.kind) == ("uwb", "range")
    assert m.value["peer_id"] == "B"
    assert m.value["distance_m"] == pytest.approx(5.0, abs=0.05)
    assert m.hud_tag.startswith("SRC: UWB conf")


def test_simulator_pairs_two_units_with_10cm_noise():
    sim = UwbSimulator(seed=0)
    pos = {"A": np.array([0.0, 0.0, 0.0]), "B": np.array([3.0, 4.0, 0.0])}  # 5 m apart
    out = sim.ranging(pos)
    assert set(out) == {"A", "B"}
    for u in ("A", "B"):
        assert len(out[u]) == 1 and out[u][0].value["sim"] is True
    assert abs(out["A"][0].value["distance_m"] - 5.0) < 0.5
    import pytest as _pt

    assert out["A"][0].covariance[0][0] == _pt.approx(0.01)  # (0.1 m)^2, honest LOS std


def test_simulator_nlos_flagged_and_deweighted():
    sim = UwbSimulator(seed=1, nlos_pairs=(("A", "B"),))
    out = sim.ranging({"A": np.zeros(3), "B": np.array([5.0, 0, 0])})
    m = out["A"][0]
    assert m.value["nlos"] is True and m.confidence < 0.9
    assert m.value["std_m"] > 0.1 and "NLOS" in (m.provenance.notes or "")


def test_ekf_gnss_anchors_enu_and_reports_gnss():
    ekf = PoseEKF("A")
    assert ekf.pose().mode == "REL"  # indoors without GNSS: relative frame
    p0 = ekf.update_gnss(_fix(47.0, 8.0))
    assert p0.mode == "GNSS" and p0.anchor == (47.0, 8.0, 400.0)
    assert np.linalg.norm(p0.position) < 1e-9  # anchor is the origin
    p1 = ekf.update_gnss(_fix(47.0 + 10 / 111320.0, 8.0))  # 10 m north
    assert 2.0 < p1.position[1] <= 10.0  # Kalman update blends prior + fix
    for _ in range(40):
        p1 = ekf.update_gnss(_fix(47.0 + 10 / 111320.0, 8.0))
    assert abs(p1.position[1] - 10.0) < 1.0  # converges on the fix
    assert p1.hud_badge().startswith("POSE: GNSS")


def test_ekf_range_update_pulls_toward_peer():
    ekf = PoseEKF("A")
    ekf.x[:3] = np.array([10.0, 0.0, 0.0])
    before = float(np.linalg.norm(ekf.x[:3] - np.zeros(3)))
    drv = Dw1000Driver(unit_id="A")
    m = drv.exchange("B", 2 * 5.0 / 299_702_547.0 + 1e-3, 1e-3,
                     2 * 5.0 / 299_702_547.0 + 1e-3, 1e-3)
    ekf.update_range(m, np.zeros(3), np.eye(3) * 0.01)
    after = float(np.linalg.norm(ekf.x[:3] - np.zeros(3)))
    assert after < before  # 10 m estimate pulled toward 5 m measurement
    assert m.id in ekf.measurement_ids  # provenance kept


def test_ekf_predict_moves_and_grows_uncertainty():
    ekf = PoseEKF("A")
    p0, c0 = ekf.pose().position.copy(), np.trace(ekf.P)
    ekf.x[3:] = np.array([1.0, 0.0, 0.0])
    p1 = ekf.predict(1.0)
    assert p1.position[0] == p0[0] + 1.0
    assert np.trace(ekf.P) > c0


def test_ekf_stale_gnss_falls_back_to_rel():
    ekf = PoseEKF("A")
    m = _fix(47.0, 8.0)
    ekf.update_gnss(m)
    assert ekf.pose().mode == "GNSS"
    ekf._t = m.t_host + 60.0  # clock moves on, no new fixes
    ekf._refresh_mode()
    assert ekf.pose().mode == "REL"


def test_latlon_roundtrip():
    anchor = (47.3769, 8.5417, 400.0)
    from specter.localization.ekf import enu_to_latlon

    enu = latlon_to_enu(47.3779, 8.5427, 405.0, anchor)
    lat, lon, alt = enu_to_latlon(enu, anchor)
    assert abs(lat - 47.3779) < 1e-6 and abs(lon - 8.5427) < 1e-6
    assert abs(alt - 405.0) < 1e-9
