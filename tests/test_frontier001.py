"""Adversarial FRONTIER boundary tests. No device/camera access."""

import copy
import hashlib
import json
from pathlib import Path
import numpy as np
import pytest
from specter.platform.observation import Observation, ContractError, from_legacy
from specter.platform.replay import (
    CsiReplay,
    TickEpoch,
    write_capture,
    read_capture,
    load_source,
)
from specter.platform.registry import Registry, ReplaySession, default_registry
from specter.fusion.measurement import Measurement, Provenance

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def raw(tmp_path):
    # Exact committed real hardware fixture; label wrapper isn't a capture.
    fixture = json.loads(
        (ROOT / "tests/fixtures/esp32_csi/phone_station_lltf.jsonl")
        .read_text()
        .splitlines()[0]
    )["line"]
    p = tmp_path / "real.raw.csi"
    p.write_text(fixture + "\n")
    return p


@pytest.fixture
def observation(raw):
    return next(iter(CsiReplay(raw)))


def test_legacy_contract_not_extended_by_default():
    m = Measurement(
        "wifi_csi",
        "old",
        123.0,
        "old-frame",
        {"a": 1},
        Provenance("old", "wifi_csi", "old"),
    )
    d = m.to_dict()
    assert "schema_version" not in d and "evidence_level" not in d
    v = from_legacy(m).to_dict()
    assert v["origin"] == "unknown" and v["classification"] == "unknown"
    assert (
        v["validity"]["state"] == "unknown" and v["evidence"]["level"] == "unverified"
    )
    assert v["received"]["time_ns"] is None and v["value"]["original_t_host"] == 123


def test_roundtrip_immutability_and_explicit_hardware(observation):
    d = observation.to_dict()
    d["value"]["amplitudes"][0] = 999
    assert observation.to_dict()["value"]["amplitudes"][0] != 999
    assert Observation.from_json(observation.to_json()) == observation
    d = observation.to_dict()
    assert d["classification"] == "measured" and d["origin"] == "hardware"
    assert d["received"]["time_ns"] is None and d["acquisition"]["ticks"] is not None


@pytest.mark.parametrize(
    "change",
    [
        lambda d: d.update(schema="specter.observation/2.0.0"),
        lambda d: d.update(units=""),
        lambda d: d.update(seq=True),
        lambda d: d.update(seq=-1),
        lambda d: d.update(dropped_before=-1),
        lambda d: d.update(value={"bad": float("nan")}),
        lambda d: d["acquisition"].update(tick_hz=float("inf")),
        lambda d: d["acquisition"].update(ticks=2**32),
        lambda d: d["calibration"].update(status="calibrated"),
        lambda d: d.update(origin="simulated"),
        lambda d: d["evidence"].update(raw=None),
        lambda d: d["received"].update(time_ns=-1),
        lambda d: d["evidence"]["raw"].update(sha256="not-a-hash"),
        lambda d: d.update(unknown_field="future"),
        lambda d: d.update(classification="inferred"),
    ],
)
def test_contract_rejects_adversarial_mutations(observation, change):
    d = observation.to_dict()
    change(d)
    with pytest.raises(ContractError):
        Observation(d)


@pytest.mark.parametrize(
    "cov",
    [
        [[1, 2], [2, 1]],
        [[1, 0], [1, 1]],
        [[float("inf"), 0], [0, 1]],
        [[True, 0], [0, 1]],
        [[1]],
        [],
    ],
)
def test_covariance_negative_control(observation, cov):
    d = observation.to_dict()
    d["uncertainty"] = dict(kind="covariance", variables=["x:m", "y:m"], covariance=cov)
    with pytest.raises(ContractError):
        Observation(d)


def test_covariance_positive_semidefinite(observation):
    d = observation.to_dict()
    d["uncertainty"] = dict(
        kind="covariance", variables=["x:m", "y:m"], covariance=[[1, 1], [1, 1]]
    )
    assert Observation(d)


def test_duplicate_json_and_missing_required_fields(observation):
    with pytest.raises(ContractError):
        Observation.from_json('{"schema":"one","schema":"two"}')
    d = observation.to_dict()
    del d["classification"]
    with pytest.raises(ContractError):
        Observation(d)


