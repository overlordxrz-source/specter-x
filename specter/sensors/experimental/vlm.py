"""EXPERIMENTAL: on-device VLM on the Raspberry Pi AI HAT+ 2 (Hailo-10H).

40 TOPS INT4, 8 GB RAM, runs ~1.5–6B VLMs: turns fused team tracks into
short spoken/written reports ("2 people, room NE, one not moving").
Rule: LLM output must cite Measurement ids, and the HUD marks it AI-SUMMARY
— never a bare claim. No model runs here; summarize_tracks() is the
deterministic template the VLM prompt must match in CI.
"""
from __future__ import annotations

import time
from typing import List, Sequence

import numpy as np

from specter.fusion.measurement import Measurement, Provenance

EXPERIMENTAL = True
SENSOR = "vlm"
FRAME = "team"
ALGORITHM = "vlm-summary-tmpl-v1"


def summarize_tracks(tracks: Sequence[object], *,
                     sensor_id: str = "hailo10h-0",
                     sim: bool = True) -> Measurement:
    """Template summary over objects with .position/.contributors/.measurement_ids.

    Returns Measurement(kind="ai_summary") whose text cites every Measurement
    id it used. Empty input yields an explicit no-contact statement, never
    silence dressed as certainty.
    """
    ids: List[str] = []
    parts: List[str] = []
    for t in tracks:
        mids = list(getattr(t, "measurement_ids", []))
        ids.extend(mids)
        pos = np.asarray(getattr(t, "position", [0, 0, 0]), float).reshape(3)
        dist = float(np.linalg.norm(pos[:2]))
        brg = "N" if pos[1] >= abs(pos[0]) else ("S" if -pos[1] >= abs(pos[0])
              else ("E" if pos[0] > 0 else "W"))
        contrib = ",".join(u for u, _ in getattr(t, "contributors", [("?", "?")]))
        parts.append(f"{getattr(t, 'label', 'contact')} {brg} ~{dist:.0f}m [{contrib}]")
    if parts:
        text = f"{len(parts)} contact(s): " + "; ".join(parts)
    else:
        text = "no contacts on the team picture."
    cited = " cites: " + ",".join(ids) if ids else " (no measurements)"
    return Measurement(
        sensor=SENSOR,
        kind="ai_summary",
        t_host=time.time(),
        frame_id=FRAME,
        value={"text": text + cited, "cited_ids": ids, "sim": bool(sim)},
        confidence=0.3,
        covariance=np.array([[1.0]]),
        provenance=Provenance(
            sensor_id=sensor_id, source=SENSOR, algorithm=ALGORITHM,
            parents=tuple(ids),
            notes="EXPERIMENTAL AI-SUMMARY: template stand-in, verify against display",
        ),
    )
