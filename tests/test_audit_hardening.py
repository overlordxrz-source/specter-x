"""Independent failure controls for repository audit. No physical acquisition."""

import copy
import json
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pytest
from specter.platform.observation import Observation, ContractError
from specter.platform.registry import default_registry
from specter.platform.replay import CsiReplay
from specter.fusion.measurement import Measurement, Provenance
from specter.net.security import sign, verify, ReplayGuard
from specter.net.transport import UdpMulticastTransport
from specter.net.messages import Heartbeat
from specter.net.clock import ClockSync
from specter.world.server import catalog, Handler


@pytest.fixture
def observation(tmp_path):
    p = tmp_path / "fixture.raw.csi"
    p.write_text(
        json.loads(
            (Path(__file__).parent / "fixtures/esp32_csi/phone_station_lltf.jsonl")
            .read_text()
            .splitlines()[0]
        )["line"]
        + "\n"
    )
    return next(iter(CsiReplay(p)))


@pytest.mark.parametrize(
    "field,value", [("domain", "other-clock"), ("tick_hz", 500000), ("wrap_bits", None)]
)
def test_clock_contract_change_negative_control(observation, field, value):
    r = default_registry()
    r.ingest(observation, 0)
    d = observation.to_dict()
    d["seq"] += 1
    d["id"] = "next"
    d["acquisition"][field] = value
    d["acquisition"]["ticks"] += 10000
    d["acquisition"]["unwrapped_ticks"] += 10000
    with pytest.raises(ContractError):
        r.ingest(Observation(d), 1)
    assert r.streams[d["sensor_id"]].received == 1


def test_negative_variance_negative_control(observation):
    d = observation.to_dict()
    d["uncertainty"] = {
        "kind": "covariance",
        "variables": ["x:m"],
        "covariance": [[-1e-11]],
    }
    with pytest.raises(ContractError):
        Observation(d)


def test_nonfinite_numpy_json_negative_control():
    m = Measurement(
        "synthetic",
        "example",
        1,
        "f",
        {"a": np.array([np.nan, np.inf]), "b": np.float64(np.nan)},
        Provenance("s", "synthetic", "raw"),
    )
    d = json.loads(
        m.to_json(), parse_constant=lambda x: pytest.fail("Nonstandard JSON " + x)
    )
    assert d["value"] == {"a": [None, None], "b": None}


@pytest.mark.parametrize("cov", [[[float("inf")]], [[-1.0]], [[1.0, 2.0], [2.0, 1.0]]])
def test_legacy_covariance_negative_control(cov):
    with pytest.raises(ValueError):
        Measurement(
            "synthetic",
            "x",
            1,
            "f",
            {},
            Provenance("s", "synthetic", "raw"),
            covariance=cov,
        )


def test_sign_roundtrip_whitespace_positive_control():
    assert json.loads(verify(sign('{"x": 1}', b"x" * 32), b"x" * 32)) == {"x": 1}


@pytest.mark.parametrize(
    "boot,seq",
    [("", 1), ("epoch", -1), ("epoch", True), ("epoch", 1.5), ("epoch", "1")],
)
def test_replay_header_negative_control(boot, seq):
    assert not ReplayGuard().check("peer", boot, seq)


def test_malformed_signed_packet_cannot_poison_valid_sequence():
    key = b"x" * 32
    t = UdpMulticastTransport(key, unit_id="self", loopback_only=True)
    bad = {
        "schema": 1,
        "type": "unknown",
        "unit_id": "peer",
        "seq": 99,
        "boot": "epoch",
        "t_host": 1,
    }
    t._local = [
        sign(json.dumps(bad), key).encode(),
        sign(Heartbeat("peer", 1, 1, boot="epoch").to_json(), key).encode(),
    ]
    assert len(t.receive()) == 1


@pytest.mark.parametrize(
    "body",
    [
        [],
        {
            "schema": 1,
            "type": "heartbeat",
            "unit_id": "peer",
            "seq": None,
            "boot": "epoch",
            "t_host": 1,
        },
        {
            "schema": 1,
            "type": "heartbeat",
            "unit_id": "peer",
            "seq": 1,
            "boot": "epoch",
            "t_host": float("nan"),
        },
    ],
)
def test_signed_malformed_shapes_are_dropped(body):
    key = b"x" * 32
    t = UdpMulticastTransport(key, unit_id="self", loopback_only=True)
    import hmac, hashlib

    inner = json.dumps(body, separators=(",", ":"))
    env = json.dumps(
        {"msg": body, "sig": hmac.new(key, inner.encode(), hashlib.sha256).hexdigest()}
    )
    t._local = [env.encode()]
    assert t.receive() == []


