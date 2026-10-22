"""A synthetic CSI link with a *known* ground truth.

The question "can this pipeline detect a person?" cannot be answered by
running it on a real link, because a real link never tells you what was
actually happening in the room. A synthetic link can: it is built from a
stated model, so the answer is known before the experiment starts.

What this models
----------------
A single access point and a single station. The station measures the
downlink CSI of 64 complex subcarriers, 12 of which are unused (DC and the
guard band). The channel is a static multipath profile plus:

* **a person**, which adds a reflection whose delay changes with the
  person's distance, and whose amplitude is a function of distance;
* **the radio**, which drifts: a slow AGC wander and a per-frame PHY rate
  that changes the amplitude scale, exactly as the real board does;
* **a background**, which is the temporal noise the features have to see
  through.

The ground truth is therefore a label per trial plus a *known effect size*,
which is what makes it possible to measure the detection pipeline's
sensitivity and, more importantly, its **false-positive rate**: run the
whole procedure on trials where the ground truth says "nobody is there" and
count how often it claims otherwise.

    from specter.sensors.esp32.synthetic_link import SyntheticLink
    link = SyntheticLink(effect=0.06)
    trial = link.trial("stationary", 30.0)
    trial2 = link.trial("hand", 30.0)
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

#: the board's real HT20 LLTF layout: 64 carriers, of which these are unused
NULL_CARRIERS = (0,) + tuple(range(27, 38))
CARRIERS = 64
USED = np.array([c not in NULL_CARRIERS for c in range(CARRIERS)])


class SyntheticLink:
    """A CSI link whose truth is known.

    Parameters
    ----------
    effect:
        the *amplitude of the temporal disturbance* a person adds, as a
        fraction of the per-carrier amplitude. 0.0 means a person has no
        effect at all - that is the null control.
    rate_hz:
        the packet rate, to match the real board (~178 packets/s).
    gain:
        the receiver's AGC scale, which drifts slowly.
    phy_rates:
        the PHY rate codes the frames arrive at. Each rate has its own
        amplitude scale, because the CSI is measured on the preamble of a
        frame received at that rate.
    """

    def __init__(self, effect: float = 0.05, rate_hz: float = 178.0,
                 seed: int = 0, gain: float = 20.0,
                 phy_rates: Sequence[int] = (8, 9, 11, 13, 14),
                 rate_scales: Optional[Dict[int, float]] = None):
        self.effect = float(effect)
        self.rate_hz = float(rate_hz)
        self.gain = float(gain)
        self.phy_rates = list(phy_rates)
        self.rate_scales = rate_scales or {r: 0.85 + 0.05 * (i + 1)
                                           for i, r in enumerate(self.phy_rates)}
        self.rng = np.random.default_rng(seed)
        self._profile = self._static_profile()
        self._agc = 1.0
        self._seq = 0
        self._t = 0.0

    # -- the channel --------------------------------------------------------

    def _static_profile(self) -> np.ndarray:
        """A plausible static multipath profile: high at the band edges."""
        x = np.arange(CARRIERS, dtype=np.float64)
        prof = 1.0 + 0.55 * np.exp(-((x - 6) ** 2) / 26.0) \
            + 0.75 * np.exp(-((x - 58) ** 2) / 34.0) \
            - 0.35 * np.exp(-((x - 46) ** 2) / 80.0)
        prof[list(NULL_CARRIERS)] = 0.0
        return prof

    def _person(self, amount: float, phase: float) -> np.ndarray:
        """The perturbation a body adds to the profile.

        A body is a reflector: it adds a second path whose amplitude falls
        with distance and whose *phase* moves as they move. Both matter -
        a static reflector would change the amplitude and nothing else.
        """
        if amount <= 0:
            return np.zeros(CARRIERS)
        # a moving reflector: a few carriers are deepened and a few lifted,
        # and the pattern slides along the band as they move
        base = 0.5 + 0.5 * math.sin(phase)
        out = np.zeros(CARRIERS)
        for k in range(6):
            c = 6 + k * 9
            if c >= CARRIERS:
                break
            w = 0.6 + 0.4 * math.sin(phase + k)
            out[c] = amount * (1.0 if k % 2 == 0 else -0.7) * w
        out[list(NULL_CARRIERS)] = 0.0
        return out * base

    # -- the trials ---------------------------------------------------------

    def trial(self, label: str, seconds: float, moving: bool = False,
              packet_rate: Optional[float] = None) -> Dict:
        """One labelled trial of the synthetic link.

        ``moving`` is the ground truth: whether a body is in the path. It
        is what the analysis is asked to recover from the signal alone.
        """
        rate = packet_rate or self.rate_hz
        n = max(int(seconds * rate), 4)
        amps = np.zeros((n, CARRIERS), dtype=np.float32)
        rssi = np.zeros(n, dtype=np.float32)
        ids = np.zeros(n, dtype=np.int64)
        rates = np.zeros(n, dtype=np.int32)
        ts = np.zeros(n, dtype=np.float64)
        phase = self.rng.uniform(0, 2 * math.pi)
        for i in range(n):
            # the receiver's AGC drifts slowly
            self._agc = 1.0 + 0.04 * math.sin(self._t / 12.0)
            rate_code = self.phy_rates[i % len(self.phy_rates)]
            scale = self.rate_scales[rate_code]
            amount = self.effect if moving else 0.0
            if moving:
                phase += 0.45
            prof = self._profile + self._person(amount, phase)
            noise = self.rng.normal(0.0, 0.035, CARRIERS)
            values = np.clip((prof + noise) * self.gain * self._agc * scale, 0, None)
            values[list(NULL_CARRIERS)] = 0.0
            amps[i] = values
            rssi[i] = -70 + 6.0 * self._agc + self.rng.normal(0, 0.4)
            ids[i] = self._seq
            rates[i] = rate_code
            ts[i] = self._t
            self._seq += 1
            self._t += 1.0 / rate
        return {
            "label": label,
            "ground_truth_moving": bool(moving),
            "packets": n,
            "requested_s": seconds,
            "actual_s": round(n / rate, 3),
            "amplitudes": amps,
            "rssi": rssi,
            "ids": ids,
            "t": ts,
            "rates": rates,
            "used": USED.copy(),
            "effect_size": self.effect,
        }

    def set(self, labels: Sequence[str], repeats: int = 3,
            seconds: float = 30.0) -> List[Dict]:
        """A whole blinded set: the labels, repeated, with the ground truth
        following the label (stationary = nobody, the rest = somebody)."""
        out = []
        for r in range(repeats):
            for label in labels:
                out.append(self.trial(label, seconds,
                                      moving=(label != "stationary")))
        return out


def amplitude_to_complex(amps: np.ndarray, rng=None) -> np.ndarray:
    """Turn real amplitudes into complex I/Q, for testing the complex path.

    A magnitude alone cannot distinguish a phase change from an amplitude
    change, and the respiration experiment needs the phase. This builds a
    plausible complex buffer with the requested magnitudes and a random
    (or supplied) phase.
    """
    rng = rng or np.random.default_rng(0)
    phase = rng.uniform(-math.pi, math.pi, amps.shape)
    return amps * np.exp(1j * phase)