def test_simulated_cannot_upgrade_evidence(observation):
    d = observation.to_dict()
    d.update(origin="simulated", classification="simulated")
    d["evidence"]["level"] = "simulated"
    o = Observation(d)
    assert o.to_dict()["origin"] == "simulated"
    d["evidence"]["level"] = "recorded_hardware"
    with pytest.raises(ContractError):
        Observation(d)


def test_capture_byte_determinism_integrity_and_no_overwrite(tmp_path, observation):
    a = tmp_path / "a.jsonl"
    b = tmp_path / "b.jsonl"
    write_capture(a, [observation])
    write_capture(b, [observation])
    assert a.read_bytes() == b.read_bytes()
    assert list(read_capture(a)) == [observation]
    with pytest.raises(FileExistsError):
        write_capture(a, [observation])
    a.write_text(a.read_text().replace("csi_lltf_amplitude", "tampered"))
    with pytest.raises(ContractError):
        list(read_capture(a))


def test_truncated_manifest_negative_control(tmp_path, observation):
    p = tmp_path / "capture.jsonl"
    write_capture(p, [observation])
    p.write_text("")
    with pytest.raises(ContractError):
        list(read_capture(p))


def test_wrap_and_discontinuity_never_invent_boot_identity():
    c = TickEpoch()
    c.push(2**32 - 10)
    tick, ep, flags = c.push(12)
    assert (
        tick == 2**32 + 12 and flags == ["counter_wrap"] and ep == "unrecorded-epoch-0"
    )
    tick, ep, flags = c.push(1)
    assert ep == "unrecorded-epoch-1" and "clock_discontinuity" in flags


def test_parser_replay_counts_gaps_malformed_and_masks_invalid(raw):
    line = raw.read_text()
    head, tail = line.split('"', 1)
    cols = head.rstrip(",").split(",")
    seq = int(cols[1])
    cols[1] = str(seq + 2)
    cols[23] = "1"
    second = ",".join(cols) + ',"' + tail
    raw.write_text(line + "CSI_DATA,broken\n" + second)
    adapter = CsiReplay(raw)
    obs = list(adapter)
    assert (
        len(obs) == 2
        and adapter.counts["malformed"] == 1
        and adapter.counts["sequence_missing"] == 1
    )
    assert obs[1].to_dict()["value"]["amplitudes"][:2] == [None, None]
    assert obs[1].to_dict()["dropped_before"] == 1


def test_duplicate_raw_sequence_is_not_silently_replayed(raw):
    raw.write_text(raw.read_text() * 2)
    with pytest.raises(ContractError):
        list(CsiReplay(raw))


def test_bounded_loading_and_unsupported_layout(raw):
    line = raw.read_text()
    rows = []
    for i in range(4):
        head, tail = line.split('"', 1)
        cols = head.rstrip(",").split(",")
        cols[1] = str(100 + i)
        rows.append(",".join(cols) + ',"' + tail)
    raw.write_text("".join(rows))
    observations, counts = load_source(raw, limit=2)
    assert len(observations) == 2 and counts["truncated"]
    with pytest.raises(ValueError):
        load_source(raw, limit=0)


def test_registry_strictness_bounded_accounting_stale_and_offline(observation):
    r = default_registry(2)
    d = observation.to_dict()
    for i in range(3):
        d["seq"] += 1
        d["id"] = str(i)
        r.ingest(Observation(d), i * 100)
    assert len(r.history) == 2 and r.evictions == 1
    st = r.streams["bench/esp32-s3/csi"]
    assert st.received == 3 and st.buffer_evictions == 1 and st.source_missing == 0
    assert r.streams["bench/di188/analog"].state == "OFFLINE"
    r.mark_stale(10**10)
    assert st.state == "STALE"
    r.disconnect(st.spec.sensor_id)
    assert st.state == "OFFLINE"
    with pytest.raises(ContractError):
        r.ingest(Observation(d), 10**10)
    d["seq"] += 1
    d["frame_id"] = "wrong"
    with pytest.raises(ContractError):
        default_registry().ingest(Observation(d), 0)


