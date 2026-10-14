"""u-blox NEO-M9N GNSS driver (GNSS 7 Click, MIKROE-3922).

Primary: UBX-NAV-PVT (class 0x01, id 0x07). Optional pyubx2 is used when
installed; otherwise a dependency-free internal parser handles the same
message. NMEA GGA is a fallback for fix + hAcc estimate only.

Every fix is emitted as a Measurement(kind="gnss_fix", frame "wgs84") with
hAcc/vAcc converted to a 3x3 covariance in m^2 (diagonal). No position is
ever emitted without its accuracy: fix_type 0 (no fix) yields confidence 0
and a large covariance, never a fake-precise point.
"""
from __future__ import annotations

import struct
import time
from dataclasses import dataclass, field
from typing import List, Optional, Sequence

from specter.fusion.measurement import Measurement, Provenance

SENSOR = "gnss"
FRAME = "wgs84"
ALGORITHM_UBX = "ubx-nav-pvt"
ALGORITHM_NMEA = "nmea-gga"

UBX_SYNC = b"\xb5\x62"
NAV_PVT_CLS, NAV_PVT_ID = 0x01, 0x07
NAV_PVT_LEN = 92

FIX_LABELS = {
    0: "NO_FIX",
    1: "DR_ONLY",
    2: "FIX_2D",
    3: "FIX_3D",
    4: "GNSS_DR",
    5: "TIME_ONLY",
}

# struct of UBX-NAV-PVT payload (little-endian, u-blox spec). Packed by
# explicit offsets (total 92 bytes) — see field table in build_nav_pvt.
_OFF = {
    "tow": (0, "<I"), "year": (4, "<H"),
    "month": (6, "<B"), "day": (7, "<B"), "hour": (8, "<B"),
    "minute": (9, "<B"), "sec": (10, "<B"), "valid": (11, "<B"),
    "t_acc": (12, "<I"), "nano": (16, "<i"),
    "fix": (20, "<B"), "flags": (21, "<B"), "flags2": (22, "<B"),
    "num_sv": (23, "<B"),
    "lon": (24, "<i"), "lat": (28, "<i"), "height": (32, "<i"),
    "h_msl": (36, "<i"), "h_acc": (40, "<I"), "v_acc": (44, "<I"),
}


def ubx_checksum(cls: int, mid: int, payload: bytes) -> bytes:
    ck_a = ck_b = 0
    for b in bytes([cls, mid]) + struct.pack("<H", len(payload)) + payload:
        ck_a = (ck_a + b) & 0xFF
        ck_b = (ck_b + b) & 0xFF
    return bytes([ck_a, ck_b])


def build_nav_pvt(
    *,
    lon_deg: float = 0.0,
    lat_deg: float = 0.0,
    height_m: float = 0.0,
    h_acc_mm: int = 5000,
    v_acc_mm: int = 8000,
    fix_type: int = 3,
    num_sv: int = 12,
    tow_ms: int = 0,
) -> bytes:
    """Build a synthetic UBX-NAV-PVT frame (for tests / simulators)."""
    p = bytearray(NAV_PVT_LEN)
    struct.pack_into("<I", p, 0, tow_ms & 0xFFFFFFFF)
    struct.pack_into("<H", p, 4, 2026)
    struct.pack_into("<BBBBBB", p, 6, 10, 14, 12, 0, 0, 1)
    struct.pack_into("<B", p, 11, 1)  # valid flags
    struct.pack_into("<B", p, 20, fix_type)
    struct.pack_into("<B", p, 23, num_sv)
    struct.pack_into("<i", p, 24, int(round(lon_deg * 1e7)))
    struct.pack_into("<i", p, 28, int(round(lat_deg * 1e7)))
    h_mm = int(round(height_m * 1000))
    struct.pack_into("<i", p, 32, h_mm)
    struct.pack_into("<i", p, 36, h_mm)
    struct.pack_into("<I", p, 40, h_acc_mm)
    struct.pack_into("<I", p, 44, v_acc_mm)
    payload = bytes(p)
    header = UBX_SYNC + bytes([NAV_PVT_CLS, NAV_PVT_ID]) + struct.pack("<H", len(payload))
    return header + payload + ubx_checksum(NAV_PVT_CLS, NAV_PVT_ID, payload)


