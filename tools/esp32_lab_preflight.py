#!/usr/bin/env python3
"""The hardware preflight: one timed capture, scored pass or fail.

This is the 60-second test that decides whether the new firmware is
behaving on the real board. It reads **both** USB paths at once, because
they answer different questions:

* the native USB-Serial/JTAG port carries the CSI stream - the thing the
  science uses;
* the CH343 bridge carries the same stream **and** the ESP-IDF log at
  921600 baud - the thing that says *why* if the first goes quiet.

It scores five things, with the thresholds written down:

    activity        the CSI callback is firing, and at a plausible rate
    continuity      packets keep arriving; nothing is silently missing
    rf              RSSI, noise floor, channel and the subcarrier map are sane
    usb             no stall, no torn line, no device-side queue loss
    telemetry       the supervisor protocol - NOT IN THIS BUILD (deferred)

    python3 tools/esp32_lab_preflight.py --seconds 60
    python3 tools/esp32_lab_preflight.py --seconds 60 --ping 192.168.4.1
    python3 tools/esp32_lab_preflight.py --replay runs/lab/preflight.json

The score is deliberately conservative: a metric that cannot be measured
is reported as UNKNOWN, not as a pass.
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from specter.sensors.esp32.dispatcher import CsiParser
from specter.sensors.esp32.firmware_status import parse_status_line

CSI_PORT = "/dev/cu.usbmodem1101"
CONSOLE_PORT = "/dev/cu.usbmodem5B901602281"
CONSOLE_BAUD = 921600

#: Scoring rules changed after the first hardware run; scores are comparable
#: only within a version. v1 required the set of non-zero subcarriers to equal
#: the 52 used slots exactly, which fails on any active subcarrier whose int8
#: I and Q both truncate to zero. v2 asserts the structural property instead:
#: every required null slot is zero, and all 52 active slots carry energy at
#: least once across the capture.
SCORING_VERSION = 2

#: The null-carrier set of an 802.11n 20 MHz LLTF, measured on this board
#: and confirmed against the ESP-IDF subcarrier table: 64 slots, 52 used.
NULL_CARRIERS = frozenset({0} | set(range(27, 38)))
USED_CARRIERS = 64 - len(NULL_CARRIERS)
ACTIVE_CARRIERS = frozenset(range(64)) - NULL_CARRIERS
LLTF_SLOTS = 64

#: The thresholds. Every one of them is a decision, not a default, and each
#: carries the reason it is where it is.
THRESHOLDS = {
    "min_csi_rate_hz": 5.0,        # below this the link is not really up
    "min_continuity": 0.95,        # 95% of the expected packets, when known
    "max_gap_s": 1.0,              # a 1 s hole is already suspicious
    "max_malformed": 0,            # a parser reject means a format change
    "rssi_min_dbm": -85.0,         # below this the geometry is wrong
    "rssi_max_dbm": -15.0,         # above this the radio is saturating
    "max_noise_floor_dbm": -80.0,  # a noisy channel invalidates the features
    "min_used_subcarrier_rate": 0.99,   # active slots seen across the capture
    "min_null_zero_rate": 1.0,     # a null that carries energy is structural
    "min_frames_for_map": 20,      # below this the map cannot be verified
    "max_queue_drops": 0,          # the queue must be keeping up
}


@dataclass
class Observation:
    """Everything one capture measured, with no interpretation yet."""
    seconds: float = 0.0
    csi_count: int = 0
    malformed: int = 0
    status_lines: int = 0
    first_status: Optional[Dict] = None
    last_status: Optional[Dict] = None
    rssi: List[float] = field(default_factory=list)
    noise_floor: List[float] = field(default_factory=list)
    channels: List[int] = field(default_factory=list)
    rate_histogram: Dict[str, int] = field(default_factory=dict)
    # v2: structural null check plus aggregate active-slot coverage
    null_ok: int = 0
    null_checked: int = 0
    active_seen: List[int] = field(default_factory=list)
    # legacy v1 counters, kept only so that v1 observations still replay
    used_carrier_ok: int = 0
    used_carrier_checked: int = 0
    max_gap_s: float = 0.0
    seq_gaps: int = 0
    usb_bytes: int = 0
    console_bytes: int = 0
    expected_rate_hz: Optional[float] = None
    console_text: str = ""


@dataclass
class Result:
    name: str
    value: str
    criterion: str
    status: str   # PASS / FAIL / UNKNOWN / DEFERRED


def _analyse_subcarriers(iq: List[int]):
    """Return ``(nulls_ok, active_slots, slots)`` for one CSI record.

    A **required null** carries no energy. If one does, the record is not a
    20 MHz LLTF capture and everything derived from it is unsafe.

    An **active** slot may read zero without anything being wrong: I and Q are
    int8, so a faint subcarrier truncates to exactly ``(0, 0)``. v1 treated
    that as a broken map, which is why a healthy link scored 79.7%. v2 never
    fails an individual record for a zero active slot; it verifies coverage
    across the capture instead.
    """
    slots = len(iq) // 2
    zero = frozenset(i for i in range(slots)
                     if iq[2 * i] == 0 and iq[2 * i + 1] == 0)
    nulls_ok = slots == LLTF_SLOTS and NULL_CARRIERS <= zero
    active = (frozenset(range(slots)) - NULL_CARRIERS) - zero
    return nulls_ok, active, slots


def evaluate(obs: Observation) -> List[Result]:
    """Score one capture. Pure, so it can be tested without a board."""
    results: List[Result] = []
    th = THRESHOLDS

    # --- activity ---------------------------------------------------------
    csi_rate = obs.csi_count / obs.seconds if obs.seconds > 0 else 0.0
    cb_rate = None
    delta = 0
    if obs.first_status and obs.last_status:
        delta = (obs.last_status.get("csi_callbacks", 0)
                 - obs.first_status.get("csi_callbacks", 0))
        cb_rate = delta / obs.seconds if obs.seconds > 0 else 0.0

    if cb_rate is None:
        results.append(Result("csi callback activity", "no status line",
                              f">= {th['min_csi_rate_hz']:.0f}/s", "UNKNOWN"))
    else:
        ok = cb_rate >= th["min_csi_rate_hz"]
        results.append(Result("csi callback activity", f"{cb_rate:.1f}/s",
                              f">= {th['min_csi_rate_hz']:.0f}/s",
                              "PASS" if ok else "FAIL"))
        # the SoftAP capability probe, stated as its own line
        results.append(Result(
            "csi callback fires at all", "yes" if delta > 0 else "never",
            "> 0 (SoftAP probe)", "PASS" if delta > 0 else "FAIL"))

    # --- continuity -------------------------------------------------------
    if obs.expected_rate_hz:
        continuity = csi_rate / obs.expected_rate_hz
        results.append(Result(
            "packet continuity",
            f"{continuity * 100:.1f}% of {obs.expected_rate_hz:.0f}/s",
            f">= {th['min_continuity'] * 100:.0f}%",
            "PASS" if continuity >= th["min_continuity"] else "FAIL"))
    else:
        results.append(Result("packet continuity", f"{csi_rate:.1f}/s",
                              "no expected rate given", "UNKNOWN"))

    results.append(Result("longest inter-packet gap", f"{obs.max_gap_s:.3f}s",
                          f"<= {th['max_gap_s']:.1f}s",
                          "PASS" if obs.max_gap_s <= th["max_gap_s"] else "FAIL"))
    results.append(Result("malformed lines", str(obs.malformed),
                          f"<= {th['max_malformed']}",
                          "PASS" if obs.malformed <= th["max_malformed"] else "FAIL"))
    results.append(Result("sequence gaps", str(obs.seq_gaps), "0",
                          "PASS" if obs.seq_gaps == 0 else "FAIL"))

    # --- rf ---------------------------------------------------------------
    if obs.rssi:
        lo, hi = min(obs.rssi), max(obs.rssi)
        ok = th["rssi_min_dbm"] <= lo and hi <= th["rssi_max_dbm"]
        results.append(Result("rssi", f"{statistics.mean(obs.rssi):.0f} dBm "
                                      f"({lo:.0f}..{hi:.0f})",
                              f"{th['rssi_min_dbm']:.0f}..{th['rssi_max_dbm']:.0f}",
                              "PASS" if ok else "FAIL"))
    else:
        results.append(Result("rssi", "no packets", "in range", "UNKNOWN"))

    if obs.noise_floor:
        nf = statistics.mean(obs.noise_floor)
        results.append(Result("noise floor", f"{nf:.0f} dBm",
                              f"<= {th['max_noise_floor_dbm']:.0f}",
                              "PASS" if nf <= th["max_noise_floor_dbm"] else "FAIL"))

    if obs.channels:
        chans = sorted(set(obs.channels))
        results.append(Result("channel", ",".join(str(c) for c in chans),
                              "one value (no silent roam)",
                              "PASS" if len(chans) == 1 else "FAIL"))

    if obs.null_checked:
        frac = obs.null_ok / obs.null_checked
        results.append(Result(
            "subcarrier nulls", f"{obs.null_ok}/{obs.null_checked} frames clean",
            "every required null is zero",
            "PASS" if frac >= th["min_null_zero_rate"] else "FAIL"))
        seen = len(ACTIVE_CARRIERS & set(obs.active_seen))
        if obs.null_checked < th["min_frames_for_map"]:
            results.append(Result(
                "active subcarrier coverage", f"{seen}/{USED_CARRIERS} slots",
                f">= {th['min_frames_for_map']:.0f} frames to verify", "UNKNOWN"))
        else:
            cover = seen / USED_CARRIERS
            results.append(Result(
                "active subcarrier coverage",
                f"{seen}/{USED_CARRIERS} slots seen",
                f">= {th['min_used_subcarrier_rate'] * 100:.0f}%",
                "PASS" if cover >= th["min_used_subcarrier_rate"] else "FAIL"))
    elif obs.used_carrier_checked:
        # A v1 capture recorded only the exact-set verdict, which cannot answer
        # the v2 question. Re-scoring it would be a guess, so say so.
        results.append(Result("subcarrier nulls", "v1 capture",
                              "re-capture for v2", "UNKNOWN"))
        results.append(Result("active subcarrier coverage", "v1 capture",
                              "re-capture for v2", "UNKNOWN"))
    else:
        results.append(Result("subcarrier nulls", "no packets",
                              "every required null is zero", "UNKNOWN"))
        results.append(Result("active subcarrier coverage", "no packets",
                              f"{USED_CARRIERS} slots seen", "UNKNOWN"))

    if obs.rate_histogram:
        top = max(obs.rate_histogram.items(), key=lambda kv: kv[1])
        total = sum(obs.rate_histogram.values())
        results.append(Result(
            "phy rate", f"dominant {top[0]} ({100 * top[1] / total:.0f}%)",
            "recorded (a confound, not a failure)",
            "PASS" if len(obs.rate_histogram) <= 2 else "UNKNOWN"))

    # --- usb --------------------------------------------------------------
    results.append(Result("device queue drops",
                          f"{_drops(obs)}",
                          f"<= {th['max_queue_drops']}",
                          "PASS" if _drops(obs) <= th["max_queue_drops"]
                          else "FAIL"))
    if obs.console_bytes > 0:
        drift = abs(obs.usb_bytes - obs.console_bytes) / obs.console_bytes
        results.append(Result("usb vs console byte drift", f"{drift * 100:.2f}%",
                              "<= 0.5% (the same stream on both paths)",
                              "PASS" if drift <= 0.005 else "FAIL"))
    else:
        results.append(Result("usb vs console byte drift", "console silent",
                              "<= 0.5%", "FAIL"))

    # --- telemetry --------------------------------------------------------
    results.append(Result(
        "supervisor telemetry", "not in this build",
        "HELLO/STAT/HB - deferred to the supervisor milestone", "DEFERRED"))
    return results


def _drops(obs: Observation) -> int:
    if not obs.last_status or not obs.first_status:
        return 0
    a = obs.first_status
    b = obs.last_status
    return ((b.get("dropped_old", 0) - a.get("dropped_old", 0))
            + (b.get("dropped_new", 0) - a.get("dropped_new", 0)))


def verdict(results: List[Result]) -> str:
    """READY only if nothing failed. DEFERRED does not block; UNKNOWN does."""
    if any(r.status == "FAIL" for r in results):
        return "FAIL"
    if any(r.status == "UNKNOWN" for r in results):
        return "INCONCLUSIVE"
    return "PASS"


# --- capture ---------------------------------------------------------------

def _drain(ser, seconds: float = 0.25) -> None:
    """Discard bytes that arrived before the measurement window.

    Opening the port mid-stream means the first thing we see is the tail of a
    record, or two records spliced together where the USB path dropped bytes
    while nobody was reading. Neither belongs to this capture, and counting
    them would blame the link for our own late arrival.
    """
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        ser.read(65536)
        time.sleep(0.01)


def capture(seconds: float, csi_port: str, console_port: str,
            console_baud: int, ping: Optional[str],
            expect_rate: Optional[float],
            raw_out: Optional[str] = None) -> Observation:
    import serial

    obs = Observation(seconds=seconds, expected_rate_hz=expect_rate)
    parser = CsiParser()
    stop = threading.Event()
    lock = threading.Lock()
    times: List[float] = []
    seqs: List[int] = []
    console_lines: List[str] = []
    seen_active = set()

    def read_csi():
        try:
            ser = serial.Serial(csi_port, 115200, timeout=0.2)
        except Exception as exc:
            obs.console_text += f"\n[cannot open {csi_port}: {exc}]"
            return
        buf = b""
        _drain(ser)
        with ser:
            while not stop.is_set():
                chunk = ser.read(65536)
                if not chunk:
                    continue
                with lock:
                    obs.usb_bytes += len(chunk)
                buf += chunk
                while b"\n" in buf:
                    raw, _, buf = buf.partition(b"\n")
                    line = raw.decode("utf-8", "replace").strip()
                    if not line:
                        continue
                    if line.startswith("CSI_DATA"):
                        try:
                            rec = parser.feed(line)
                        except ValueError:
                            # a spliced or truncated line is a transport fault,
                            # not a reason to abandon the capture
                            rec = None
                        if rec is None:
                            with lock:
                                obs.malformed += 1
                            continue
                        now = time.monotonic()
                        nulls_ok, active, _slots = _analyse_subcarriers(rec.iq)
                        with lock:
                            obs.csi_count += 1
                            obs.rssi.append(rec.rssi)
                            obs.noise_floor.append(rec.noise_floor)
                            obs.channels.append(rec.channel)
                            obs.rate_histogram[str(rec.rate)] = \
                                obs.rate_histogram.get(str(rec.rate), 0) + 1
                            obs.null_checked += 1
                            if nulls_ok:
                                obs.null_ok += 1
                            seen_active.update(active)
                            seqs.append(rec.seq)
                            if times:
                                gap = now - times[-1]
                                if gap > obs.max_gap_s:
                                    obs.max_gap_s = gap
                            times.append(now)

    def read_console():
        try:
            ser = serial.Serial(console_port, console_baud, timeout=0.2)
        except Exception as exc:
            obs.console_text += f"\n[cannot open {console_port}: {exc}]"
            return
        raw_f = open(raw_out, "wb") if raw_out else None
        buf = b""
        _drain(ser)
        with ser:
            try:
                while not stop.is_set():
                    chunk = ser.read(65536)
                    if not chunk:
                        continue
                    if raw_f:
                        raw_f.write(chunk)
                    with lock:
                        obs.console_bytes += len(chunk)
                    buf += chunk
                    while b"\n" in buf:
                        raw, _, buf = buf.partition(b"\n")
                        line = raw.decode("utf-8", "replace").strip()
                        if line:
                            console_lines.append(line)
                            st = parse_status_line(line)
                            if st is not None:
                                with lock:
                                    obs.status_lines += 1
                                    if obs.first_status is None:
                                        obs.first_status = st
                                    obs.last_status = st
            finally:
                if raw_f:
                    raw_f.close()

    threads = [threading.Thread(target=read_csi, daemon=True),
               threading.Thread(target=read_console, daemon=True)]
    for t in threads:
        t.start()

    ping_proc = None
    if ping:
        ping_proc = subprocess.Popen(
            ["ping", "-i", "0.05", ping],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(seconds)
    stop.set()
    if ping_proc:
        ping_proc.terminate()
    for t in threads:
        t.join(timeout=2.0)

    # sequence gaps: the firmware's own counter, per accepted record
    if len(seqs) > 1:
        obs.seq_gaps = sum(1 for a, b in zip(seqs, seqs[1:]) if b != a + 1)
    obs.active_seen = sorted(seen_active)
    obs.console_text = "\n".join(console_lines[-40:])
    return obs


def report(results: List[Result], obs: Observation) -> int:
    print(f"  capture: {obs.seconds:.0f}s, {obs.csi_count} CSI packets, "
          f"{obs.status_lines} status lines")
    print()
    print(f"  {'check':<28} {'measured':<32} {'criterion':<38} result")
    print(f"  {'-' * 28} {'-' * 32} {'-' * 38} {'-' * 8}")
    for r in results:
        print(f"  {r.name:<28} {r.value:<32} {r.criterion:<38} {r.status}")
    v = verdict(results)
    print()
    print(f"  PREFLIGHT (scoring v{SCORING_VERSION}): {v}")
    return 0 if v == "PASS" else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seconds", type=float, default=60.0)
    ap.add_argument("--csi-port", default=CSI_PORT)
    ap.add_argument("--console-port", default=CONSOLE_PORT)
    ap.add_argument("--console-baud", type=int, default=CONSOLE_BAUD)
    ap.add_argument("--ping", default=None,
                    help="host to ping during the capture (the stimulus)")
    ap.add_argument("--expect-rate", type=float, default=None,
                    help="expected packet rate, e.g. the ping rate in Hz")
    ap.add_argument("--out", default=None, help="write the observation as JSON")
    ap.add_argument("--raw-out", default=None,
                    help="also preserve the console/CSI bytes verbatim, so the "
                         "run can be re-scored without re-running it")
    ap.add_argument("--replay", default=None,
                    help="re-score a saved observation instead of capturing")
    args = ap.parse_args(argv)

    if args.replay:
        with open(args.replay, encoding="utf-8") as fh:
            saved = json.load(fh)
        saved.pop("scoring_version", None)  # metadata, not an Observation field
        obs = Observation(**saved)
    else:
        obs = capture(args.seconds, args.csi_port, args.console_port,
                      args.console_baud, args.ping, args.expect_rate,
                      args.raw_out)
        if args.out:
            os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
            payload = dict(obs.__dict__)
            payload["scoring_version"] = SCORING_VERSION
            with open(args.out, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=2)

    results = evaluate(obs)
    rc = report(results, obs)
    if obs.console_text:
        print()
        print("  last console lines:")
        for line in obs.console_text.splitlines()[-10:]:
            print("   ", line)
    return rc


if __name__ == "__main__":
    sys.exit(main())
