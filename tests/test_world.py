"""WORLD failure controls: isolated recordings, no device access."""

import json
from pathlib import Path
import threading
import time
import urllib.error
import urllib.request

import pytest
from specter.platform.replay import CsiReplay, write_capture
from specter.platform.observation import Observation, ContractError
from specter.world.store import WorldStore
from specter.world.server import WorldServer, catalog
from specter.world.ingress import Ingress

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def raw(tmp_path):
    line = json.loads(
        (ROOT / "tests/fixtures/esp32_csi/phone_station_lltf.jsonl")
        .read_text()
        .splitlines()[0]
    )["line"]
    path = tmp_path / "real.raw.csi"
    path.write_text(line + "\n")
    return path


@pytest.fixture
def store():
    s = WorldStore()
    yield s
    s.close()


def wait(s):
    s.worker.join(10)
    assert not s.worker.is_alive()
    return s.snapshot()


def test_world_source_identity_negative_control(store, raw):
    store.load(raw)
    d = wait(store)
    assert d["status"] == "READY" and d["mode"] == "REPLAY"
    assert d["observation"]["origin"] == "hardware"
    assert d["observation"]["received"]["time_ns"] is None
    raw.write_text(raw.read_text() + "# changed artifact\n")
    store.load(raw)
    d = wait(store)
    assert d["observation"]["origin"] == "unknown"
    assert not d["live_verified"]


def test_world_replay_exact_and_filtered(store, raw):
    original = next(iter(CsiReplay(raw)))
    store.load(raw)
    d = wait(store)
    assert d["observation"] == original.to_dict()
    assert store.snapshot(query="impossible")["rows"] == []
    assert store.snapshot(source="future/thermal")["rows"] == []
    store.control("seek", 0)
    assert store.snapshot()["observation"] == original.to_dict()
    store.control("disconnect")
    assert store.snapshot()["status"] == "DISCONNECTED"
    with pytest.raises(ValueError):
        store.control("play", True)
    store.load(raw)
    assert wait(store)["status"] == "READY"


def test_world_malformed_duplicate_negative_control(store, raw):
    raw.write_text(raw.read_text() * 2)
    store.load(raw)
    d = wait(store)
    assert d["status"] == "ERROR"
    assert "sequence" in d["error"]["message"]
    raw.write_text("CSI_DATA,broken\n")
    store.load(raw)
    d = wait(store)
    assert d["status"] == "ERROR"
    assert d["counters"]["malformed"] == 1


def test_world_simulation_never_live_negative_control(store, raw, tmp_path):
    d = next(iter(CsiReplay(raw))).to_dict()
    d.update(origin="simulated", classification="simulated")
    d["evidence"]["level"] = "simulated"
    file = tmp_path / "test.observations.jsonl"
    write_capture(file, [Observation(d)])
    store.load(file)
    s = wait(store)
    assert s["observation"]["origin"] == "simulated" and not s["live_verified"]
    assert s["mode"] == "REPLAY"
    file.write_text(file.read_text().replace("simulated", "hardware"))
    store.load(file)
    assert wait(store)["status"] == "ERROR"


def test_world_large_limit_and_random_access(raw, tmp_path):
    d = next(iter(CsiReplay(raw))).to_dict()
    file = tmp_path / "large.observations.jsonl"

    def records():
        for i in range(5000):
            item = json.loads(json.dumps(d))
            item["seq"] = i
            item["id"] = f"test:{i}"
            item["acquisition"].update(ticks=i * 100000, unwrapped_ticks=i * 100000)
            item["origin"] = "simulated"
            item["classification"] = "simulated"
            item["evidence"]["level"] = "simulated"
            yield Observation(item)

    write_capture(file, records())
    s = WorldStore(max_records=2048)
    try:
        s.load(file)
        r = wait(s)
        assert r["count"] == 2048 and r["limited"]
        assert len(s.snapshot(index=2047)["rows"]) == 80
        assert len(s.snapshot(index=2047)["series"]) == 160
        assert s.snapshot(index=2047)["health"]["buffer_evictions"] == 1792
        with pytest.raises(ValueError):
            s.snapshot(index=2048)
    finally:
        s.close()


@pytest.mark.parametrize(
    "action,value",
    [
        ("seek", -1),
        ("seek", True),
        ("speed", float("nan")),
        ("speed", 32),
        ("unknown", None),
    ],
)
def test_world_invalid_controls_negative_control(store, action, value):
    with pytest.raises(ValueError):
        store.control(action, value)