def test_future_time_negative_control():
    assert ClockSync().is_stale(1e20, local_t=1)
    assert ClockSync().is_stale(float("nan"), local_t=1)
    assert not ClockSync().is_stale(1, local_t=1.5)


def test_replaced_catalog_path_negative_control(tmp_path):
    root = tmp_path / "approved"
    root.mkdir()
    p = root / "report.json"
    p.write_text("safe")
    outside = tmp_path / "outside.json"
    outside.write_text("canary")
    items = catalog([root])
    p.unlink()
    p.symlink_to(outside)
    handler = object.__new__(Handler)
    handler.server = SimpleNamespace(items=items)
    with pytest.raises(ValueError):
        handler.item("0", "evidence")


def test_fragmented_echo_positive_control():
    from specter.sensors.di188.driver import DI188Driver

    d = DI188Driver("/fake")
    d._pending_echo = b"start"
    assert d._consume_echo(b"sta") == b""
    assert d._consume_echo(b"rt1 2\r") == b"1 2\r"


def test_fragmented_gnss_positive_control():
    from specter.sensors.gnss.neom9n import Neom9nDriver, build_nav_pvt

    data = build_nav_pvt()
    for split in range(1, len(data)):
        d = Neom9nDriver()
        result = d.feed(data[:split]) + d.feed(data[split:])
        assert len(result) == 1, split


@pytest.mark.parametrize("session", ["../escape", "/absolute", "a/b"])
def test_event_session_cannot_escape_or_reuse(tmp_path, session):
    from specter.events.log import EventLog

    with pytest.raises(ValueError):
        EventLog(tmp_path, session)


def test_event_log_rejects_duplicate_session_and_nonfinite_detail(tmp_path):
    from specter.events.log import EventLog

    log = EventLog(tmp_path, "control")
    try:
        with pytest.raises(FileExistsError):
            EventLog(tmp_path, "control")
        with pytest.raises(ValueError):
            log.log("bad", {"value": float("nan")})
        assert log.log("valid")["seq"] == 1
        assert len(log.path.read_text().splitlines()) == 1
    finally:
        log.close()


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1.0])
def test_gas_invalid_values_never_report_ok(value):
    from specter.sensors.experimental.gas import danger_level, gas_measurement

    assert danger_level(value, 450) == "UNKNOWN"
    with pytest.raises(ValueError):
        gas_measurement(value, 450)


def test_thermal_variation_is_not_measurement_uncertainty():
    from specter.sensors.thermal.interface import thermal_measurement

    frame = np.array([[20, 30], [25, 22]])
    m = thermal_measurement(frame, sensor_id="test", algorithm="test")
    assert m.confidence is None and m.covariance is None
    assert m.value["verified"] is False
    assert m.value["spatial_variance_c2"] == np.var(frame)
    for bad in (np.array([]), np.array([1, 2]), np.array([[np.nan]])):
        with pytest.raises(ValueError):
            thermal_measurement(bad, sensor_id="test", algorithm="test")
    with pytest.raises(ValueError):
        thermal_measurement(
            frame, sensor_id="test", algorithm="test", sim=True, verified=True
        )


def test_ekf_prediction_advances_clock_and_expires_gnss():
    from specter.localization.ekf import PoseEKF
    from specter.sensors.gnss.neom9n import Neom9nDriver, build_nav_pvt

    ekf = PoseEKF("test")
    m = Neom9nDriver().feed(build_nav_pvt())[0]
    ekf.update_gnss(m)
    old = ekf.pose().t
    pose = ekf.predict(6.0)
    assert pose.t == old + 6.0 and pose.mode == "REL"
    for dt in (-1, float("nan"), float("inf")):
        with pytest.raises(ValueError):
            ekf.predict(dt)
    with pytest.raises(ValueError):
        ekf.predict(1, t=old)


@pytest.mark.parametrize(
    "field,value",
    [
        ("position_enu", [1, 2]),
        ("position_enu", ["nan", 0, 0]),
        ("cov_3x3", [[-1, 0, 0], [0, 1, 0], [0, 0, 1]]),
        ("cov_3x3", [[1, 2, 0], [2, 1, 0], [0, 0, 1]]),
        ("confidence", "nan"),
        ("confidence", 2),
        ("boot", None),
        ("measurement_ids", "parent"),
    ],
)
def test_network_semantics_reject_invalid_vectors_and_numeric_strings(field, value):
    from specter.net.messages import TrackReport, decode_message

    d = json.loads(TrackReport("peer", 1, 1, 1, [0, 0, 0], np.eye(3)).to_json())
    d[field] = value
    with pytest.raises(ValueError):
        decode_message(json.dumps(d))
