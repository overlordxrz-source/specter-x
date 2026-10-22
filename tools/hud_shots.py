#!/usr/bin/env python3
"""Render the HUD and save the pictures, then benchmark it.

The HUD is a drawing surface over state, so the pictures can be produced
without hardware: this driver feeds the CSI view a synthetic stream that
behaves like the real board (the same 64 subcarriers, the same unused DC
and guard band, the same ~178 packets/s), and renders every mode.

    python3 tools/hud_shots.py --out docs/alpha002
    python3 tools/hud_shots.py --bench
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from typing import Dict, List

import cv2
import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from specter.hud.renderer import HUD_H, HUD_W, HudState, render  # noqa: E402
from specter.sensors.base import Health, SensorStatus  # noqa: E402
from specter.sensors.esp32.csi_analysis import CsiViewState  # noqa: E402
from specter.sensors.esp32.experiment import (GuidedExperiment,  # noqa: E402
                                               TrialSpec)

#: the board's real 802.11n 20 MHz layout, verified on the wire
NULL_CARRIERS = (0,) + tuple(range(27, 38))
CARRIERS = 64


def synthetic_spectrum() -> np.ndarray:
    """A realistic subcarrier profile: high at the edges, a dip in the middle."""
    x = np.arange(CARRIERS, dtype=np.float32)
    prof = 18.0 + 2.2 * np.exp(-((x - 8) ** 2) / 30.0) \
        + 3.0 * np.exp(-((x - 56) ** 2) / 40.0) \
        - 9.0 * np.exp(-((x - 45) ** 2) / 90.0)
    prof[0] = 0.0
    for c in NULL_CARRIERS:
        prof[c] = 0.0
    return prof


def synthetic_stream(packets: int = 4200, motion_from: int = 1700,
                     motion_to: int = 3400, rate: float = 178.0,
                     seed: int = 3) -> List[Dict]:
    """A synthetic CSI stream: quiet, then a body in the path, then quiet."""
    rng = np.random.default_rng(seed)
    prof = synthetic_spectrum()
    out = []
    for i in range(packets):
        moving = motion_from <= i < motion_to
        gain = 1.0 + (0.35 if moving else 0.0) * rng.random()
        amps = prof * gain * (1.0 + 0.06 * rng.standard_normal(CARRIERS))
        if moving:
            # a moving body: a few carriers fade and a few deepen
            fade = rng.choice([38, 39, 40, 48, 49, 50], size=3, replace=False)
            for c in fade:
                amps[c] *= rng.uniform(0.25, 0.55)
        amps = np.clip(amps, 0, None)
        out.append({
            "id": 1000 + i,
            "mac": "b8:62:1f:e5:ac:62",
            "channel": 11,
            "rssi": -70 if not moving else -66,
            "noise_floor": -96,
            "local_timestamp": 17_000_000 + int(i * 1e6 / rate),
            "amplitudes": amps,
        })
    return out


def build_csi_view(stream, health=None) -> Dict:
    state = CsiViewState(columns=640, carriers=CARRIERS, packet_rate=178.0)
    for pkt in stream:
        state.push_amplitudes(pkt["amplitudes"], rssi=pkt["rssi"],
                               noise_floor=pkt["noise_floor"],
                               local_timestamp=pkt["local_timestamp"],
                               source_mac=pkt["mac"],
                               source_channel=pkt["channel"])
    view = state.view(health)
    view["waterfall"] = state.waterfall()
    view["trace"] = state.trace()
    view["used_mask"] = state.used_mask()
    return view


def _health(state="CONNECTED", detail="esp32: streaming"):
    class H:
        pass
    h = H()
    h.state = type("S", (), {"value": state})()
    h.detail = detail
    h.board_mac = "14:C1:9F:26:52:EC"
    h.uptime_s = 734.2
    h.bytes = 58_213_441
    h.packets = 131_004
    h.packets_per_s = 178.4
    h.gaps = 0
    h.missing_packets = 0
    h.malformed = 1
    h.unknown_lines = 0
    h.dropped = 0
    h.first_id = 1000
    h.last_id = 131_003
    h.silence_s = 0.012
    h.reconnects = 0
    return h


def sensor_rows() -> List[SensorStatus]:
    return [
        SensorStatus("nightvision", "NV CAM IMX462", Health.OK, "usb3-1  1280x800"),
        SensorStatus("pose", "POSE ENGINE", Health.OK, "yolo11n-pose"),
        SensorStatus("thermal", "THERMAL SENSOR", Health.NOT_INSTALLED, "no driver"),
        SensorStatus("radar", "RADAR", Health.NOT_INSTALLED, "no driver"),
        SensorStatus("wifi_csi", "WIFI CSI ESP32", Health.OK, "CONNECTED | 178 pkt"),
        SensorStatus("supervisor", "SUPERVISOR ESP32", Health.NOT_INSTALLED,
                     "telemetry not available"),
        SensorStatus("imu", "IMU BNO085", Health.NOT_INSTALLED, "no driver"),
        SensorStatus("gnss", "GNSS NEO-M9N", Health.NOT_INSTALLED, "no driver"),
        SensorStatus("uwb", "UWB DW1000", Health.NOT_INSTALLED, "no driver"),
    ]


def make_experiment_state(phase="RECORDING", index=2, total=6,
                          remaining=18.0) -> GuidedExperiment:
    exp = GuidedExperiment(
        [TrialSpec("stationary", 30.0, "Stand still and do not move."),
         TrialSpec("hand", 30.0, "Wave one hand up and down, in place.")] * 3,
        consent="subject: operator (self); informed: yes; agreed: yes")
    exp.phase = phase
    exp.index = index
    exp.phase_started = time.time() - 2.0
    return exp


def render_modes(out_dir: str) -> List[str]:
    os.makedirs(out_dir, exist_ok=True)
    written = []
    stream = synthetic_stream()

    # a camera-ish image for the optical modes
    rng = np.random.default_rng(7)
    base = np.full((720, 1280, 3), 34, np.uint8)
    for i in range(0, 720, 40):
        cv2.line(base, (0, i), (1280, i), (46, 44, 48), 1)
    cv2.circle(base, (640, 300), 90, (70, 90, 120), -1)
    cv2.rectangle(base, (580, 180), (700, 430), (80, 100, 130), 2)
    base = np.clip(base.astype(np.int16)
                   + rng.integers(-8, 8, base.shape), 0, 255).astype(np.uint8)

    st = HudState(mode="CSI", sensors=sensor_rows(), source_name="synthetic",
                  session="20261021-abc123")
    st.csi = build_csi_view(stream, _health())
    st.experiment = make_experiment_state().state()
    p = os.path.join(out_dir, "hud_csi_waterfall.png")
    cv2.imwrite(p, render(base, st))
    written.append(p)

    st2 = HudState(mode="CSI", sensors=sensor_rows(), source_name="synthetic",
                   session="20261021-abc123")
    st2.csi = build_csi_view(stream, _health())
    st2.csi_spectrum = True
    p = os.path.join(out_dir, "hud_csi_spectrum.png")
    cv2.imwrite(p, render(base, st2))
    written.append(p)

    st3 = HudState(mode="OPTICAL", sensors=sensor_rows(), source_name="IMX462",
                   session="20261021-abc123")
    p = os.path.join(out_dir, "hud_optical.png")
    cv2.imwrite(p, render(base, st3))
    written.append(p)

    st4 = HudState(mode="NIGHT-GREEN", sensors=sensor_rows(), source_name="IMX462",
                   session="20261021-abc123")
    p = os.path.join(out_dir, "hud_night_green.png")
    cv2.imwrite(p, render(base, st4))
    written.append(p)

    return written


def benchmark(frames: int = 300) -> Dict:
    """Time the renderer, and the CSI state update separately."""
    stream = synthetic_stream(packets=1200)
    state = CsiViewState(columns=640, carriers=CARRIERS)
    for pkt in stream:
        state.push_amplitudes(pkt["amplitudes"], rssi=pkt["rssi"],
                               source_mac=pkt["mac"], source_channel=pkt["channel"])
    view = state.view(_health())
    view["waterfall"] = state.waterfall()
    view["trace"] = state.trace()
    view["used_mask"] = state.used_mask()

    st = HudState(mode="CSI", sensors=sensor_rows(), source_name="synthetic")
    st.csi = view
    img = np.full((720, 1280, 3), 34, np.uint8)

    render(img, st)  # warm up
    t0 = time.perf_counter()
    for _ in range(frames):
        render(img, st)
    t_render = (time.perf_counter() - t0) / frames

    # the state update, at the real packet rate
    t0 = time.perf_counter()
    for pkt in stream[:600]:
        state.push_amplitudes(pkt["amplitudes"], rssi=pkt["rssi"])
    t_push = (time.perf_counter() - t0) / 600

    # the cost of the two rolling buffers alone
    t0 = time.perf_counter()
    for _ in range(frames):
        state.waterfall()
        state.trace()
    t_buffers = (time.perf_counter() - t0) / frames

    return {
        "frames": frames,
        "render_ms": round(t_render * 1000, 3),
        "render_fps": round(1.0 / t_render, 1),
        "state_update_us_per_packet": round(t_push * 1e6, 2),
        "buffer_snapshot_ms": round(t_buffers * 1000, 3),
        "waterfall_shape": list(state.waterfall().shape),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="docs/alpha002")
    ap.add_argument("--bench", action="store_true", help="benchmark the renderer")
    ap.add_argument("--no-shots", action="store_true")
    args = ap.parse_args(argv)

    if not args.no_shots:
        for p in render_modes(args.out):
            print("wrote", p)

    if args.bench:
        r = benchmark()
        print("\n--- HUD benchmark ---")
        for k, v in r.items():
            print(f"  {k}: {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
