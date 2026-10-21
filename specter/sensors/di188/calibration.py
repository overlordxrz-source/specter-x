"""Counts -> volts calibration for the DI-188.

The instrument's own firmware already applies a per-channel digital
``scale``/``offset`` (readable from the device flash via ``readflash``), so the
counts we receive are device-calibrated. What remains unknown is **how many
volts one count represents**.

Two ways to close that gap:

``nominal``
    Datasheet-derived. The DI-188 is +/-10 V full scale over the +/-32768 count
    domain, i.e. ~305 uV per count. This is an *estimate*: the open-source
    front-end reference is not trimmed to a known voltage and no calibration
    certificate exists. It is labelled ``UNCALIBRATED`` everywhere.

``measured``
    A two-or-more point fit against a known voltage source. This is the only
    way to claim a calibrated measurement, and it requires a reference (see
    ``docs/di188-wiring.md`` for the safe first-measurement procedure).

Everything is provenance-first: a calibration file records which instrument,
which reference, which operator and when it was made.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

#: Nominal front-end profiles, keyed by the device's ADC scale constant.
PROFILES: Dict[str, Dict[str, float]] = {
    # DI-188 analog front end: +/-10 V over the +/-32768 count domain.
    "di188_pm10v": {"full_scale_v": 10.0, "counts_full_scale": 32768.0},
    # Bare Seeed XIAO M0 ADC inputs (no +/-10 V front end present).
    "xiao_0_3v3": {"full_scale_v": 3.3, "counts_full_scale": 32767.0},
}

NOMINAL = "nominal"
MEASURED = "measured"


@dataclass
class ChannelCalibration:
    """A linear counts -> volts model for one channel."""

    gain: float                       # volts per count
    offset: float = 0.0               # volts at zero counts
    basis: str = NOMINAL              # "nominal" | "measured"
    method: str = ""                  # human readable description
    reference: str = ""               # what the reference was
    uncertainty_v: float = 0.0        # +/- volts (0 when unknown)
    points: List[Tuple[float, float]] = field(default_factory=list)  # (counts, volts)

    @property
    def calibrated(self) -> bool:
        return self.basis == MEASURED and len(self.points) >= 2

    def to_volts(self, counts: float) -> float:
        return self.gain * counts + self.offset

    def as_dict(self) -> Dict:
        return {
            "gain": self.gain,
            "offset": self.offset,
            "basis": self.basis,
            "method": self.method,
            "reference": self.reference,
            "uncertainty_v": self.uncertainty_v,
            "points": [[c, v] for c, v in self.points],
            "calibrated": self.calibrated,
        }

    @classmethod
    def from_dict(cls, d: Dict) -> "ChannelCalibration":
        return cls(
            gain=float(d["gain"]),
            offset=float(d.get("offset", 0.0)),
            basis=d.get("basis", NOMINAL),
            method=d.get("method", ""),
            reference=d.get("reference", ""),
            uncertainty_v=float(d.get("uncertainty_v", 0.0)),
            points=[(float(c), float(v)) for c, v in d.get("points", [])],
        )


@dataclass
class CalibrationSet:
    """Per-channel calibration plus the provenance of the whole set."""

    channels: Dict[int, ChannelCalibration] = field(default_factory=dict)
    device_serial: str = ""
    device_model: str = ""
    profile: str = "unknown"
    created_utc: str = ""
    operator: str = ""
    notes: str = ""

    # -- construction ------------------------------------------------------

    @classmethod
    def nominal(cls, profile: str, channels: Sequence[int],
                device_serial: str = "", device_model: str = "") -> "CalibrationSet":
        """Datasheet-derived fallback for every requested channel."""
        spec = PROFILES.get(profile)
        out = cls(profile=profile, device_serial=device_serial,
                  device_model=device_model, created_utc=_utcnow())
        for ch in channels:
            if spec is None:
                out.channels[ch] = ChannelCalibration(
                    gain=0.0, basis=NOMINAL,
                    method="unknown front end - volts not claimed",
                    reference="")
            else:
                gain = spec["full_scale_v"] / spec["counts_full_scale"]
                out.channels[ch] = ChannelCalibration(
                    gain=gain, basis=NOMINAL,
                    method=(f"datasheet nominal: {spec['full_scale_v']:g} V full scale "
                            f"over +/-{spec['counts_full_scale']:.0f} counts"),
                    reference="datasheet (uncertified)")
        return out

    @classmethod
    def load(cls, path: str) -> "CalibrationSet":
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        cs = cls(
            device_serial=data.get("device_serial", ""),
            device_model=data.get("device_model", ""),
            profile=data.get("profile", "unknown"),
            created_utc=data.get("created_utc", ""),
            operator=data.get("operator", ""),
            notes=data.get("notes", ""),
        )
        for key, ch in (data.get("channels") or {}).items():
            cs.channels[int(key)] = ChannelCalibration.from_dict(ch)
        return cs

    def save(self, path: str) -> None:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        payload = {
            "_note": "SPECTER-X DI-188 counts->volts calibration. "
                     "Basis 'nominal' is an uncertified datasheet estimate; "
                     "basis 'measured' was fitted against a known reference.",
            "device_serial": self.device_serial,
            "device_model": self.device_model,
            "profile": self.profile,
            "created_utc": self.created_utc or _utcnow(),
            "operator": self.operator,
            "notes": self.notes,
            "channels": {str(k): v.as_dict() for k, v in sorted(self.channels.items())},
        }
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
            fh.write("\n")

    # -- use ---------------------------------------------------------------

    def for_channel(self, ch: int) -> ChannelCalibration:
        if ch in self.channels:
            return self.channels[ch]
        spec = PROFILES.get(self.profile)
        if spec is None:
            return ChannelCalibration(gain=0.0, basis=NOMINAL,
                                      method="unknown front end - volts not claimed")
        return ChannelCalibration(
            gain=spec["full_scale_v"] / spec["counts_full_scale"],
            basis=NOMINAL,
            method=f"datasheet nominal ({self.profile})",
            reference="datasheet (uncertified)")

    def to_volts(self, ch: int, counts: float) -> Optional[float]:
        cal = self.for_channel(ch)
        if cal.gain == 0.0:
            return None
        return cal.to_volts(counts)

    @property
    def any_calibrated(self) -> bool:
        return any(c.calibrated for c in self.channels.values())

    def basis_label(self) -> str:
        if self.any_calibrated:
            return "CALIBRATED"
        return "UNCALIBRATED (nominal)"

    def as_dict(self) -> Dict:
        return {
            "device_serial": self.device_serial,
            "device_model": self.device_model,
            "profile": self.profile,
            "created_utc": self.created_utc,
            "operator": self.operator,
            "notes": self.notes,
            "basis_label": self.basis_label(),
            "any_calibrated": self.any_calibrated,
            "channels": {str(k): v.as_dict() for k, v in sorted(self.channels.items())},
        }


def fit_linear(points: Sequence[Tuple[float, float]]) -> Tuple[float, float, float]:
    """Least-squares fit ``volts = gain*counts + offset``.

    Returns ``(gain, offset, rms_residual_v)``. Needs at least two distinct
    count levels; raises ValueError otherwise.
    """
    if len(points) < 2:
        raise ValueError("calibration needs at least two points")
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    n = len(xs)
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    sxx = sum((x - mean_x) ** 2 for x in xs)
    if sxx <= 0:
        raise ValueError("calibration points have identical count levels")
    sxy = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    gain = sxy / sxx
    offset = mean_y - gain * mean_x
    resid = [y - (gain * x + offset) for x, y in zip(xs, ys)]
    rms = (sum(r * r for r in resid) / n) ** 0.5
    return gain, offset, rms


def _utcnow() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
