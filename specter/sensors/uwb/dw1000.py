"""Qorvo DW1000 UWB driver (UWB Click, MIKROE-4199): DS-TWR ranging.

Host-side protocol: this module frames poll/response/final exchanges and
converts timestamps to distances; the SPI register poking itself stays
behind `Dw1000Driver` so CI exercises the same code path via `UwbSimulator`,
where pairs of virtual units range against each other with ~10 cm noise and
an optional NLOS bias flag.

Every range is a Measurement(kind="range", frame "body") carrying the peer
unit id, distance and std — provenance survives into team fusion.

Hardware note: real DW1000 timestamps are 40-bit device ticks (~15.65 ps;
the counter wraps about every 17.2 s). The SPI/hardware path MUST convert
with tick_delta_s() and range via ds_twr_tof_ticks()/exchange_ticks() —
never feed raw ticks, or seconds differenced across the wrap, into
ds_twr_tof().
"""
from __future__ import annotations

import struct
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

from specter.fusion.measurement import Measurement, Provenance

SENSOR = "uwb"
FRAME = "body"
ALGORITHM_TWR = "ds-twr"
SPEED_OF_LIGHT = 299_702_547.0  # m/s (DW1000 clock-compensated constant)
NOMINAL_STD_M = 0.10  # ~10 cm in line of sight

# DW1000 system clock: 499.2 MHz * 128 -> ~15.65 ps per tick, 40-bit counter.
DW1000_TICK_S = 1.0 / 63_897_600_000.0
TICK_MASK_40 = (1 << 40) - 1
TICK_WRAP_S = (1 << 40) * DW1000_TICK_S  # ~17.2 s


def tick_delta_s(newer_ticks: int, older_ticks: int) -> float:
    """Wrap-safe (newer - older) of raw 40-bit DW1000 timestamps, in seconds."""
    return ((int(newer_ticks) - int(older_ticks)) & TICK_MASK_40) * DW1000_TICK_S


def tof_to_distance_m(tof_s: float) -> float:
    return float(tof_s) * SPEED_OF_LIGHT


def ds_twr_tof(t_round1: float, t_reply1: float, t_round2: float, t_reply2: float) -> float:
    """Classic double-sided TWR time-of-flight from 4 timestamps (seconds)."""
    num = t_round1 * t_round2 - t_reply1 * t_reply2
    den = t_round1 + t_round2 + t_reply1 + t_reply2
    if den <= 0:
        raise ValueError("non-positive DS-TWR denominator")
    return num / den


def ds_twr_tof_ticks(t1: int, t2: int, t3: int, t4: int, t5: int, t6: int) -> float:
    """DS-TWR time-of-flight from six raw 40-bit DW1000 timestamps (wrap-safe).

    Initiator: t1 poll TX, t2 response RX, t3 final TX.
    Responder: t4 poll RX, t5 response TX, t6 final RX.
    Mapping to ds_twr_tof(): round1 = t2-t1 (initiator), reply1 = t5-t4
    (responder), round2 = t6-t5 (responder), reply2 = t3-t2 (initiator).
    """
    r1 = tick_delta_s(t2, t1)
    p1 = tick_delta_s(t5, t4)
    r2 = tick_delta_s(t6, t5)
    p2 = tick_delta_s(t3, t2)
    return ds_twr_tof(r1, p1, r2, p2)


# --- host-side air protocol (compact binary, also used on the wire in sims) ---
# Numeric unit ids are 16-bit on the wire for both ends (src and dst alike):
# poll:  >BHH  (msg_type=1, src, dst) ; response: >BHHd ; final: >BHHdddd
MSG_POLL, MSG_RESP, MSG_FINAL = 1, 2, 3


def encode_poll(src: int, dst: int) -> bytes:
    return struct.pack(">BHH", MSG_POLL, src & 0xFFFF, dst & 0xFFFF)


def encode_response(src: int, dst: int, t_reply1: float) -> bytes:
    return struct.pack(">BHHd", MSG_RESP, src & 0xFFFF, dst & 0xFFFF, t_reply1)


def encode_final(src: int, dst: int, r1: float, p1: float, r2: float, p2: float) -> bytes:
    return struct.pack(">BHHdddd", MSG_FINAL, src & 0xFFFF, dst & 0xFFFF, r1, p1, r2, p2)


def decode_frame(buf: bytes) -> tuple:
    if len(buf) < 5:
        raise ValueError("frame too short")
    kind = buf[0]
    if kind == MSG_POLL and len(buf) == 5:
        _, src, dst = struct.unpack(">BHH", buf)
        return ("poll", src, dst)
    if kind == MSG_RESP and len(buf) == 13:
        _, src, dst, t = struct.unpack(">BHHd", buf)
        return ("response", src, dst, t)
    if kind == MSG_FINAL and len(buf) == 37:
        _, src, dst, r1, p1, r2, p2 = struct.unpack(">BHHdddd", buf)
        return ("final", src, dst, r1, p1, r2, p2)
    raise ValueError(f"unknown UWB frame kind={kind} len={len(buf)}")


