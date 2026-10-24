"""Independent reconstructions of review 760a3f6; offline only."""
import csv
import io
import json
from pathlib import Path

import pytest

import specter.node.csi_capture as capture
from specter.sensors.imu.bno085 import Bno085Driver


@pytest.fixture
def line():
    p = Path(__file__).parent / "fixtures/esp32_csi/phone_station_lltf.jsonl"
    return (json.loads(p.read_text().splitlines()[0])["line"] + "\n").encode()


class Reader:
    def __init__(self, *chunks):
        self.items = iter(chunks)
        self.closed = False

    def read(self, size):
        value = next(self.items, b"")
        if isinstance(value, BaseException):
            raise value
        return value

    def close(self):
        self.closed = True


@pytest.mark.parametrize("filename", ["session.raw.csi", "receipts.jsonl"])
@pytest.mark.parametrize("lie", [False, True])
def test_short_writes_never_complete(tmp_path, monkeypatch, line, filename, lie):
    original = Path.open
    class ShortWriter:
        def __init__(self, f): self.f = f
        def __enter__(self): return self
        def __exit__(self, *args): return self.f.__exit__(*args)
        def __getattr__(self, name): return getattr(self.f, name)
        def write(self, data):
            written = self.f.write(data[:-1])
            return len(data) if lie else written
    def open_file(path, mode="r", *args, **kwargs):
        stream = original(path, mode, *args, **kwargs)
        return ShortWriter(stream) if path.name == filename and "x" in mode else stream
    monkeypatch.setattr(Path, "open", open_file)
    reader = Reader(line)
    status = capture.record_session(reader, tmp_path / "session", transport="file")
    assert reader.closed and status["state"] == "FAILED"
    assert status["errors"]


@pytest.mark.parametrize("stage", ["read", "finalize"])
@pytest.mark.parametrize("exception,state", [(KeyboardInterrupt, "CANCELLED"), (SystemExit, "FAILED")])
def test_baseexception_publishes_terminal_and_reraises(tmp_path, monkeypatch, line, stage, exception, state):
    reader = Reader(exception("injected")) if stage == "read" else Reader(line)
    if stage == "finalize":
        def interrupt(*args): raise exception("injected")
        monkeypatch.setattr(capture, "write_capture", interrupt)
    directory = tmp_path / "session"
    with pytest.raises(exception, match="injected"):
        capture.record_session(reader, directory, transport="file")
    status = json.loads((directory / "status.json").read_text())
    assert reader.closed and status["state"] == state
    assert status["stopped_monotonic_ns"] is not None


def test_previous_completion_is_a_monotonic_bound(tmp_path, line):
    values = iter([0, 100, 200, 150, 180, 181, 182, 183])
    status = capture.record_session(Reader(line[:13], line[13:]),
        tmp_path / "session", transport="file", clock=lambda: next(values, 500))
    assert status["state"] == "FAILED"
    assert "clock" in status["error"] or "monotonic" in status["error"]


@pytest.mark.parametrize("integer", [10**1000, -(10**1000)])
def test_nonrepresentable_integer_is_valueerror_without_state_mutation(integer):
    driver = Bno085Driver()
    with pytest.raises(ValueError):
        driver.report([integer, 0, 0, 0])
    assert driver._i == 0
    assert driver.report([1, 0, 0, 0]).provenance.frame_index == 1


def changed(line, seq=740, tick=419722600, unsupported=False):
    fields = next(csv.reader([line.decode()]))
    fields[1], fields[18] = str(seq), str(tick)
    if unsupported:
        fields[22] = "64"
        fields[-1] = json.dumps(json.loads(fields[-1])[:64], separators=(",", ":"))
    target = io.StringIO()
    csv.writer(target, lineterminator="\n").writerow(fields)
    return target.getvalue().encode()


@pytest.mark.parametrize("defect", ["gap", "malformed", "recovered", "unsupported", "clock"])
def test_dirty_capture_is_complete_but_not_accepted(tmp_path, line, defect):
    second = changed(line)
    if defect == "gap": second = changed(line, seq=742)
    if defect == "clock": second = changed(line, tick=100)
    if defect == "unsupported": second = changed(line, unsupported=True)
    data = line + second
    if defect == "malformed": data = line + b"CSI_DATA,broken\n" + second
    if defect == "recovered": data = line.rstrip(b"\n") + second
    status = capture.record_session(Reader(data), tmp_path / "session", transport="file")
    assert status["state"] == "COMPLETE"  # byte acquisition was preserved
    assert status["clean_first_run"]["status"] == "FAIL"
    assert status["clean_first_run"]["reasons"]
    assert status["scientific_acceptance"] == "NOT_EVALUATED"


def test_dirty_cli_is_unsuccessful(tmp_path, line):
    source = tmp_path / "input.raw.csi"
    source.write_bytes(line + changed(line, seq=742))
    assert capture.main(["--input", str(source), "--out", str(tmp_path / "session")]) == 2


def test_stop_during_finalization_cannot_be_success(tmp_path, monkeypatch, line):
    import threading
    stop = threading.Event()
    original = capture.write_capture
    def cancel_after_write(*args):
        result = original(*args)
        stop.set()
        return result
    monkeypatch.setattr(capture, "write_capture", cancel_after_write)
    status = capture.record_session(Reader(line), tmp_path / "session", transport="file", stop=stop)
    assert status["state"] == "CANCELLED"
