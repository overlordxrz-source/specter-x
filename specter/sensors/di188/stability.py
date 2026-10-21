"""Long-run stability harness for the DI-188 link.

The DI-188 ASCII protocol carries no frame sequence number, so dropped frames
cannot be counted directly. Five independent views are reported, because they
fail in different ways and conflating them produces nonsense:

``frames_shortfall`` (genuine loss)
    ``expected = elapsed * realised_rate`` minus ``received``. The instrument
    reports its rate from a nominal timer constant, so this number is
    authoritative only up to that offset - see ``rate offset`` below.

``rate offset`` (systematic, NOT loss)
    The hardware timer is quantised, so the instrument runs slightly slower
    than the ``srate`` command claims (about -0.8 % at 500 Hz on this unit).
    A shortfall that is *stable* over the whole window is that offset, not
    lost frames. The per-window rate spread tells the two apart: random frame
    loss makes the window-to-window rate wobble, a fixed offset does not.

``arrival batching`` (host-side, NOT loss)
    macOS delivers CDC-ACM data in bursts, so the host typically sees a quiet
    moment of up to ~1 s, then a batch of frames arrives. The frame *count* is
    unaffected. Gaps above 10x the median arrival interval are counted as
    ``burst_gaps`` and reported separately - they are not stalls.

``stalls`` (a genuine pause in the link)
    A gap longer than ``stall_gap_s`` (default 5 s) during which the link
    produced nothing. The frames that would have arrived during that pause are
    counted separately.

``malformed / serial errors``
    Frames the instrument emitted that could not be parsed, and link failures.
"""
from __future__ import annotations

import json
import os
import statistics
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .driver import DI188Driver, DI188Error


@dataclass
class StabilityReport:
    duration_s: float = 0.0
    requested_rate: float = 0.0
    realised_rate: float = 0.0
    frames_received: int = 0
    frames_expected: int = 0
    frames_shortfall: int = 0
    frames_lost_to_stalls: int = 0
    stall_events: int = 0
    stall_gap_s: float = 5.0
    worst_stall_s: float = 0.0
    burst_gaps: int = 0
    worst_burst_gap_s: float = 0.0
    jitter_events: int = 0
    arrival_median_s: float = 0.0
    arrival_p95_s: float = 0.0
    arrival_max_s: float = 0.0
    malformed_lines: int = 0
    serial_errors: int = 0
    disconnects: int = 0
    achieved_rate_hz: float = 0.0
    rate_offset_pct: float = 0.0
    window_rate_std_pct: float = 0.0
    window_rates: List[float] = field(default_factory=list)
    verdict: str = ""
    error_messages: List[str] = field(default_factory=list)
    started_utc: str = ""
    finished_utc: str = ""

    @property
    def ok(self) -> bool:
        """A clean run: no frame loss, no stall, no malformed frame, no error."""
        return (self.frames_shortfall == 0
                and self.stall_events == 0
                and self.serial_errors == 0
                and self.malformed_lines == 0)

    @property
    def loss_fraction(self) -> float:
        if self.frames_expected <= 0:
            return 0.0
        return self.frames_shortfall / self.frames_expected

    def as_dict(self) -> Dict:
        return {
            "started_utc": self.started_utc,
            "finished_utc": self.finished_utc,
            "duration_s": round(self.duration_s, 3),
            "requested_rate_hz": self.requested_rate,
            "realised_rate_hz": self.realised_rate,
            "achieved_rate_hz": round(self.achieved_rate_hz, 4),
            "rate_offset_pct": round(self.rate_offset_pct, 4),
            "window_rate_std_pct": round(self.window_rate_std_pct, 4),
            "verdict": self.verdict,
            "frames_received": self.frames_received,
            "frames_expected": self.frames_expected,
            "frames_shortfall": self.frames_shortfall,
            "loss_fraction": round(self.loss_fraction, 8),
            "frames_lost_to_stalls": self.frames_lost_to_stalls,
            "stall_events": self.stall_events,
            "stall_gap_s": self.stall_gap_s,
            "worst_stall_s": round(self.worst_stall_s, 4),
            "burst_gaps": self.burst_gaps,
            "worst_burst_gap_s": round(self.worst_burst_gap_s, 4),
            "jitter_events_over_2x_median": self.jitter_events,
            "arrival_interval_median_s": round(self.arrival_median_s, 6),
            "arrival_interval_p95_s": round(self.arrival_p95_s, 6),
            "arrival_interval_max_s": round(self.arrival_max_s, 6),
            "malformed_lines": self.malformed_lines,
            "serial_errors": self.serial_errors,
            "disconnects": self.disconnects,
            "errors": self.error_messages[:50],
            "ok": self.ok,
        }

    def summary(self) -> str:
        return "\n".join([
            "DI-188 stability report",
            f"  window              : {self.duration_s:.1f} s",
            f"  rate req/realised  : {self.requested_rate:g} / {self.realised_rate:g} Hz",
            f"  achieved rate       : {self.achieved_rate_hz:.4f} Hz "
            f"({self.rate_offset_pct:+.3f}% vs requested)",
            f"  window rate spread  : {self.window_rate_std_pct:.3f}% "
            f"(low = systematic offset, high = random loss)",
            f"  frames received     : {self.frames_received}",
            f"  frames expected     : {self.frames_expected}",
            f"  FRAME LOSS          : {self.frames_shortfall} "
            f"({self.loss_fraction * 100:.4f}%)",
            f"  stalls (>{self.stall_gap_s:g}s)    : {self.stall_events} "
            f"(worst {self.worst_stall_s:.3f} s, {self.frames_lost_to_stalls} frames)",
            f"  arrival bursts      : {self.burst_gaps} gaps >10x median "
            f"(worst {self.worst_burst_gap_s:.3f} s) - host-side batching, no loss",
            f"  arrival jitter      : median {self.arrival_median_s * 1e3:.3f} ms, "
            f"p95 {self.arrival_p95_s * 1e3:.3f} ms, max {self.arrival_max_s * 1e3:.3f} ms",
            f"  malformed lines     : {self.malformed_lines}",
            f"  serial errors       : {self.serial_errors}",
            f"  disconnects         : {self.disconnects}",
            f"  VERDICT             : {self.verdict}",
            f"  pass/fail           : {'PASS' if self.ok else 'ISSUES FOUND'}",
        ])