def parse_nav_pvt(payload: bytes) -> dict:
    """Parse a 92-byte UBX-NAV-PVT payload into plain fields."""
    if len(payload) != NAV_PVT_LEN:
        raise ValueError(f"NAV-PVT payload must be {NAV_PVT_LEN} bytes, got {len(payload)}")
    g = lambda off, fmt: struct.unpack_from(fmt, payload, off)[0]
    fix = g(20, "<B")
    return {
        "tow_ms": g(0, "<I"),
        "fix_type": fix,
        "fix_label": FIX_LABELS.get(fix, f"UNKNOWN_{fix}"),
        "num_sv": g(23, "<B"),
        "lon_deg": g(24, "<i") / 1e7,
        "lat_deg": g(28, "<i") / 1e7,
        "height_m": g(32, "<i") / 1000.0,
        "h_acc_m": g(40, "<I") / 1000.0,
        "v_acc_m": g(44, "<I") / 1000.0,
    }


def pvt_to_measurement(
    pvt: dict,
    *,
    sensor_id: str = "neom9n-0",
    t_host: Optional[float] = None,
    t_sensor: Optional[float] = None,
    algorithm: str = ALGORITHM_UBX,
    sim: bool = False,
) -> Measurement:
    """PVT dict -> provenance-first Measurement in frame wgs84."""
    h, v = max(float(pvt["h_acc_m"]), 1e-3), max(float(pvt["v_acc_m"]), 1e-3)
    fix = int(pvt["fix_type"])
    no_fix = fix == 0
    # No-fix: keep coordinates but covariance huge + confidence 0 — never fake precision.
    cov = (
        [[2500.0, 0, 0], [0, 2500.0, 0], [0, 0, 10000.0]]
        if no_fix
        else [[h * h, 0, 0], [0, h * h, 0], [0, 0, v * v]]
    )
    conf = 0.0 if no_fix else (0.95 if fix == 3 else 0.6)
    if sim:
        conf = min(conf, 0.9)
    return Measurement(
        sensor=SENSOR,
        kind="gnss_fix",
        t_host=t_host if t_host is not None else time.time(),
        t_sensor=t_sensor if t_sensor is not None else pvt.get("tow_ms", 0) / 1000.0,
        frame_id=FRAME,
        value={
            "lat_deg": float(pvt["lat_deg"]),
            "lon_deg": float(pvt["lon_deg"]),
            "alt_m": float(pvt["height_m"]),
            "fix_type": fix,
            "fix_label": pvt.get("fix_label", FIX_LABELS.get(fix, "?")),
            "num_sv": int(pvt["num_sv"]),
            "h_acc_m": float(pvt["h_acc_m"]),
            "v_acc_m": float(pvt["v_acc_m"]),
            "sim": bool(sim),
        },
        confidence=conf,
        covariance=cov,
        provenance=Provenance(
            sensor_id=sensor_id,
            source=SENSOR,
            algorithm=algorithm + ("-sim" if sim else ""),
            frame_index=None,
        ),
    )