def test_ingress_stale_disconnect_and_duplicate_negative_control(raw):
    now = [0]
    observation = next(iter(CsiReplay(raw)))
    ingress = Ingress(capacity=1, clock=lambda: now[0])
    with pytest.raises(ContractError):
        ingress.submit(observation)
    ingress.connect_test()
    ingress.submit(observation)
    ingress.submit(observation)
    assert ingress.dropped == 1
    ingress.drain()
    assert "UNVERIFIED" in ingress.health()
    now[0] = 3_000_000_000
    assert ingress.health().startswith("STALE")
    ingress.submit(observation)
    with pytest.raises(ContractError):
        ingress.drain()
    assert ingress.state == "ERROR"
    ingress.disconnect()
    assert ingress.health() == "OFFLINE"
    assert not ingress.queue


def test_catalog_rejects_escape_symlink(raw, tmp_path):
    root = tmp_path / "approved"
    root.mkdir()
    (root / "escape.raw.csi").symlink_to(raw)
    assert catalog([root]) == []


def test_http_security_and_shutdown_negative_control(raw, store):
    server = WorldServer(("127.0.0.1", 0), store, [raw.parent])
    t = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.02})
    t.start()
    base = f"http://127.0.0.1:{server.server_port}"

    def request(path, body=None, headers=None):
        data = json.dumps(body).encode() if body is not None else None
        return urllib.request.urlopen(
            urllib.request.Request(base + path, data=data, headers=headers or {}),
            timeout=3,
        )

    try:
        assert json.load(request("/api/state"))["status"] == "OFFLINE"
        with pytest.raises(urllib.error.HTTPError) as exc:
            request("/api/control", {"action": "play", "value": True})
        assert exc.value.code == 403
        with pytest.raises(urllib.error.HTTPError) as exc:
            request("/api/state", headers={"Host": "evil.invalid"})
        assert exc.value.code == 403
        assert json.load(
            request(
                "/api/session", {"id": "0"}, headers={"X-Specter-Token": server.token}
            )
        )["ok"]
        assert wait(store)["status"] == "READY"
        with pytest.raises(urllib.error.HTTPError):
            request("/api/evidence?id=../../etc/passwd")
        assert json.load(
            request("/api/shutdown", {}, headers={"X-Specter-Token": server.token})
        )["ok"]
        t.join(3)
        assert not t.is_alive()
    finally:
        server.shutdown()
        server.server_close()
        t.join(3)


@pytest.mark.parametrize(
    "bad_value",
    [
        {"amplitudes": "not an array"},
        {"amplitudes": [1] * 64},
        {"amplitudes": [-1] * 64},
    ],
)
def test_world_payload_semantics_negative_control(store, raw, tmp_path, bad_value):
    d = next(iter(CsiReplay(raw))).to_dict()
    d["value"] = bad_value
    path = tmp_path / "bad.observations.jsonl"
    write_capture(path, [Observation(d)])
    store.load(path)
    result = wait(store)
    assert result["status"] == "ERROR" and result["count"] == 0
    assert result["error"]["code"] == "ContractError"


def test_world_disconnect_while_loading_stays_detached(store, raw, monkeypatch):
    original = CsiReplay.__iter__
    entered = threading.Event()
    release = threading.Event()

    def delayed(self):
        entered.set()
        assert release.wait(2)
        yield from original(self)

    monkeypatch.setattr(CsiReplay, "__iter__", delayed)
    store.load(raw)
    assert entered.wait(2)
    store.control("disconnect")
    release.set()
    store.worker.join(3)
    assert store.snapshot()["status"] == "DISCONNECTED"


def test_world_play_boolean_negative_control(store, raw):
    store.load(raw)
    wait(store)
    with pytest.raises(ValueError):
        store.control("play", "false")


def test_world_changing_source_negative_control(store, raw, monkeypatch):
    original = CsiReplay.__iter__

    def mutated(self):
        yield from original(self)
        raw.write_text(raw.read_text() + "# modified after parsing\n")

    monkeypatch.setattr(CsiReplay, "__iter__", mutated)
    store.load(raw)
    d = wait(store)
    assert d["status"] == "ERROR" and "integrity" in d["error"]["message"]


def test_world_concurrent_source_switches_are_serialized(store, raw):
    errors = []

    def load():
        try:
            store.load(raw)
        except Exception as exc:
            errors.append(str(exc))

    threads = [threading.Thread(target=load) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(4)
    result = wait(store)
    assert not errors
    assert result["status"] == "READY" and result["count"] == 1
    store.close()
    store.close()
    with pytest.raises(RuntimeError):
        store.load(raw)
