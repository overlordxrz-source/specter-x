"""Synthetic three-condition CSI link for Alpha 003 code tests.

This is a **test fixture**, not a physical model of a room and not evidence of
presence detection. It exists to exercise the offline pipeline on cases whose
truth is known:

* ``empty`` - no person, slow gain/phase drift, noise;
* ``stationary`` - a fixed reflector plus a small breathing-like phase
  oscillation, so static presence and micro-motion can be separated;
* ``moving`` - a reflector whose phase moves strongly over time.

The channel also carries a per-session random static profile, PHY-rate
amplitude scaling, RSSI variation and packet timing jitter. Those are the
confounds a real session has; a benchmark that removes them is not useful.
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional

import numpy as np

CARRIERS = 64
NULL = (0,) + tuple(range(27, 38))
CONDITIONS = ("empty", "stationary", "moving")


class PresenceSyntheticLink:
    """Three-condition synthetic CSI source with a known label per trial."""

    def __init__(self, static_effect: float = 0.08,
                 moving_effect: float = 0.85,
                 breathing_phase: float = 0.035,
                 drift_phase: float = 0.18,
                 noise: float = 0.018,
                 rate_hz: float = 20.0,
                 seed: int = 0):
        self.static_effect = float(static_effect)
        self.moving_effect = float(moving_effect)
        self.breathing_phase = float(breathing_phase)
        self.drift_phase = float(drift_phase)
        self.noise = float(noise)
        self.rate_hz = float(rate_hz)
        self.rng = np.random.default_rng(seed)

    def _profile(self) -> np.ndarray:
        x = np.arange(CARRIERS, dtype=np.float64)
        amp = (1.0 + 0.35 * np.exp(-((x - 8) ** 2) / 40.0)
               + 0.45 * np.exp(-((x - 56) ** 2) / 55.0))
        phase = self.rng.uniform(-math.pi, math.pi, CARRIERS)
        h = amp * np.exp(1j * phase)
        h[list(NULL)] = 0.0
        return h

    def _trial(self, label: str, seconds: float, block: int,
               session_id: str, profile: np.ndarray,
               seed: int, body_slope: float = 0.17,
               body_phase: float = 0.8,
               rssi_offset_db: float = 0.0) -> Dict:
        rng = np.random.default_rng(seed)
        n = max(int(round(seconds * self.rate_hz)), 8)
        dt = 1.0 / self.rate_hz
        t = np.cumsum(dt + rng.normal(0.0, dt * 0.02, n))
        t = t - t[0]
        rate = np.full(n, 11, dtype=np.int32)
        # common-mode drift is removed by differential phase; it is still
        # present so a feature that uses absolute phase would be punished.
        common = (self.drift_phase * np.sin(2 * math.pi * 0.021 * t + 0.7)
                  + 0.03 * np.sin(2 * math.pi * 0.11 * t + 1.1))
        gain = 1.0 + 0.035 * np.sin(2 * math.pi * 0.013 * t + 0.4)
        body = np.zeros((n, CARRIERS), dtype=np.complex128)
        attenuation = np.zeros(n, dtype=np.float64)
        if label == "stationary":
            amp = self.static_effect
            phase = (body_phase + self.breathing_phase *
                     np.sin(2 * math.pi * 0.25 * t + 0.3))
            slope = body_slope
            body = amp * np.exp(1j * (slope * np.arange(CARRIERS)[None, :]
                                      + phase[:, None]))
            attenuation[:] = 0.15
        elif label == "moving":
            amp = self.moving_effect * (0.75 + 0.25 *
                                        np.sin(2 * math.pi * 0.65 * t + 0.2))
            phase = (body_phase + 2 * math.pi * 0.85 * t
                     + 0.5 * np.sin(2 * math.pi * 0.31 * t))
            slope = body_slope
            body = amp[:, None] * np.exp(
                1j * (slope * np.arange(CARRIERS)[None, :]
                      + phase[:, None]))
            attenuation[:] = 0.25 + 0.10 * np.sin(2 * math.pi * 0.65 * t)
        elif label != "empty":
            raise ValueError(f"unknown label {label!r}")

        h = (profile[None, :] * np.exp(1j * common[:, None]) * gain[:, None]
             + body)
        h = h + (rng.normal(0.0, self.noise, h.shape)
                 + 1j * rng.normal(0.0, self.noise, h.shape))
        # integer IQ, in the ESP32's (imag, real) pair order
        iq = np.empty(h.size * 2, dtype=np.int64)
        real = np.rint(h.real * 100.0).astype(np.int64)
        imag = np.rint(h.imag * 100.0).astype(np.int64)
        iq[0::2] = imag.ravel()
        iq[1::2] = real.ravel()
        iq = iq.reshape(n, CARRIERS, 2)
        iq[:, list(NULL), :] = 0
        iq = iq.ravel()
        amps = np.abs(h).astype(np.float32)
        amps[:, list(NULL)] = 0.0
        rssi = (-50.0 + rssi_offset_db - attenuation
                + 0.8 * np.sin(2 * math.pi * 0.017 * t)
                + rng.normal(0.0, 0.25, n))
        samples = []
        for i in range(n):
            samples.append({
                "id": int(block * 100000 + i),
                "t": float(t[i]),
                "sig_len": 138,
                "first_word_invalid": False,
                "rssi": float(rssi[i]),
                "rate": int(rate[i]),
                "amplitudes": amps[i].tolist(),
                "iq": iq[i * CARRIERS * 2:(i + 1) * CARRIERS * 2].tolist(),
            })
        return {
            "session_id": session_id,
            "block": int(block),
            "label": label,
            "ground_truth": label,
            "samples": samples,
            "synthetic": True,
        }

    def session(self, session_id: str, blocks: int = 8,
                seconds: float = 10.0, order_seed: Optional[int] = None,
                seed: Optional[int] = None) -> List[Dict]:
        rng = np.random.default_rng(self.rng.integers(0, 2 ** 31)
                                    if seed is None else seed)
        profile = self._profile()
        body_slope = float(rng.uniform(0.08, 0.30))
        body_phase = float(rng.uniform(-math.pi, math.pi))
        rssi_offset = float(rng.normal(0.0, 1.2))
        trials = []
        for b in range(int(blocks)):
            labels = list(CONDITIONS)
            rng.shuffle(labels)
            for j, label in enumerate(labels):
                trials.append(self._trial(
                    label, seconds, b, session_id, profile,
                    seed=int(rng.integers(0, 2 ** 31)) + j,
                    body_slope=body_slope, body_phase=body_phase,
                    rssi_offset_db=rssi_offset))
        return trials

    def make_dataset(self, n_sessions: int = 6, blocks: int = 8,
                     seconds: float = 10.0) -> List[Dict]:
        out = []
        for s in range(int(n_sessions)):
            out.extend(self.session(f"syn-{s}", blocks=blocks,
                                    seconds=seconds,
                                    seed=int(self.rng.integers(0, 2 ** 31))))
        return out
