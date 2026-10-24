#!/usr/bin/env python3
"""Offline analysis for SPECTER-SYNC Shrike Lite event-counter captures.

This tool never opens a serial port or device. It consumes the future RP2040
CSV containing repeated snapshots:

    host_us,event_count,fpga_ticks

Repeated event counts are normal (the host polls faster than events) and are
deduplicated. Counter deltas are computed modulo the declared width. Nominal
tick frequency is an input, not a claim about the FPGA oscillator; absolute
accuracy requires a reference measurement.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from pathlib import Path
from typing import Iterable, Mapping, Optional


def _integer(value, name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be an integer")
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be an integer") from exc
    return result


def _finite(value, name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be finite")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be finite") from exc
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def analyze(
    rows: Iterable[Mapping[str, object]],
    *,
    tick_hz: float = 50_000_000.0,
    counter_bits: int = 32,
    expected_period_s: Optional[float] = None,
) -> dict:
    """Analyze repeated event snapshots.

    The raw counter is 32-bit in the current design. ``counter_bits`` is
    configurable so the same analysis remains valid for a future verified
    counter width. No frequency calibration is inferred.
    """
    tick_hz = _finite(tick_hz, "tick_hz")
    if tick_hz <= 0.0:
        raise ValueError("tick_hz must be positive")
    if not isinstance(counter_bits, int) or isinstance(counter_bits, bool):
        raise ValueError("counter_bits must be an integer")
    if not 1 <= counter_bits <= 64:
        raise ValueError("counter_bits must be in 1..64")
    if expected_period_s is not None:
        expected_period_s = _finite(expected_period_s, "expected_period_s")
        if expected_period_s <= 0.0:
            raise ValueError("expected_period_s must be positive")
    mask = (1 << counter_bits) - 1

    unique = []
    duplicate_samples = 0
    for index, row in enumerate(rows):
        count = _integer(row.get("event_count"), "event_count")
        ticks = _integer(row.get("fpga_ticks"), "fpga_ticks")
        if count < 0 or ticks < 0 or count > mask or ticks > mask:
            raise ValueError(f"row {index}: counter value outside {counter_bits} bits")
        if unique and count == unique[-1][0]:
            duplicate_samples += 1
            continue
        if unique:
            event_delta = (count - unique[-1][0]) & mask
            if event_delta == 0 or event_delta > 0x7FFFFFFF:
                raise ValueError(f"row {index}: event_count moved backwards or reset")
        unique.append((count, ticks))

    intervals = []
    missing_events = 0
    wrap_deltas = 0
    for (prev_count, prev_ticks), (count, ticks) in zip(unique, unique[1:]):
        event_delta = (count - prev_count) & mask
        missing_events += max(0, event_delta - 1)
        tick_delta = (ticks - prev_ticks) & mask
        if ticks < prev_ticks:
            wrap_deltas += 1
        intervals.append(tick_delta)

    result = {
        "samples": duplicate_samples + len(unique),
        "unique_events": len(unique),
        "duplicate_samples_ignored": duplicate_samples,
        "missing_events": missing_events,
        "wrap_deltas": wrap_deltas,
        "intervals_ticks": intervals,
        "counter_bits": counter_bits,
        "nominal_tick_hz": tick_hz,
        "nominal_tick_ns": 1_000_000_000.0 / tick_hz,
    }
    if intervals:
        result["interval_min_ticks"] = min(intervals)
        result["interval_max_ticks"] = max(intervals)
        result["interval_mean_ticks"] = statistics.fmean(intervals)
        result["interval_stdev_ticks"] = (
            statistics.pstdev(intervals) if len(intervals) > 1 else 0.0
        )
        if expected_period_s is not None:
            expected_ticks = expected_period_s * tick_hz
            errors_ticks = [value - expected_ticks for value in intervals]
            errors_ns = [value / tick_hz * 1_000_000_000.0 for value in errors_ticks]
            result["expected_period_s"] = expected_period_s
            result["expected_ticks"] = expected_ticks
            result["error_ticks_min"] = min(errors_ticks)
            result["error_ticks_max"] = max(errors_ticks)
            result["error_ticks_mean"] = statistics.fmean(errors_ticks)
            result["error_ns_mean"] = statistics.fmean(errors_ns)
            result["error_ns_stdev"] = (
                statistics.pstdev(errors_ns) if len(errors_ns) > 1 else 0.0
            )
            result["nominal_period_estimate_s"] = (
                statistics.fmean(intervals) / tick_hz
            )
    return result


def read_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        required = {"event_count", "fpga_ticks"}
        if not required.issubset(reader.fieldnames or ()):
            raise ValueError("CSV requires event_count and fpga_ticks columns")
        return list(reader)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv", type=Path, help="RP2040 snapshot CSV")
    parser.add_argument("--tick-hz", type=float, default=50_000_000.0)
    parser.add_argument("--counter-bits", type=int, default=32)
    parser.add_argument("--expected-period-s", type=float)
    args = parser.parse_args(argv)
    result = analyze(
        read_csv(args.csv),
        tick_hz=args.tick_hz,
        counter_bits=args.counter_bits,
        expected_period_s=args.expected_period_s,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
