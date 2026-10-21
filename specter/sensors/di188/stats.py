"""Per-channel statistics and input-state labelling for the DI-188.

The repo rule is provenance first: a number may only be shown as a
*measurement* when we know a source is attached. A floating input produces
perfectly plausible numbers that mean nothing, so the monitor must say so.

State model
-----------
``CONNECTED``   a source is declared attached to this channel
``FLOATING``    the channel is declared empty - the readings are noise
``UNDECLARED``  nobody said - shown as "assumed floating" with a caveat

Software cannot tell a 0 V source apart from a floating input, so
``UNDECLARED`` is never silently upgraded to ``CONNECTED``.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Sequence


class ChannelState(str, Enum):
    CONNECTED = "CONNECTED"
    FLOATING = "FLOATING"
    UNDECLARED = "UNDECLARED"

    @property
    def is_measurement(self) -> bool:
        return self is ChannelState.CONNECTED


@dataclass
class ChannelStats:
    """Running statistics over device counts."""

    n: int = 0
    total: float = 0.0
    total_sq: float = 0.0
    minimum: float = math.inf
    maximum: float = -math.inf
    last: Optional[float] = None

    def add(self, value: float) -> None:
        self.n += 1
        self.total += value
        self.total_sq += value * value
        self.minimum = min(self.minimum, value)
        self.maximum = max(self.maximum, value)
        self.last = value

    def reset(self) -> None:
        self.n = 0
        self.total = 0.0
        self.total_sq = 0.0
        self.minimum = math.inf
        self.maximum = -math.inf
        self.last = None

    @property
    def mean(self) -> float:
        return self.total / self.n if self.n else 0.0

    @property
    def variance(self) -> float:
        if self.n < 2:
            return 0.0
        var = (self.total_sq - self.n * self.mean ** 2) / self.n
        return max(var, 0.0)

    @property
    def std(self) -> float:
        return math.sqrt(self.variance)

    @property
    def rms(self) -> float:
        return math.sqrt(self.total_sq / self.n) if self.n else 0.0

    @property
    def peak_to_peak(self) -> float:
        return (self.maximum - self.minimum) if self.n else 0.0

    def as_dict(self) -> Dict:
        return {
            "n": self.n,
            "mean": self.mean,
            "std": self.std,
            "min": self.minimum if self.n else 0.0,
            "max": self.maximum if self.n else 0.0,
            "rms": self.rms,
            "peak_to_peak": self.peak_to_peak,
            "last": self.last if self.last is not None else 0.0,
        }


@dataclass
class ChannelSpec:
    """How the operator declared one physical channel."""

    index: int
    label: str = ""
    connected: Optional[bool] = None     # None -> undeclared
    source: str = ""                     # what is plugged in
    terminal: str = ""                   # e.g. "+CH1 / -CH1"

    def state(self) -> ChannelState:
        if self.connected is True:
            return ChannelState.CONNECTED
        if self.connected is False:
            return ChannelState.FLOATING
        return ChannelState.UNDECLARED


DEFAULT_TERMINALS = {
    0: "+CH1 / -CH1",
    1: "+CH2 / -CH2",
    2: "+CH3 / -CH3",
    3: "+CH4 / -CH4",
}


def default_specs(n: int = 4) -> List[ChannelSpec]:
    """The four DI-188 analog channels, all *undeclared* by default.

    Nothing is declared connected until a source is actually wired and the
    operator says so - the safe default for a rig where the harness may be
    sitting on a shelf.
    """
    return [
        ChannelSpec(index=i, label=f"CH{i + 1}",
                    terminal=DEFAULT_TERMINALS.get(i, f"ch{i}"))
        for i in range(n)
    ]


@dataclass
class ChannelReport:
    """Everything the dashboard needs about one channel."""

    index: int
    label: str
    terminal: str
    state: ChannelState
    source: str
    stats: ChannelStats
    volts: Optional[float] = None
    volts_mean: Optional[float] = None
    volts_std: Optional[float] = None
    uncertainty_v: Optional[float] = None
    calibration_basis: str = "nominal"
    note: str = ""

    def as_dict(self) -> Dict:
        return {
            "index": self.index,
            "label": self.label,
            "terminal": self.terminal,
            "state": self.state.value,
            "is_measurement": self.state.is_measurement,
            "source": self.source,
            "note": self.note,
            "counts": self.stats.as_dict(),
            "volts": self.volts,
            "volts_mean": self.volts_mean,
            "volts_std": self.volts_std,
            "uncertainty_v": self.uncertainty_v,
            "calibration_basis": self.calibration_basis,
        }


class ChannelMonitor:
    """Tracks statistics and state for a set of channels."""

    def __init__(self, specs: Sequence[ChannelSpec]):
        self.specs: Dict[int, ChannelSpec] = {s.index: s for s in specs}
        self.stats: Dict[int, ChannelStats] = {s.index: ChannelStats() for s in specs}

    @property
    def channels(self) -> List[int]:
        return sorted(self.stats)

    def add(self, values: Sequence[float]) -> None:
        for idx, value in zip(self.channels, values):
            self.stats[idx].add(float(value))

    def reset(self) -> None:
        for st in self.stats.values():
            st.reset()

    def report(self, calibration=None, index: int = 0) -> List[ChannelReport]:
        """Build a report for every channel, applying the calibration basis."""
        out: List[ChannelReport] = []
        for idx in self.channels:
            spec = self.specs[idx]
            st = self.stats[idx]
            volts = volts_mean = volts_std = unc = None
            basis = "nominal"
            if calibration is not None:
                cal = calibration.for_channel(idx)
                basis = cal.basis
                if cal.gain != 0.0 and st.n:
                    volts = cal.to_volts(st.last if st.last is not None else 0.0)
                    volts_mean = cal.to_volts(st.mean)
                    volts_std = abs(cal.gain) * st.std
                    unc = cal.uncertainty_v or None
            state = spec.state()
            note = ""
            if state is ChannelState.UNDECLARED:
                note = "no source declared - readings are noise, not a measurement"
            elif state is ChannelState.FLOATING:
                note = "input declared floating - readings are noise, not a measurement"
            else:
                note = f"source: {spec.source or 'undeclared'}"
                if calibration is not None and not calibration.any_calibrated:
                    note += " | volts are nominal/uncertified"
            out.append(ChannelReport(
                index=idx,
                label=spec.label,
                terminal=spec.terminal,
                state=state,
                source=spec.source,
                stats=st,
                volts=volts,
                volts_mean=volts_mean,
                volts_std=volts_std,
                uncertainty_v=unc,
                calibration_basis=basis,
                note=note,
            ))
        return out