def parse_nmea_gga(line: str) -> Optional[dict]:
    """Minimal $GxGGA parser -> {lat, lon, alt, fix, sats, hdop}. None if unusable."""
    s = line.strip()
    if "GGA" not in s:
        return None
    body = s.split("*")[0]
    p = body.split(",")
    if len(p) < 10:
        return None
    try:
        fix = int(p[6] or 0)
        lat_raw, lat_h, lon_raw, lon_h = p[2], p[3], p[4], p[5]
        if not lat_raw or not lon_raw:
            return None
        lat = int(float(lat_raw) // 100) + (float(lat_raw) % 100) / 60.0
        lon = int(float(lon_raw) // 100) + (float(lon_raw) % 100) / 60.0
        if lat_h == "S":
            lat = -lat
        if lon_h == "W":
            lon = -lon
        alt = float(p[9] or 0.0)
        sats = int(p[7] or 0)
        hdop = float(p[8] or 9.9)
    except ValueError:
        return None
    # hdop -> rough horizontal accuracy; honest: mark as estimate.
    return {
        "lat_deg": lat, "lon_deg": lon, "height_m": alt,
        "fix_type": 3 if fix >= 1 else 0,
        "fix_label": ("FIX_3D" if fix >= 1 else "NO_FIX") + "+NMEA-EST",
        "num_sv": sats, "h_acc_m": max(hdop * 4.0, 2.5), "v_acc_m": max(hdop * 6.0, 4.0),
    }


@dataclass
class Neom9nDriver:
    """Host-side NEO-M9N driver: feed() UBX bytes or NMEA lines, get Measurements.

    Hardware path (UART /dev/serial0 @38400, or I2C 0x42) is opened lazily via
    open_serial() so imports and CI never touch hardware.
    """

    sensor_id: str = "neom9n-0"
    has_time_pulse: bool = False  # True only when PPS is wired to GPIO18
    _buf: bytearray = field(default_factory=bytearray, repr=False)
    _frame_index: int = 0

    def feed(self, chunk: bytes) -> List[Measurement]:
        """Consume raw UBX stream bytes; return 0+ Measurements."""
        self._buf += chunk
        out: List[Measurement] = []
        while True:
            i = self._buf.find(UBX_SYNC)
            if i < 0:
                self._buf.clear()
                break
            if i > 0:
                del self._buf[:i]
            if len(self._buf) < 6:
                break
            cls, mid = self._buf[2], self._buf[3]
            ln = struct.unpack_from("<H", self._buf, 4)[0]
            if len(self._buf) < 6 + ln + 2:
                break
            payload = bytes(self._buf[6 : 6 + ln])
            cksum = bytes(self._buf[6 + ln : 8 + ln])
            del self._buf[: 8 + ln]
            if cksum != ubx_checksum(cls, mid, payload):
                continue  # corrupt frame: drop, keep sync
            if (cls, mid) == (NAV_PVT_CLS, NAV_PVT_ID) and ln == NAV_PVT_LEN:
                self._frame_index += 1
                pvt = parse_nav_pvt(payload)
                m = pvt_to_measurement(pvt, sensor_id=self.sensor_id)
                # stamp frame index into a fresh provenance (frozen dataclass)
                object.__setattr__(m, "provenance", Provenance(
                    sensor_id=self.sensor_id, source=SENSOR,
                    algorithm=ALGORITHM_UBX, frame_index=self._frame_index))
                out.append(m)
        return out

    def feed_nmea(self, line: str) -> Optional[Measurement]:
        p = parse_nmea_gga(line)
        if p is None:
            return None
        self._frame_index += 1
        m = pvt_to_measurement(p, sensor_id=self.sensor_id, algorithm=ALGORITHM_NMEA)
        object.__setattr__(m, "provenance", Provenance(
            sensor_id=self.sensor_id, source=SENSOR,
            algorithm=ALGORITHM_NMEA, frame_index=self._frame_index))
        return m


@dataclass
class SyntheticGnss:
    """CI synthetic GNSS: walks a straight line, UBX-accurate covariances, SIM-labelled."""

    sensor_id: str = "neom9n-sim"
    lat0: float = 47.3769
    lon0: float = 8.5417
    speed_m_s: float = 1.2
    h_acc_m: float = 2.5
    v_acc_m: float = 4.0
    _i: int = 0

    def read(self, dt: float = 0.2) -> Measurement:
        self._i += 1
        # ~1e-5 deg lat ~= 1.11 m; walk north.
        lat = self.lat0 + self._i * dt * self.speed_m_s / 111320.0
        payload = build_nav_pvt(
            lon_deg=self.lon0, lat_deg=lat, height_m=400.0,
            h_acc_mm=int(self.h_acc_m * 1000), v_acc_mm=int(self.v_acc_m * 1000),
            fix_type=3, num_sv=14, tow_ms=self._i * int(dt * 1000),
        )
        pvt = parse_nav_pvt(payload[6 : 6 + NAV_PVT_LEN])
        m = pvt_to_measurement(pvt, sensor_id=self.sensor_id, sim=True)
        object.__setattr__(m, "provenance", Provenance(
            sensor_id=self.sensor_id, source=SENSOR,
            algorithm=ALGORITHM_UBX + "-sim", frame_index=self._i))
        return m

    def read_many(self, n: int, dt: float = 0.2) -> Sequence[Measurement]:
        return [self.read(dt) for _ in range(n)]
