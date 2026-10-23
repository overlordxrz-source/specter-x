"""Message authentication: HMAC-SHA256 with a shared team key.

Every datagram is `{"sig": hex, "msg": {...}}`. A rogue node without the key
cannot inject tracks — unsigned or mis-signed datagrams are dropped before
decoding. Keys are 32 random bytes, distributed out of band (never logged).

HMAC stops forgery but not replay: a captured datagram resent within the
clock window would verify. ReplayGuard closes that: every message carries a
boot id (ordered per sender boot) and a per-boot sequence number, and the
receive path accepts only a new boot id or a strictly greater seq — checked
after authentication and message validation. Residual risk (receiver restart clears the
in-memory table) is stated in the README, not hidden.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from typing import Dict, Tuple

SIG_LEN = 64  # hex chars of SHA-256


def generate_key() -> bytes:
    return secrets.token_bytes(32)


def generate_boot_id() -> str:
    """Ordered boot id: zero-padded wall-clock ns + random suffix.

    Lexicographic order matches boot order while the clock runs forward, so a
    rebooted sender's messages (new boot, seq from 1) are accepted while
    replays of the old boot sort below and are dropped by the guard.
    """
    import time as _time

    return f"{_time.time_ns():020d}-{secrets.token_hex(4)}"


def sign(message_json: str, key: bytes) -> str:
    """Wrap a message JSON string in a signed envelope JSON string."""
    message = json.loads(message_json)
    canonical = json.dumps(message, separators=(",", ":"), allow_nan=False)
    sig = hmac.new(key, canonical.encode(), hashlib.sha256).hexdigest()
    return json.dumps({"sig": sig, "msg": message}, separators=(",", ":"))


def verify(envelope_json: str, key: bytes) -> str:
    """Verify envelope; return the inner message JSON. Raises ValueError."""
    try:
        env = json.loads(envelope_json)
    except json.JSONDecodeError as e:
        raise ValueError(f"bad envelope: {e}")
    if not isinstance(env, dict) or "sig" not in env or "msg" not in env:
        raise ValueError("bad envelope: need {sig, msg}")
    inner = json.dumps(env["msg"], separators=(",", ":"))
    # NOTE: re-serialisation must be canonical (separators above) to match.
    # sign() uses the same canonical form, so this verifies.
    good = hmac.new(key, inner.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(good, str(env["sig"])):
        raise ValueError("HMAC mismatch: rogue or corrupted datagram")
    return inner


class ReplayGuard:
    """Per-sender (boot id, last seq) table against replay.

    Accept a datagram iff its boot id is strictly newer than the stored one
    (sender rebooted — adopt it) or the boot matches and seq is strictly
    greater (normal flow). Everything else — exact replays, old seq, replays
    of a superseded boot — is dropped. Fail-closed: unknown shapes are
    rejected, never admitted.
    """

    def __init__(self) -> None:
        self._last: Dict[str, Tuple[str, int]] = {}

    def check(self, unit_id: str, boot: str, seq: int) -> bool:
        if (
            not isinstance(unit_id, str)
            or not unit_id
            or not isinstance(boot, str)
            or not boot
            or type(seq) is not int
            or seq < 0
        ):
            return False
        boot = str(boot or "")
        prev = self._last.get(str(unit_id))
        if prev is None or not prev[0]:
            self._last[str(unit_id)] = (boot, seq)
            return True
        prev_boot, prev_seq = prev
        if boot != prev_boot:
            if boot > prev_boot:
                self._last[str(unit_id)] = (boot, seq)  # reboot: adopt new epoch
                return True
            return False  # superseded boot replayed: drop
        if seq > prev_seq:
            self._last[str(unit_id)] = (boot, seq)
            return True
        return False  # duplicate or out-of-order old seq: drop