def _classify(report: "StabilityReport") -> str:
    """Distinguish 'no loss' from 'device runs slightly slow' from 'loss'."""
    if report.serial_errors or report.disconnects:
        return "LINK ERROR - the connection dropped"
    if report.frames_shortfall == 0:
        return "NO FRAME LOSS"
    if (report.window_rate_std_pct < 0.5
            and abs(report.rate_offset_pct) < 3.0
            and report.stall_events == 0):
        return ("SYSTEMATIC RATE OFFSET (device timer quantisation) - not frame loss")
    return "FRAME LOSS - frames were genuinely dropped"


def run_stability_test(driver: DI188Driver, channels: List[int], rate: float,
                       duration_s: float = 1800.0, stall_gap_s: float = 5.0,
                       stall_timeout: float = 10.0,
                       progress: Optional[callable] = None) -> StabilityReport:
    """Stream for ``duration_s`` seconds and report link stability."""
    report = StabilityReport(requested_rate=rate, stall_gap_s=stall_gap_s)
    report.started_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    realised = driver.configure(channels, rate)
    report.realised_rate = realised
    frame_period = 1.0 / realised if realised > 0 else 0.0

    t_start = time.time()
    last_frame_t = t_start
    gaps: List[float] = []
    lost_time = 0.0
    frames = 0
    next_progress = 10.0
    window_s = 10.0
    window_start = t_start
    window_frames = 0
    window_rates: List[float] = []

    driver.start()
    frame_iter = driver.stream(stall_timeout=stall_timeout)
    try:
        while True:
            now = time.time()
            elapsed = now - t_start
            if elapsed >= duration_s:
                break
            try:
                next(frame_iter)
            except StopIteration:
                break
            gap = now - last_frame_t
            last_frame_t = now
            gaps.append(gap)
            if gap > stall_gap_s:
                report.stall_events += 1
                lost_time += (gap - frame_period)
                report.worst_stall_s = max(report.worst_stall_s, gap)
            frames += 1
            report.frames_received = frames
            window_frames += 1
            if now - window_start >= window_s:
                window_rates.append(window_frames / (now - window_start))
                window_start = now
                window_frames = 0
            if progress and elapsed >= next_progress:
                next_progress += 10.0
                progress(report, elapsed)
    except DI188Error as exc:
        report.serial_errors += 1
        report.disconnects += 1
        report.error_messages.append(str(exc))
    except Exception as exc:  # pragma: no cover - defensive
        report.serial_errors += 1
        report.error_messages.append(f"{type(exc).__name__}: {exc}")
    finally:
        try:
            driver.stop()
        except Exception:
            pass

    report.malformed_lines = getattr(driver, "malformed_lines", 0)
    report.duration_s = time.time() - t_start
    report.window_rates = window_rates
    report.frames_expected = int(round(report.realised_rate * report.duration_s))
    report.frames_shortfall = max(0, report.frames_expected - report.frames_received)
    report.frames_lost_to_stalls = int(round(lost_time / frame_period)) if frame_period else 0

    if gaps:
        ordered = sorted(gaps)
        report.arrival_median_s = statistics.median(ordered)
        report.arrival_p95_s = ordered[min(len(ordered) - 1, int(0.95 * len(ordered)))]
        report.arrival_max_s = ordered[-1]
        if report.arrival_median_s > 0:
            report.jitter_events = sum(1 for g in gaps if g > 2 * report.arrival_median_s)
            burst_threshold = 10 * report.arrival_median_s
            burst = [g for g in gaps if g > burst_threshold]
            report.burst_gaps = len(burst)
            report.worst_burst_gap_s = max(burst) if burst else 0.0

    if report.duration_s > 0:
        report.achieved_rate_hz = report.frames_received / report.duration_s
    if report.realised_rate > 0:
        report.rate_offset_pct = (
            (report.achieved_rate_hz - report.realised_rate) / report.realised_rate * 100.0)
    if len(window_rates) > 1:
        mean = sum(window_rates) / len(window_rates)
        var = sum((r - mean) ** 2 for r in window_rates) / len(window_rates)
        if mean > 0:
            report.window_rate_std_pct = (var ** 0.5) / mean * 100.0

    report.verdict = _classify(report)
    report.finished_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    return report


def save_report(report: StabilityReport, path: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(report.as_dict(), fh, indent=2)
        fh.write("\n")


#: Alias with a clearer name for CLI/tool use.
save_stability_report = save_report
