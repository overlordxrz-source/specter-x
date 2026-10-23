"""WORLD failure controls: isolated recordings, no device access."""

import json
from pathlib import Path
import threading
import time
import urllib.error
import urllib.request

import pytest
import specter.world.server as world_server
from specter.platform.replay import CsiReplay, write_capture
from specter.platform.observation import Observation, ContractError
from specter.world.store import WorldStore
from specter.world.server import (CATALOG_LIMIT, WorldServer,
                                  approved_roots, catalog, catalog_result)
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


def test_replay_does_not_implicitly_authorize_its_parent(raw, tmp_path):
    sibling = tmp_path / "private-note.md"
    sibling.write_text("should not be browsable")
    assert approved_roots([], raw) == []
    store = WorldStore()
    server = WorldServer(("127.0.0.1", 0), store, approved_roots([], raw))
    try:
        assert server.items == []
    finally:
        server.server_close()
        store.close()


def test_catalog_stops_at_the_bounded_limit(tmp_path):
    root = tmp_path / "large"
    root.mkdir()
    for i in range(CATALOG_LIMIT + 40):
        (root / f"evidence-{i:04d}.md").write_text("x")
    result = catalog_result([root])
    items = result["items"]
    assert len(items) == CATALOG_LIMIT
    assert result["truncated"] is True
    assert result["limit"] == CATALOG_LIMIT
    assert [i["name"] for i in items] == sorted(i["name"] for i in items)


def test_catalog_has_a_separate_scan_bound(tmp_path, monkeypatch):
    root = tmp_path / "flat"
    root.mkdir()
    for i in range(80):
        (root / f"evidence-{i:03d}.md").write_text("x")
    monkeypatch.setattr(world_server, "SCAN_LIMIT", 32)
    result = catalog_result([root])
    assert result["scan_truncated"] is True
    assert result["truncated"] is True
    assert result["scan_limit"] == 32
    assert len(result["items"]) <= 32


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
        cat = json.load(request("/api/catalog"))
        assert isinstance(cat, dict) and isinstance(cat["items"], list)
        assert isinstance(cat["truncated"], bool) and cat["limit"] == CATALOG_LIMIT
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


def test_history_is_exact_masked_source_data(store, raw):
    import csv
    import io
    fields = next(csv.reader([raw.read_text().strip()]))
    fields[23] = '1'  # explicit hardware-invalid first word in synthetic fixture
    output = io.StringIO()
    csv.writer(output).writerow(fields)
    raw.write_text(output.getvalue())
    expected = next(iter(CsiReplay(raw))).to_dict()['value']
    store.load(raw)
    d = wait(store)
    point = d['series'][0]
    assert point['amplitudes'] == expected['amplitudes']
    assert any(v is None for v in point['amplitudes'])
    assert point['sig_len'] == expected['sig_len_bytes']
    assert point['phy_rate'] == expected['phy_rate_code']
