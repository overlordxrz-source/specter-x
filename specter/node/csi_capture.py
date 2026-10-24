"""Bounded CSI byte acquisition and completed-session handoff to WORLD.

Imports never open a device. Serial requires explicit CLI opt-in. File input
is offline rehearsal, not physical acquisition. No inference or reconnect.
"""
from __future__ import annotations

import argparse
from itertools import chain
import json
import math
from pathlib import Path
import signal
import threading
import time
import uuid

from specter.platform.observation import Observation
from specter.platform.replay import CsiReplay, sha256_file, write_capture

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
    temporary.write_text(json.dumps(status, indent=2, allow_nan=False) + "\n")
    temporary.replace(directory / "status.json")


def _observations(directory, source, transport, session_id):
    """Map raw line ends to read-completion upper bounds, streaming both logs."""
    with (directory / "session.raw.csi").open("rb") as raw, (
        directory / "receipts.jsonl"
    ).open() as receipts:
        line_number = end = 0
        receipt = None
        for observation in source:
            data = observation.to_dict()
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
    Failures preserve partial raw bytes and a FAILED status. They do not
    produce a completion manifest for derived observations. A disk failure
    while publishing status remains an exception, never a success result.
    """
    try:
        duration_s = _positive(duration_s, "duration_s")
        stall_s = _positive(stall_s, "stall_s")
        if transport not in {"file", "serial"}:
            raise ValueError("explicit file or serial transport required")
        if type(max_bytes) is not int or not 1 <= max_bytes <= MAX_BYTES:
            raise ValueError("max_bytes outside 1..512 MiB")
        if type(max_reads) is not int or not 1 <= max_reads <= MAX_READS:
            raise ValueError("max_reads outside 1..100000")
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=False)
    except BaseException:
        reader.close()
        raise
    started = clock()
    session_id = str(uuid.uuid4())
    status = dict(
        format_version=1, session_id=session_id, transport=transport,
        mode="OFFLINE REHEARSAL" if transport == "file" else "ACQUISITION / UNVERIFIED",
        state="RECORDING", reason=None, bytes=0, reads=0,
        read_bytes=0, rejected_bytes=0,
        started_monotonic_ns=started, stopped_monotonic_ns=None,
        live_verified=False, error=None, observations=0,
    )
    raw_path = directory / "session.raw.csi"
    last_data = last_publish = started
    try:
        _publish(directory, status)
        with raw_path.open("xb") as raw, (
            directory / "receipts.jsonl"
        ).open("x") as receipts:
            while True:
                now = clock()
                if stop is not None and stop.is_set():
                    status["reason"] = "cancelled"
                    break
                if now - started >= duration_s * 1e9:
                    status["reason"] = "duration"
                    break
                if now - last_data >= stall_s * 1e9:
                    raise TimeoutError("no bytes within stall limit")
                chunk = reader.read(CHUNK_BYTES)
                completed = clock()
                if completed < now:
                    raise ValueError("monotonic clock moved backwards")
                if not isinstance(chunk, bytes) or len(chunk) > CHUNK_BYTES:
                    raise ValueError("reader violated bounded bytes contract")
                if not chunk:
                    if transport == "file":
                        status["reason"] = "eof"
                        break
                    continue
                status["read_bytes"] += len(chunk)
                if status["bytes"] + len(chunk) > max_bytes:
                    status["rejected_bytes"] += len(chunk)
                    raise ValueError("capture byte limit exceeded")
                if status["reads"] >= max_reads:
                    status["rejected_bytes"] += len(chunk)
                    raise ValueError("capture read-event limit exceeded")
                raw.write(chunk)
                status["bytes"] += len(chunk)
                status["reads"] += 1
                receipts.write(json.dumps(dict(
                    byte_end=status["bytes"], read_completed_ns=completed,
                    meaning="offline_feed" if transport == "file" else "host_read_completion",
                )) + "\n")
                last_data = completed
                if completed - last_publish >= 1_000_000_000:
                    raw.flush()
                    receipts.flush()
                    _publish(directory, status)
                    last_publish = completed
    except Exception as exc:
        status.update(state="FAILED", error=f"{type(exc).__name__}: {exc}")
    finally:
        try:
            reader.close()
        except Exception as exc:
            status.update(state="FAILED", error=f"transport close failed: {exc}")
        status["stopped_monotonic_ns"] = clock()
    try:
        if status["state"] == "FAILED":
            pass
        elif status["reason"] == "cancelled":
            status["state"] = "CANCELLED"
        else:
            status["state"] = "FINALIZING"
            _publish(directory, status)
            source = CsiReplay(raw_path)
            status["raw_sha256"] = source.digest
            observations = _observations(directory, source, transport, session_id)
            try:
                first = next(observations)
            except StopIteration as exc:
                raise ValueError("no usable CSI observations") from exc
            status["observations"] = write_capture(
                directory / "session.observations.jsonl",
                chain([first], observations),
            )
            status["counters"] = dict(source.counts)
            status["receipts_sha256"] = sha256_file(directory / "receipts.jsonl")
            status["state"] = "COMPLETE"
    except Exception as exc:
        status.update(state="FAILED", error=f"{type(exc).__name__}: {exc}")
    finally:
        if raw_path.exists():
            status["raw_sha256"] = sha256_file(raw_path)
        _publish(directory, status)
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
    if args.port:
        if not args.allow_hardware:
            parser.error("serial requires explicit --allow-hardware and owner authorization")
        import serial  # optional pyserial, never imported on offline path
        reader = serial.Serial(args.port, args.baud, timeout=.1, exclusive=True)
    else:
        reader = args.input.open("rb")
    stop = threading.Event()
    old_handlers = {}
    for sig in (signal.SIGINT, signal.SIGTERM):
        old_handlers[sig] = signal.signal(sig, lambda *_: stop.set())
    try:
        status = record_session(reader, args.out,
            transport="serial" if args.port else "file",
            duration_s=args.duration, stall_s=args.stall, stop=stop)
    finally:
        for sig, handler in old_handlers.items():
            signal.signal(sig, handler)
    print(json.dumps(status, indent=2))
    return 0 if status["state"] == "COMPLETE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
