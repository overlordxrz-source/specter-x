"""Append-only JSONL event log. One file per session in events/sessions/.

Each line: {"t_host", "session", "seq", "event", "detail", "measurement"?}
where "measurement" is a full Measurement dict (provenance included).
"""

from __future__ import annotations

import json
import os
import re
import time
import uuid
from collections import deque
from pathlib import Path
from typing import Deque, Optional

from specter.fusion.measurement import Measurement


class EventLog:
    def __init__(
        self, directory: str | os.PathLike, session: Optional[str] = None
    ) -> None:
        self.dir = Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        self.session = session or f"{stamp}-{uuid.uuid4().hex[:6]}"
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", self.session):
            raise ValueError("session must be a simple local identifier")
        self.path = self.dir / f"{self.session}.jsonl"
        # Sessions are immutable identities; resuming needs a separate protocol.
        self._f = open(self.path, "x", buffering=1, encoding="utf-8")
        self._seq = 0
        self.recent: Deque[str] = deque(maxlen=6)  # for the HUD ticker
        self.counts: dict = {}

    def log(
        self,
        event: str,
        detail: Optional[dict] = None,
        measurement: Optional[Measurement] = None,
    ) -> dict:
        rec = {
            "t_host": time.time(),
            "session": self.session,
            "seq": self._seq + 1,
            "event": event,
            "detail": detail or {},
        }
        if measurement is not None:
            rec["measurement"] = measurement.to_dict()
        encoded = json.dumps(rec, separators=(",", ":"), allow_nan=False)
        self._f.write(encoded + "\n")
        self._seq += 1
        self.counts[event] = self.counts.get(event, 0) + 1
        tag = ""
        if measurement is not None:
            c = (
                ""
                if measurement.confidence is None
                else f" {measurement.confidence:.2f}"
            )
            tag = f" {measurement.label}{c}"
        self.recent.append(time.strftime("%H:%M:%S") + f" {event}{tag}")
        return rec

    def close(self) -> None:
        if not self._f.closed:
            self._f.close()


class PresenceMonitor:
    """Hysteresis on per-frame detections -> 'acquired' / 'lost' events.

    acquired after `on_frames` consecutive frames with a detection,
    lost after `off_frames` consecutive frames without one.
    """

    def __init__(self, name: str, log: EventLog, on_frames: int = 3, off_frames: int = 5) -> None:
        self.name, self.log = name, log
        self.on_frames, self.off_frames = on_frames, off_frames
        self.active = False
        self._hit = 0
        self._miss = 0
        self.last: Optional[Measurement] = None

    def update(self, best: Optional[Measurement], frame_index: int) -> Optional[str]:
        if best is not None:
            self._hit += 1
            self._miss = 0
            self.last = best
            if not self.active and self._hit >= self.on_frames:
                self.active = True
                self.log.log(f"{self.name}_acquired", {"frame_index": frame_index}, best)
                return "acquired"
        else:
            self._miss += 1
            self._hit = 0
            if self.active and self._miss >= self.off_frames:
                self.active = False
                self.log.log(f"{self.name}_lost",
                             {"frame_index": frame_index, "frames_missing": self._miss},
                             self.last)
                return "lost"
        return None