def test_seek_matches_fresh_replay(observation):
    obs = []
    d = observation.to_dict()
    for i in range(4):
        d["seq"] += 1
        obs.append(Observation(d))
    s = ReplaySession(obs, 2)
    s.seek(3)
    expected = [o.to_json() for o in s.registry.history]
    s.seek(0)
    s.seek(3)
    assert [
        o.to_json() for o in s.registry.history
    ] == expected and s.registry.evictions == 2


def test_console_never_opens_camera_and_renders_both_sizes(tmp_path, raw, monkeypatch):
    import specter.app as app

    monkeypatch.setattr(
        app, "open_camera", lambda *a, **k: pytest.fail("camera access")
    )
    for size in ["800x480", "1440x900"]:
        p = tmp_path / (size + ".png")
        assert (
            app.main(
                [
                    "--console",
                    "--replay",
                    str(raw),
                    "--headless",
                    "--console-size",
                    size,
                    "--save-frame",
                    str(p),
                ]
            )
            == 0
        )
        import cv2

        image = cv2.imread(str(p))
        assert image.shape[:2] == tuple(reversed([int(x) for x in size.split("x")]))
        assert np.std(image) > 10


def test_console_empty_offline_evidence_and_nodes():
    from specter.hud.console import render_console

    for page in ["streams", "evidence", "nodes"]:
        assert render_console(None, 800, 480, page).shape == (480, 800, 3)


def test_registry_rejected_timestamp_does_not_advance_count(observation):
    r = default_registry()
    d = observation.to_dict()
    r.ingest(observation, 0)
    d["seq"] += 1
    d["acquisition"]["unwrapped_ticks"] -= 1
    with pytest.raises(ContractError):
        r.ingest(Observation(d), 100)
    assert r.streams[d["sensor_id"]].received == 1


def test_missing_manifest_and_unknown_registry_source(tmp_path, observation):
    p = tmp_path / "capture.jsonl"
    p.write_text(observation.to_json())
    with pytest.raises(ContractError):
        list(read_capture(p))
    d = observation.to_dict()
    d["sensor_id"] = "unregistered"
    with pytest.raises(ContractError):
        default_registry().ingest(Observation(d), 0)


def test_registry_rejects_false_drop_accounting(observation):
    r = default_registry()
    r.ingest(observation, 0)
    d = observation.to_dict()
    d["seq"] += 3
    with pytest.raises(ContractError):
        r.ingest(Observation(d), 100)
    assert r.streams[d["sensor_id"]].received == 1


def test_arbitrary_csi_text_is_unknown_not_hardware(raw):
    raw.write_text(raw.read_text().replace(",-38,", ",-39,"))
    o = next(iter(CsiReplay(raw))).to_dict()
    assert o["origin"] == "unknown" and o["evidence"]["level"] == "unverified"
    assert "source_origin_unverified" in o["validity"]["flags"]


def test_new_epoch_clears_old_acquisition_rate(observation):
    r = default_registry()
    d = observation.to_dict()
    r.ingest(Observation(d), 0)
    d["seq"] += 1
    d["acquisition"]["unwrapped_ticks"] += 100000
    r.ingest(Observation(d), 100)
    assert r.streams[d["sensor_id"]].rate_hz == pytest.approx(10)
    d["seq"] = 0
    d["acquisition"]["epoch"] = "unrecorded-epoch-1"
    d["acquisition"]["ticks"] = 1
    d["acquisition"]["unwrapped_ticks"] = 1
    r.ingest(Observation(d), 200)
    assert r.streams[d["sensor_id"]].rate_hz is None


def test_existing_orphan_manifest_is_never_overwritten(tmp_path, observation):
    p = tmp_path / "capture.jsonl"
    m = Path(str(p) + ".manifest.json")
    m.write_text("private-existing")
    with pytest.raises(FileExistsError):
        write_capture(p, [observation])
    assert not p.exists() and m.read_text() == "private-existing"


def test_untrusted_field_types_raise_contract_errors(observation):
    for mutate in (
        lambda d: d["validity"].update(flags=[[]]),
        lambda d: d.update(acquisition=None),
        lambda d: d["uncertainty"].update(
            kind="covariance", variables=["x:m"], covariance=[[False]]
        ),
    ):
        d = observation.to_dict()
        mutate(d)
        with pytest.raises(ContractError):
            Observation(d)
