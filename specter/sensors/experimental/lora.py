"""EXPERIMENTAL: LoRa mesh fallback (Meshtastic-compatible) for heartbeats + man-down.

When Wi-Fi drops, units fall back to a low-rate LoRa link carrying only
heartbeats and man-down alerts — never tracks or video. This stub defines
the compact over-the-air encoding (fits a <200 B mesh payload) + round-trip.
Real radio driver lands with hardware; the frustration budget does not.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

EXPERIMENTAL = True
SENSOR = "lora"
MTU = 200


def encode_heartbeat(unit_id: str, seq: int, mode: str, rmse: float) -> bytes:
    payload = {"t": "hb", "u": unit_id[:12], "s": seq, "m": mode, "r": round(rmse, 1)}
    raw = json.dumps(payload, separators=(",", ":")).encode()
    if len(raw) > MTU:
        raise ValueError(f"heartbeat {len(raw)}B exceeds {MTU}B LoRa MTU")
    return raw


def encode_mandown(unit_id: str, seq: int, reason: str) -> bytes:
    payload = {"t": "md", "u": unit_id[:12], "s": seq, "why": reason[:24],
               "ts": int(time.time())}
    raw = json.dumps(payload, separators=(",", ":")).encode()
    if len(raw) > MTU:
        raise ValueError(f"man-down {len(raw)}B exceeds {MTU}B LoRa MTU")
    return raw


def decode_packet(raw: bytes) -> Dict[str, Any]:
    try:
        d = json.loads(bytes(raw).decode())
    except (ValueError, UnicodeDecodeError) as e:
        raise ValueError(f"bad LoRa packet: {e}")
    if not isinstance(d, dict) or d.get("t") not in ("hb", "md"):
        raise ValueError(f"unknown LoRa packet: {d!r}")
    return d


@dataclass
class LoRaFallback:
    unit_id: str = "unit-1"
    _seq: int = 0

    def heartbeat(self, mode: str = "REL", rmse: float = 99.0) -> bytes:
        self._seq += 1
        return encode_heartbeat(self.unit_id, self._seq, mode, rmse)

    def mandown(self, reason: str) -> bytes:
        self._seq += 1
        return encode_mandown(self.unit_id, self._seq, reason)

    def try_open_hardware(self) -> bool:
        return False  # radio not on the bench yet
