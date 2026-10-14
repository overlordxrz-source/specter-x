"""Loader + validator for specter/hw/pinmap.yaml.

Socket contract (enforced): mikroBUS socket 1 = UWB, socket 2 = GNSS,
IMU on I2C. Any violation raises PinmapError so wiring mistakes fail fast
at startup instead of silently misrouting sensors.

PyYAML is optional: CI installs only numpy/opencv/pytest, so a small
fallback parser handles this file's subset of YAML when yaml is missing.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

PINMAP_PATH = Path(__file__).resolve().parent / "pinmap.yaml"


class PinmapError(ValueError):
    pass


def _fallback_parse(text: str) -> Dict[str, Any]:
    """Minimal indent-based parser good enough for pinmap.yaml.

    Supports nested `key: value` maps via indentation; quoted strings are
    unwrapped. Not a general YAML parser — prefer PyYAML when present.
    """
    root: Dict[str, Any] = {}
    stack: list[tuple[int, Dict[str, Any]]] = [(-1, root)]
    for raw in text.splitlines():
        if not raw.strip() or raw.strip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        line = raw.strip()
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        key, val = key.strip(), val.strip()
        if (val.startswith('"') and val.endswith('"')) or (
            val.startswith("'") and val.endswith("'")
        ):
            val = val[1:-1]
        while stack and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]
        if val == "":
            child: Dict[str, Any] = {}
            parent[key] = child
            stack.append((indent, child))
        else:
            parent[key] = val
    return root


def _load_raw(path: Path = PINMAP_PATH) -> Dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(text)
        if not isinstance(data, dict):
            raise PinmapError(f"{path}: top-level mapping expected")
        return data
    except ImportError:
        return _fallback_parse(text)


@dataclass(frozen=True)
class Pinmap:
    raw: Dict[str, Any]
    board: str

    @property
    def uwb_spi(self) -> str:
        return str(self.raw["sockets"]["socket_1"]["spi"])

    @property
    def gnss_uart(self) -> str:
        return str(self.raw["sockets"]["socket_2"]["uart"])

    @property
    def imu_bus(self) -> str:
        return str(self.raw["imu"]["bus"])


def load_pinmap(path: str | Path = PINMAP_PATH) -> Pinmap:
    """Load and validate the pin map. Raises PinmapError on any violation."""
    p = Path(path)
    if not p.exists():
        raise PinmapError(f"pinmap not found: {p}")
    data = _load_raw(p)
    for key in ("board", "sockets", "imu", "constraints"):
        if key not in data:
            raise PinmapError(f"{p}: missing top-level key '{key}'")
    try:
        s1 = data["sockets"]["socket_1"]
        s2 = data["sockets"]["socket_2"]
    except (KeyError, TypeError) as e:
        raise PinmapError(f"{p}: sockets.socket_1/socket_2 required: {e}")
    if s1.get("role") != "uwb":
        raise PinmapError(f"{p}: socket_1 role must be 'uwb', got {s1.get('role')!r}")
    if s2.get("role") != "gnss":
        raise PinmapError(f"{p}: socket_2 role must be 'gnss', got {s2.get('role')!r}")
    for field in ("spi", "pins"):
        if field not in s1:
            raise PinmapError(f"{p}: socket_1 missing '{field}'")
    for field in ("uart", "pins", "protocol"):
        if field not in s2:
            raise PinmapError(f"{p}: socket_2 missing '{field}'")
    imu = data["imu"]
    if imu.get("bus") != "i2c-1":
        raise PinmapError(f"{p}: imu.bus must be 'i2c-1', got {imu.get('bus')!r}")
    if "addresses" not in imu or "pins" not in imu:
        raise PinmapError(f"{p}: imu needs 'addresses' and 'pins'")
    c = data["constraints"]
    if c.get("socket_1_role_must_be") != "uwb" or c.get("socket_2_role_must_be") != "gnss":
        raise PinmapError(f"{p}: constraints must pin socket_1=uwb, socket_2=gnss")
    if c.get("imu_bus_must_be") != "i2c-1":
        raise PinmapError(f"{p}: constraints must pin imu bus to i2c-1")
    return Pinmap(raw=data, board=str(data["board"]))
