"""Bounded CSI byte acquisition and completed-session handoff to WORLD.

Imports never open a device. Serial requires explicit CLI opt-in. File input
is offline rehearsal, not physical acquisition. No inference or reconnect.
"""
from __future__ import annotations

import argparse
from collections import Counter
from itertools import chain
import hashlib
import json
import math
from pathlib import Path
import signal
import threading
import time
import uuid

from specter.platform.observation import Observation
from specter.platform.replay import CsiReplay, sha256_file, write_capture, read_capture
from .serial_owner import open_serial

MAX_BYTES = 512 * 1024 * 1024
MAX_READS = 100_000
CHUNK_BYTES = 4096


def _positive(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be finite and positive")
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be finite and positive")
    return float(value)


def _publish(directory, status):
    # Only this newly-created session's derived status is replaced. Raw and
    # receipt logs are append-only; no pre-existing directory is accepted.
    temporary = directory / "status.pending"
    data = json.dumps(status, indent=2, allow_nan=False) + "\n"
    with temporary.open("w") as stream:
        _write_checked(stream, data)
    if temporary.stat().st_size != len(data.encode("utf-8")):
        raise OSError("short status write")
    temporary.replace(directory / "status.json")


def _write_checked(stream, data):
    if stream.write(data) != len(data):
        raise OSError("short recording write")


def _time(clock):
    value = clock()
    if type(value) is not int or value < 0:
        raise ValueError("monotonic clock must return nonnegative integer nanoseconds")
    return value


class _Cancelled(Exception):
    pass


def _check_stop(stop):
    if stop is not None and stop.is_set():
        raise _Cancelled("cancellation requested")


def _audit_recording(directory, status):
    """Reconcile closed files, not just the writer's claimed return values."""
    raw = directory / "session.raw.csi"
    receipts = directory / "receipts.jsonl"
    size = raw.stat().st_size
    status["raw_file_bytes"] = size
    status["raw_sha256"] = sha256_file(raw)
    status["unaccounted_bytes"] = status["read_bytes"] - size - status["rejected_bytes"]
    if status["unaccounted_bytes"] != 0 or size != status["bytes"]:
        raise OSError("raw byte accounting mismatch")
    if status["raw_sha256"] != status["accepted_read_sha256"]:
        raise OSError("raw persisted/read hash mismatch")
    if receipts.stat().st_size != status["receipt_bytes"]:
        raise OSError("receipt byte accounting mismatch")
    end, completed, count = 0, status["started_monotonic_ns"], 0
    with receipts.open() as stream:
        for line in stream:
            if not line.endswith("\n") or len(line) > 1024:
                raise OSError("incomplete or oversized receipt")
            item = json.loads(line)
            next_end, next_completed = item["byte_end"], item["read_completed_ns"]
            if (type(next_end) is not int or not 0 < next_end - end <= CHUNK_BYTES
                    or type(next_completed) is not int or next_completed < completed):
                raise OSError("receipt monotonic accounting mismatch")
            expected = "offline_feed" if status["transport"] == "file" else "host_read_completion"
            if item["meaning"] != expected:
                raise OSError("receipt transport mismatch")
            end, completed, count = next_end, next_completed, count + 1
    if end != size or count != status["reads"]:
        raise OSError("receipt count/end accounting mismatch")
    status["receipts_sha256"] = sha256_file(receipts)
    if status["receipts_sha256"] != status["receipt_write_sha256"]:
        raise OSError("receipt persisted/write hash mismatch")


def _clean_gate(counters):
    keys = ("sequence_missing", "malformed", "spliced_lines", "recovered_records",
            "unsupported_layout", "nonmonotonic_sequence", "clock_discontinuity")
    reasons = [f"{key}={counters[key]}" for key in keys if counters.get(key, 0)]
    return dict(status="FAIL" if reasons else "PASS", reasons=reasons)


def _limits(max_bytes, max_reads):
    if type(max_bytes) is not int or not 1 <= max_bytes <= MAX_BYTES:
        raise ValueError("max_bytes outside 1..512 MiB")
    if type(max_reads) is not int or not 1 <= max_reads <= MAX_READS:
        raise ValueError("max_reads outside 1..100000")


def _fail(status, message):
    status["errors"].append(message)
    status.update(state="FAILED", error="; ".join(status["errors"]))


def _observations(directory, source, transport, session_id, quality, stop):
    """Map raw line ends to read-completion upper bounds, streaming both logs."""
    with (directory / "session.raw.csi").open("rb") as raw, (
        directory / "receipts.jsonl"
    ).open() as receipts:
        line_number = end = 0
        receipt = None
        for observation in source:
            _check_stop(stop)
            data = observation.to_dict()
            if "clock_discontinuity" in data["validity"]["flags"]:
                quality["clock_discontinuity"] += 1
            sig_len = data["value"]["sig_len_bytes"]
            quality["payload_frames" if sig_len == 138 else
                    "null_frames" if sig_len == 28 else "other_frames"] += 1
            if transport == "serial":
                # A port name (or replaying known bytes over a port) does
                # not authenticate a physical sensor or a fresh acquisition.
                data["origin"] = data["classification"] = "unknown"
                data["evidence"]["level"] = "unverified"
                target = data["evidence"]["raw"]["line"]
                while line_number < target:
                    line = raw.readline(16385)
                    if not line:
                        raise ValueError("raw line reference missing")
                    end += len(line)
                    line_number += 1
                while receipt is None or receipt["byte_end"] < end:
                    receipt = json.loads(next(receipts))
                data["received"] = dict(
                    domain=f"node/{session_id}/host.monotonic",
                    time_ns=receipt["read_completed_ns"],
                )
                data["acquisition"]["epoch"] = (
                    session_id + "/" + data["acquisition"]["epoch"]
                )
                flags = data["validity"]["flags"]
                flags.remove("receive_time_unrecorded")
                flags.append("receive_time_is_chunk_completion")
                if "source_origin_unverified" not in flags:
                    flags.append("source_origin_unverified")
            # File input retains original unknown physical receive time.
            yield Observation(data)


def record_session(reader, directory, *, transport, duration_s=60.,
                   stall_s=5., max_bytes=MAX_BYTES, max_reads=MAX_READS,
                   clock=time.monotonic_ns, stop=None):
    """Own/close an already configured reader; return truthful terminal status.

    Reader.read(4096) must return within its transport timeout. An empty
    read means EOF for file input and a timeout for serial. Tests inject a
    deterministic reader/clock; the production serial timeout is 100 ms.
    Failures preserve evidence and terminal FAILED/CANCELLED status. Direct
    BaseException is re-raised after cleanup/publication; stop requests return
    CANCELLED. Late failure may retain derived artifacts: terminal status and
    acceptance gates, not file existence, determine success. If terminal
    publication is impossible, the error propagates rather than succeeding.
    """
    try:
        duration_s = _positive(duration_s, "duration_s")
        stall_s = _positive(stall_s, "stall_s")
        if transport not in {"file", "serial"}:
            raise ValueError("explicit file or serial transport required")
        _limits(max_bytes, max_reads)
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=False)
    except BaseException:
        reader.close()
        raise
    started = None
    session_id = str(uuid.uuid4())
    status = dict(
        format_version=1, session_id=session_id, transport=transport,
        mode="OFFLINE REHEARSAL" if transport == "file" else "ACQUISITION / UNVERIFIED",
        state="RECORDING", reason=None, bytes=0, reads=0,
        read_bytes=0, rejected_bytes=0, receipt_bytes=0,
        ownership=getattr(reader, "ownership", "caller_supplied_reader_unverified")
            if transport == "serial" else "read_only_file",
        started_monotonic_ns=started, stopped_monotonic_ns=None,
        live_verified=False, error=None, errors=[], observations=0,
        acquisition_complete=False, scientific_acceptance="NOT_EVALUATED",
        clean_first_run=dict(status="NOT_EVALUATED", reasons=["acquisition incomplete"]),
    )
    raw_path = directory / "session.raw.csi"
    last_data = last_publish = started
    pending = None
    source, quality = None, Counter()
    raw_hash, receipt_hash = hashlib.sha256(), hashlib.sha256()

    def abort(exc, context=""):
        nonlocal pending
        was_failed = status["state"] == "FAILED"
        _fail(status, f"{context}{type(exc).__name__}: {exc}")
        status["acquisition_complete"] = False
        status["clean_first_run"] = dict(status="NOT_EVALUATED", reasons=["acquisition incomplete"])
        if isinstance(exc, (KeyboardInterrupt, _Cancelled)) and not was_failed:
            status.update(state="CANCELLED", reason="cancelled")
        if not isinstance(exc, Exception) and pending is None:
            pending = (exc, exc.__traceback__)

    try:
        _publish(directory, status)
        started = _time(clock)
        status["started_monotonic_ns"] = started
        last_data = last_publish = started
        with raw_path.open("xb") as raw, (directory / "receipts.jsonl").open("x") as receipts:
            while True:
                _check_stop(stop)
                now = _time(clock)
                if now < last_data:
                    raise ValueError("monotonic clock moved backwards")
                if now - started >= duration_s * 1e9:
                    status["reason"] = "duration"
                    break
                if now - last_data >= stall_s * 1e9:
                    raise TimeoutError("no bytes within stall limit")
                chunk = reader.read(CHUNK_BYTES)
                completed = _time(clock)
                if completed < max(now, last_data):
                    raise ValueError("monotonic clock moved backwards")
                if not isinstance(chunk, bytes):
                    raise ValueError("reader violated bounded bytes contract")
                status["read_bytes"] += len(chunk)
                if len(chunk) > CHUNK_BYTES:
                    status["rejected_bytes"] += len(chunk)
                    raise ValueError("reader violated bounded bytes contract")
                if not chunk:
                    if transport == "file":
                        status["reason"] = "eof"
                        break
                    continue
                if status["bytes"] + len(chunk) > max_bytes:
                    status["rejected_bytes"] += len(chunk)
                    raise ValueError("capture byte limit exceeded")
                if status["reads"] >= max_reads:
                    status["rejected_bytes"] += len(chunk)
                    raise ValueError("capture read-event limit exceeded")
                _write_checked(raw, chunk)
                raw_hash.update(chunk)
                status["bytes"] += len(chunk)
                status["reads"] += 1
                receipt = json.dumps(dict(
                    byte_end=status["bytes"], read_completed_ns=completed,
                    meaning="offline_feed" if transport == "file" else "host_read_completion",
                )) + "\n"
                _write_checked(receipts, receipt)
                receipt_hash.update(receipt.encode("utf-8"))
                status["receipt_bytes"] += len(receipt.encode("utf-8"))
                last_data = completed
                if completed - last_publish >= 1_000_000_000:
                    raw.flush()
                    receipts.flush()
                    _publish(directory, status)
                    last_publish = completed
    except BaseException as exc:
        abort(exc)
    finally:
        try:
            reader.close()
        except BaseException as exc:
            abort(exc, "transport close failed: ")
        try:
            stopped = _time(clock)
            if last_data is not None and stopped < last_data:
                raise ValueError("monotonic stop clock moved backwards")
            status["stopped_monotonic_ns"] = stopped
        except BaseException as exc:
            abort(exc)
        status["accepted_read_sha256"] = raw_hash.hexdigest()
        status["receipt_write_sha256"] = receipt_hash.hexdigest()

    try:
        # Audit even failed/interrupted captures; they retain their terminal
        # state unless an additional integrity fault requires FAILED.
        if raw_path.exists() and (directory / "receipts.jsonl").exists():
            _audit_recording(directory, status)
        elif status["state"] == "RECORDING":
            raise OSError("recording files missing")
        if status["state"] == "RECORDING":
            _check_stop(stop)
            status["state"] = "FINALIZING"
            _publish(directory, status)
            source = CsiReplay(raw_path)
            observations = _observations(directory, source, transport, session_id, quality, stop)
            try:
                first = next(observations)
            except StopIteration as exc:
                raise ValueError("no usable CSI observations") from exc
            status["observations"] = write_capture(
                directory / "session.observations.jsonl", chain([first], observations))
            verified_count = 0
            for _ in read_capture(directory / "session.observations.jsonl"):
                _check_stop(stop)
                verified_count += 1
            if verified_count != status["observations"]:
                raise OSError("derived observation count mismatch")
            _check_stop(stop)
            # Recheck persisted raw/receipts before granting completion.
            _audit_recording(directory, status)
            if source.digest != status["raw_sha256"]:
                raise OSError("raw source changed during finalization")
            status["state"] = "COMPLETE"
    except BaseException as exc:
        abort(exc)
    finally:
        try:
            if source is not None:
                status["counters"] = {**dict(source.counts), **dict(quality)}
            _check_stop(stop)
            status["acquisition_complete"] = status["state"] == "COMPLETE"
            if status["acquisition_complete"]:
                status["clean_first_run"] = _clean_gate(status["counters"])
        except BaseException as exc:
            abort(exc)
        try:
            _publish(directory, status)
        except BaseException as exc:
            abort(exc)
            try:
                _publish(directory, status)
            except BaseException as publication_error:
                if pending is not None and hasattr(pending[0], "add_note"):
                    pending[0].add_note(f"terminal status publication failed: {publication_error}")
            if pending is None:
                raise
    if pending is not None:
        raise pending[0].with_traceback(pending[1])
    return status


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--input", type=Path, help="offline file rehearsal")
    source.add_argument("--port", help="explicit serial device; never auto-detected")
    parser.add_argument("--allow-hardware", action="store_true")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--out", type=Path, required=True, help="new session directory")
    parser.add_argument("--duration", type=float, default=60.)
    parser.add_argument("--stall", type=float, default=5.)
    parser.add_argument("--max-bytes", type=int, default=MAX_BYTES)
    parser.add_argument("--max-reads", type=int, default=MAX_READS)
    args = parser.parse_args(argv)
    for value, name in ((args.duration, "duration"), (args.stall, "stall")):
        try:
            _positive(value, name)
        except ValueError as exc:
            parser.error(str(exc))
    if args.out.exists():
        parser.error("output directory already exists")
    if args.baud < 1:
        parser.error("positive baud required")
    try:
        _limits(args.max_bytes, args.max_reads)
    except ValueError as exc:
        parser.error(str(exc))
    if args.port:
        if not args.allow_hardware:
            parser.error("serial requires explicit --allow-hardware and owner authorization")
        reader = open_serial(args.port, args.baud)
    else:
        reader = args.input.open("rb")
    stop = threading.Event()
    old_handlers = {}
    for sig in (signal.SIGINT, signal.SIGTERM):
        old_handlers[sig] = signal.signal(sig, lambda *_: stop.set())
    try:
        status = record_session(reader, args.out,
            transport="serial" if args.port else "file",
            duration_s=args.duration, stall_s=args.stall,
            max_bytes=args.max_bytes, max_reads=args.max_reads, stop=stop)
    finally:
        for sig, handler in old_handlers.items():
            signal.signal(sig, handler)
    print(json.dumps(status, indent=2))
    return 0 if (status["state"] == "COMPLETE"
        and status["clean_first_run"]["status"] == "PASS") else 2


if __name__ == "__main__":
    raise SystemExit(main())
