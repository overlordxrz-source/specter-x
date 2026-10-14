"""Networking + team sim: signed messages, HMAC rogues, stale drops, 2-unit walk."""
import time

import numpy as np
import pytest

from specter.net import (
    Alert, BusHub, ClockSync, Heartbeat, PoseStamped, TrackReport,
    UdpMulticastTransport, decode_message, generate_key, sign, verify,
)
from specter.sim.team import main as team_main, run_team


def _tx(uid="unit-1", **kw):
    return UdpMulticastTransport(key=kw.pop("key", generate_key()),
                                 unit_id=uid, loopback_only=True, **kw)


def test_message_roundtrip_keeps_provenance():
    hb = Heartbeat("unit-1", 1, time.time(), "GNSS", 1.2)
    assert decode_message(hb.to_json()).mode == "GNSS"
    tr = TrackReport("unit-1", 2, time.time(), 7, [1, 2, 0], np.eye(3),
                     "unit-1", "thermal", ["m-abc", "m-def"], 0.8)
    back = decode_message(tr.to_json())
    assert back.measurement_ids == ["m-abc", "m-def"]  # provenance survives
    assert back.source_unit == "unit-1" and back.source_sensor == "thermal"
    assert back.hud_tag == "SRC: unit-1/THERMAL conf 0.80"
    ps = PoseStamped("unit-2", 3, time.time(), [1, 2, 3], [0, 0, 0],
                     np.eye(3).tolist(), "REL", None)
    assert decode_message(ps.to_json()).position_enu == [1.0, 2.0, 3.0]
    al = Alert("unit-2", 4, time.time(), "man-down", {"peer": "unit-1"})
    assert decode_message(al.to_json()).kind == "man-down"
    with pytest.raises(ValueError):
        decode_message('{"schema": 999, "type": "heartbeat"}')


def test_hmac_blocks_rogue_node():
    key, rogue = generate_key(), generate_key()
    env = sign(Heartbeat("unit-1", 1, time.time()).to_json(), key)
    assert decode_message(verify(env, key)).unit_id == "unit-1"
    with pytest.raises(ValueError):
        verify(env, rogue)  # rogue key cannot forge
    tampered = env.replace("unit-1", "unit-9")
    with pytest.raises(ValueError):
        verify(tampered, key)


def test_transport_delivers_and_drops_self_stale_rogue():
    key = generate_key()
    hub = BusHub()
    a = _tx("unit-1", key=key, hub=hub)
    b = _tx("unit-2", key=key, hub=hub)
    a.send(Heartbeat("unit-1", 1, time.time()))
    assert b.receive() and not a.receive()  # B hears A; A skips its own copy
    # stale message dropped
    a.send(Heartbeat("unit-1", 2, time.time() - 60.0))
    assert b.receive(clock=ClockSync(max_age_s=2.0)) == []
    # rogue datagram dropped
    hub.publish(sign(Heartbeat("unit-9", 1, time.time()).to_json(), generate_key()).encode())
    assert b.receive() == []
    a.close(); b.close()


def test_clock_offsets_logged():
    c = ClockSync()
    assert c.is_stale(time.time() - 10.0)
    assert not c.is_stale(time.time())
    assert c.observe("unit-2", 100.5, local_t=100.0) == 0.5
    assert c.offset("unit-9") == 0.0


def test_two_unit_team_sim_shares_tracks():
    import numpy as _np

    s = run_team(units=2, steps=20, seed=5)
    assert s["sim"] is True and set(s["modes"].values()) == {"GNSS"}
    # each unit heard the other every step (heartbeat + pose each)
    assert s["heard"]["unit-1"].get("unit-2", 0) >= 20
    assert s["heard"]["unit-2"].get("unit-1", 0) >= 20
    # the shared contact propagated as TrackReports
    assert sum(s["tracks_seen"].values()) > 0
    assert all(v < 10.0 for v in s["rmse"].values())  # honest uncertainty, bounded
    # shared ENU frame: each estimate tracks its own truth within 3 m
    truth = {"unit-1": _np.array([0.9 * 4.0, 0.15 * 4.0]),
             "unit-2": _np.array([3.0 + 0.95 * 4.0, -0.15 * 4.0])}
    for uid, t in truth.items():
        est = _np.array(s["final_enu"][uid][:2])
        assert float(_np.linalg.norm(est - t)) < 3.0, (uid, est, t)


def test_team_sim_indoor_relative_mode():
    s = run_team(units=2, steps=10, seed=5, gnss_on=False)
    assert set(s["modes"].values()) == {"REL"}


def test_team_cli(capsys):
    assert team_main(["--units", "2", "--steps", "5"]) == 0
    out = capsys.readouterr().out
    assert "TEAM-SIM" in out and "unit-1" in out
