"""Parse the firmware's own status line.

The controlled-link firmware emits one ``SPECTER_STAT`` line a second, from
the device, about the device:

    SPECTER_STAT,role=softap,peer=b8:62:1f:e5:ac:62,ch=6,rssi=-62,
    csi_cb=1200,printed=1180,drop_old=0,drop_new=0,q=2,q_high=7

It is deliberately **not** the supervisor protocol (``HELLO``/``STAT``/
``HB``, checkpoint 003): that protocol is a separate piece of work, and a
host must never confuse device health with supervisor telemetry. Different
tag, different meaning.

``csi_cb`` is the capability probe. In the SoftAP role it is the number of
times the CSI callback fired at all, so a value that stays at zero while a
station is associated and sending is the answer to "does the ESP32-S3 do
AP-side CSI".
"""
from __future__ import annotations

from typing import Dict, Optional

TAG = "SPECTER_STAT"

#: the numeric fields, by the name the firmware prints. ``ch`` and ``q`` are
#: aliases the firmware uses for channel and queue depth.
_INT_FIELDS = {
    "ch": "channel",
    "rssi": "rssi",
    "csi_cb": "csi_callbacks",
    "printed": "printed",
    "drop_old": "dropped_old",
    "drop_new": "dropped_new",
    "q": "queue_depth",
    "q_high": "queue_high",
}
_STR_FIELDS = {"role": "role", "peer": "peer"}


def parse_status_line(line: str) -> Optional[Dict[str, object]]:
    """Parse one ``SPECTER_STAT`` line, or return None if it is not one.

    A malformed numeric field is skipped rather than guessed at: a status
    line that cannot be trusted must not produce a confident number.
    """
    text = (line or "").strip()
    if not text.upper().startswith(TAG + ","):
        return None
    out: Dict[str, object] = {}
    for part in text.split(",")[1:]:
        key, sep, value = part.partition("=")
        if not sep:
            continue
        key = key.strip()
        value = value.strip()
        if key in _STR_FIELDS:
            out[_STR_FIELDS[key]] = value
        elif key in _INT_FIELDS:
            try:
                out[_INT_FIELDS[key]] = int(value, 10)
            except ValueError:
                return None
    if "csi_callbacks" not in out:
        return None
    return out
