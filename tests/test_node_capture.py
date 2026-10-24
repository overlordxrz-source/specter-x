"""Bounded byte-transport controls; never opens physical devices."""
import io
import json
from pathlib import Path
import threading

import pytest

from specter.node.csi_capture import main, record_session
from specter.platform.replay import read_capture
from specter.world.store import WorldStore


class Clock:
    def __init__(self):
        self.value = 0

    def __call__(self):
        self.value += 100_000_000
        return self.value


class Chunks:
    def __init__(self, chunks):
        self.chunks = iter(chunks)
        self.closed = False

    def read(self, size):
        item = next(self.chunks, b"")
        if isinstance(item, Exception):
            raise item
        return item

    def close(self):
        self.closed = True


@pytest.fixture
def line():
    path = Path(__file__).parent / "fixtures/esp32_csi/phone_station_lltf.jsonl"
    return (json.loads(path.read_text().splitlines()[0])["line"] + "\n").encode()


def test_fragmented_raw_roundtrips_into_world(tmp_path, line):
    reader = Chunks([line[:13], line[13:]])
    directory = tmp_path / "session"
    status = record_session(reader, directory, transport="file", clock=Clock())
    assert status["state"] == "COMPLETE" and reader.closed
    assert status["bytes"] == status["read_bytes"] == len(line)
    assert status["rejected_bytes"] == 0
    assert status["raw_file_bytes"] == len(line) and status["unaccounted_bytes"] == 0
    assert (directory / "session.raw.csi").read_bytes() == line
    capture = directory / "session.observations.jsonl"
    obs, = list(read_capture(capture))
    assert obs.to_dict()["received"]["time_ns"] is None
    store = WorldStore()
    try:
        store.load(capture)
        store.worker.join(5)
        state = store.snapshot()
        assert state["status"] == "READY" and state["count"] == 1
        assert state["mode"] == "REPLAY" and not state["live_verified"]
        assert state["observation"] == obs.to_dict()
    finally:
        store.close()


def test_serial_double_maps_receive_upper_bound_without_promoting_origin(tmp_path, line):
    # Fake transport only: serial label cannot establish hardware provenance.
    reader = Chunks([line[:13], line[13:]])
    directory = tmp_path / "session"
    status = record_session(reader, directory, transport="serial",
        duration_s=.8, stall_s=1., clock=Clock())
    assert status["state"] == "COMPLETE" and status["reason"] == "duration"
    obs, = list(read_capture(directory / "session.observations.jsonl"))
    data = obs.to_dict()
    events = [json.loads(s) for s in (directory / "receipts.jsonl").read_text().splitlines()]
    assert data["received"]["time_ns"] == events[1]["read_completed_ns"]
    assert status["session_id"] in data["received"]["domain"]
    assert "receive_time_is_chunk_completion" in data["validity"]["flags"]
    assert data["origin"] == "unknown"  # even replaying the frozen fixture over a port
    assert data["evidence"]["level"] == "unverified"
    assert not status["live_verified"]


def test_unknown_bytes_are_never_promoted_by_serial_label(tmp_path, line):
    reader = Chunks([b"# different artifact\n" + line])
    directory = tmp_path / "session"
    status = record_session(reader, directory, transport="serial",
        duration_s=.6, stall_s=1., clock=Clock())
    assert status["state"] == "COMPLETE"
    obs, = list(read_capture(directory / "session.observations.jsonl"))
    assert obs.to_dict()["origin"] == "unknown"
    assert obs.to_dict()["classification"] == "unknown"


@pytest.mark.parametrize("transport", ["file", "serial"])
def test_read_error_preserves_partial_bytes_and_failed_state(tmp_path, line, transport):
    reader = Chunks([line, OSError("injected disconnect")])
    directory = tmp_path / "session"
    status = record_session(reader, directory, transport=transport, clock=Clock())
    assert status["state"] == "FAILED" and reader.closed
    assert "injected disconnect" in status["error"]
    assert (directory / "session.raw.csi").read_bytes() == line
    assert not (directory / "session.observations.jsonl.manifest.json").exists()


def test_silent_port_stalls_and_closes(tmp_path):
    reader = Chunks([])
    status = record_session(reader, tmp_path / "session", transport="serial",
        stall_s=.5, clock=Clock())
    assert status["state"] == "FAILED" and reader.closed
    assert "stall" in status["error"]


def test_cancellation_never_claims_complete(tmp_path):
    reader = Chunks([])
    stop = threading.Event()
    stop.set()
    status = record_session(reader, tmp_path / "session", transport="serial",
        clock=Clock(), stop=stop)
    assert status["state"] == "CANCELLED" and reader.closed