def range_measurement(
    unit_id: str,
    peer_id: str,
    distance_m: float,
    std_m: float = NOMINAL_STD_M,
    *,
    sensor_id: str = "dw1000-0",
    t_host: Optional[float] = None,
    frame_index: Optional[int] = None,
    sim: bool = False,
    nlos: bool = False,
    tof_s: Optional[float] = None,
) -> Measurement:
    if distance_m < 0:
        raise ValueError("distance must be non-negative")
    std = max(float(std_m) * (3.0 if nlos else 1.0), 1e-3)
    return Measurement(
        sensor=SENSOR,
        kind="range",
        t_host=t_host if t_host is not None else time.time(),
        frame_id=FRAME,
        value={
            "unit_id": unit_id,
            "peer_id": peer_id,
            "distance_m": float(distance_m),
            "std_m": float(std),
            "nlos": bool(nlos),
            "tof_s": float(tof_s) if tof_s is not None else float(distance_m) / SPEED_OF_LIGHT,
            "sim": bool(sim),
        },
        confidence=0.9 if not nlos else 0.4,
        covariance=np.array([[std * std]]),
        provenance=Provenance(
            sensor_id=sensor_id, source=SENSOR,
            algorithm=ALGORITHM_TWR + ("-sim" if sim else ""),
            frame_index=frame_index,
            notes="NLOS: accuracy degraded" if nlos else None,
        ),
    )


@dataclass
class Dw1000Driver:
    """Host-side DW1000: wraps the air protocol; SPI backend opens lazily."""

    unit_id: str = "unit-1"
    sensor_id: str = "dw1000-0"
    _i: int = 0

    def exchange(self, peer_id: str, t_round1: float, t_reply1: float,
                 t_round2: float, t_reply2: float,
                 *, nlos: bool = False) -> Measurement:
        self._i += 1
        tof = ds_twr_tof(t_round1, t_reply1, t_round2, t_reply2)
        d = tof_to_distance_m(tof)
        return range_measurement(self.unit_id, peer_id, d, NOMINAL_STD_M,
                                 sensor_id=self.sensor_id, frame_index=self._i,
                                 nlos=nlos, tof_s=tof)

    def exchange_ticks(self, peer_id: str, t1: int, t2: int, t3: int,
                       t4: int, t5: int, t6: int,
                       *, nlos: bool = False) -> Measurement:
        """Hardware path: six raw 40-bit timestamps straight from the DW1000.

        Wrap handling lives in ds_twr_tof_ticks(); callers must NOT
        pre-convert to seconds.
        """
        self._i += 1
        tof = ds_twr_tof_ticks(t1, t2, t3, t4, t5, t6)
        d = tof_to_distance_m(tof)
        return range_measurement(self.unit_id, peer_id, d, NOMINAL_STD_M,
                                 sensor_id=self.sensor_id, frame_index=self._i,
                                 nlos=nlos, tof_s=tof)

    def try_open_hardware(self) -> bool:
        try:
            import spidev  # type: ignore

            spi = spidev.SpiDev()
            spi.open(0, 0)
            spi.close()
            return True
        except Exception:
            return False


@dataclass
class UwbSimulator:
    """Pairwise ranging between virtual units for CI (replaces the air link).

    Positions are ground-truth ENU metres keyed by unit id. range_all()
    returns per-unit lists of range Measurements with LOS noise (~10 cm) and
    optional NLOS pairs (extra bias + inflated std, flagged in the value).
    """

    std_m: float = NOMINAL_STD_M
    nlos_pairs: Tuple[Tuple[str, str], ...] = ()
    nlos_bias_m: float = 0.6
    seed: int = 11

    def __post_init__(self) -> None:
        self._rng = np.random.default_rng(self.seed)
        self._counts: Dict[str, int] = {}

    def _is_nlos(self, a: str, b: str) -> bool:
        return (a, b) in self.nlos_pairs or (b, a) in self.nlos_pairs

    def ranging(
        self, positions: Dict[str, np.ndarray]
    ) -> Dict[str, List[Measurement]]:
        out: Dict[str, List[Measurement]] = {u: [] for u in positions}
        ids = sorted(positions)
        for i, a in enumerate(ids):
            for b in ids[i + 1 :]:
                true_d = float(np.linalg.norm(
                    np.asarray(positions[a], float) - np.asarray(positions[b], float)))
                nlos = self._is_nlos(a, b)
                noise = self._rng.normal(0, self.std_m * (3.0 if nlos else 1.0))
                bias = self.nlos_bias_m if nlos else 0.0
                for src, dst in ((a, b), (b, a)):
                    self._counts[src] = self._counts.get(src, 0) + 1
                    # protocol round-trip (timestamps consistent with measured d)
                    tof = (true_d + bias + noise) / SPEED_OF_LIGHT
                    r = tof * 1.02
                    m = range_measurement(src, dst, true_d + bias + noise,
                                          self.std_m, sensor_id="dw1000-sim",
                                          frame_index=self._counts[src],
                                          sim=True, nlos=nlos, tof_s=tof)
                    out[src].append(m)
        return out
