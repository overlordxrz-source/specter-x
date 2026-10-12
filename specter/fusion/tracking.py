"""Multi-sensor tracking (stub, Stage 4).

Planned: constant-velocity Kalman filter per track in the body frame, gated
association (Mahalanobis) of Measurements from optical/thermal bearings, radar
points and Wi-Fi CSI presence. Every Track keeps the ids of the Measurements
that updated it, so fused output still has full provenance.

Stage 1 provides the interface and a trivial nearest-neighbour association so
other code can be written against it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np

from .measurement import Measurement


@dataclass
class Track:
    track_id: int
    position: np.ndarray                 # (3,) in body frame, metres
    covariance: np.ndarray               # (3,3)
    last_update: float
    sources: List[str] = field(default_factory=list)          # sensor labels that contributed
    measurement_ids: List[str] = field(default_factory=list)  # provenance chain
    hits: int = 1


class Tracker:
    def __init__(self, gate_m: float = 1.0, max_age_s: float = 2.0) -> None:
        self.gate_m = gate_m
        self.max_age_s = max_age_s
        self.tracks: List[Track] = []
        self._next_id = 1

    def update(self, m: Measurement, position_body: np.ndarray) -> Track:
        """Associate a positioned measurement with an existing track or start one.

        TODO(stage4): replace with KF predict/update and Mahalanobis gating.
        """
        p = np.asarray(position_body, dtype=float).reshape(3)
        best: Optional[Track] = None
        best_d = self.gate_m
        for tr in self.tracks:
            d = float(np.linalg.norm(tr.position - p))
            if d < best_d:
                best, best_d = tr, d
        if best is None:
            best = Track(self._next_id, p, np.eye(3), m.t_host)
            self._next_id += 1
            self.tracks.append(best)
        else:
            best.position = 0.5 * (best.position + p)
            best.last_update = m.t_host
            best.hits += 1
        if m.label not in best.sources:
            best.sources.append(m.label)
        best.measurement_ids.append(m.id)
        return best

    def prune(self, t_now: float) -> None:
        self.tracks = [t for t in self.tracks if t_now - t.last_update <= self.max_age_s]