@pytest.mark.parametrize("option,value", [("max_bytes", 2), ("max_reads", 1)])
def test_limits_fail_with_explicit_rejected_byte_accounting(tmp_path, line, option, value):
    reader = Chunks([line, line])
    status = record_session(reader, tmp_path / "session", transport="file",
        clock=Clock(), **{option: value})
    assert status["state"] == "FAILED" and reader.closed
    assert status["read_bytes"] == status["bytes"] + status["rejected_bytes"]
    assert status["rejected_bytes"] == len(line)


@pytest.mark.parametrize("data", [b"", b"unrecognized\n", b"CSI_DATA,broken\n", b"\xff\n"])
def test_empty_bad_or_undecodable_input_is_not_complete(tmp_path, data):
    status = record_session(io.BytesIO(data), tmp_path / "session", transport="file")
    assert status["state"] == "FAILED"
    assert not (tmp_path / "session/session.observations.jsonl.manifest.json").exists()


def test_existing_directory_and_invalid_options_close_without_overwriting(tmp_path):
    marker = tmp_path / "keep"
    marker.write_text("preserve")
    reader = Chunks([])
    with pytest.raises(FileExistsError):
        record_session(reader, tmp_path, transport="file")
    assert reader.closed and marker.read_text() == "preserve"
    for duration in (float("nan"), float("inf"), -1.):
        reader = Chunks([])
        with pytest.raises(ValueError):
            record_session(reader, tmp_path / "unused", transport="file", duration_s=duration)
        assert reader.closed and not (tmp_path / "unused").exists()


def test_cli_rejects_device_operation_without_explicit_opt_in(tmp_path):
    with pytest.raises(SystemExit) as caught:
        main(["--port", "/dev/DO_NOT_OPEN", "--out", str(tmp_path / "session")])
    assert caught.value.code == 2
    assert not (tmp_path / "session").exists()


def test_close_failure_is_reported_before_finalizing(tmp_path, line):
    class BadClose(Chunks):
        def close(self):
            self.closed = True
            raise OSError("injected close failure")
    reader = BadClose([line])
    directory = tmp_path / "session"
    status = record_session(reader, directory, transport="file")
    assert status["state"] == "FAILED" and reader.closed
    assert "close failed" in status["error"]
    assert not (directory / "session.observations.jsonl.manifest.json").exists()


def test_cli_configures_bounded_exclusive_serial_without_real_device(tmp_path, monkeypatch, line):
    args_seen = []
    def open_double(port, baud):
        args_seen.append((port, baud))
        return Chunks([line, OSError("end of test")])
    monkeypatch.setattr("specter.node.csi_capture.open_serial", open_double)
    assert main(["--port", "FAKE_ONLY", "--allow-hardware", "--out",
        str(tmp_path / "session")]) == 2
    assert args_seen == [("FAKE_ONLY", 115200)]


@pytest.mark.parametrize("data", [b"x" * 16385, None])
def test_parser_failure_after_good_data_has_no_completion_manifest(tmp_path, line, data):
    # A duplicate sequence or overlong line must not become a usable partial
    # session merely because its first observation was valid.
    payload = line + (line if data is None else data)
    reader = io.BytesIO(payload)
    directory = tmp_path / "session"
    status = record_session(reader, directory, transport="file")
    assert status["state"] == "FAILED" and reader.closed
    assert (directory / "session.raw.csi").read_bytes() == payload
    assert not (directory / "session.observations.jsonl.manifest.json").exists()


def test_read_and_close_failures_are_both_preserved(tmp_path):
    class BadClose(Chunks):
        def close(self):
            raise OSError("close failed too")
    status = record_session(BadClose([OSError("read failed first")]),
        tmp_path / "session", transport="file")
    assert len(status["errors"]) == 2
    assert "read failed first" in status["error"] and "close failed too" in status["error"]


def test_oversized_reader_result_is_counted_as_rejected(tmp_path):
    status = record_session(Chunks([b"x"*4097]), tmp_path / "session", transport="file")
    assert status["state"] == "FAILED"
    assert status["read_bytes"] == status["rejected_bytes"] == 4097
    assert status["raw_file_bytes"] == status["unaccounted_bytes"] == 0


def test_bad_cli_limits_never_call_serial_owner(tmp_path, monkeypatch):
    def forbidden(*args):
        pytest.fail("serial owner was called before validating limits")
    monkeypatch.setattr("specter.node.csi_capture.open_serial", forbidden)
    with pytest.raises(SystemExit):
        main(["--port", "FAKE_ONLY", "--allow-hardware", "--max-bytes", "0",
            "--out", str(tmp_path / "session")])
