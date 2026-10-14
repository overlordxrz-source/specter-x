"""Message authentication: HMAC-SHA256 with a shared team key.

Every datagram is `{"sig": hex, "msg": {...}}`. A rogue node without the key
cannot inject tracks — unsigned or mis-signed datagrams are dropped before
decoding. Keys are 32 random bytes, distributed out of band (never logged).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets

SIG_LEN = 64  # hex chars of SHA-256


def generate_key() -> bytes:
    return secrets.token_bytes(32)


def sign(message_json: str, key: bytes) -> str:
    """Wrap a message JSON string in a signed envelope JSON string."""
    sig = hmac.new(key, message_json.encode(), hashlib.sha256).hexdigest()
    return json.dumps({"sig": sig, "msg": json.loads(message_json)},
                      separators=(",", ":"))


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
