"""Clock discipline: chrony/PTP does the real sync; this tracks and enforces it.

ClockSync records per-peer offset estimates (peer_t - local_t at receipt) and
rejects stale messages past max_age_s. Offsets are exposed for the session
log so a drifting unit shows up instead of silently warping fusion.
"""
from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict


@dataclass
class ClockSync:
    max_age_s: float = 2.0
    window: int = 32
    _offsets: Dict[str, Deque[float]] = field(default_factory=dict, repr=False)

    def observe(self, unit_id: str, peer_t: float,
                local_t: float | None = None) -> float:
        """Record an offset sample; return the smoothed offset for this peer."""
        local_t = time.time() if local_t is None else local_t
        q = self._offsets.setdefault(unit_id, deque(maxlen=self.window))
        q.append(peer_t - local_t)
        return sum(q) / len(q)

    def offset(self, unit_id: str) -> float:
        q = self._offsets.get(unit_id)
        return (sum(q) / len(q)) if q else 0.0

    def is_stale(self, peer_t: float, local_t: float | None = None) -> bool:
        local_t = time.time() if local_t is None else local_t
        return (local_t - peer_t) > self.max_age_s
