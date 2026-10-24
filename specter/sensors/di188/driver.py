"""DATAQ DI-188 USB DAQ driver (CDC-ACM, documented ASCII protocol).

The DI-188 is an open-source firmware project (dataq-instruments/Arduino_WinDaq).
It always enumerates as a USB CDC-ACM device, so on macOS it appears as a plain
serial node (``/dev/cu.usbmodemXXXX``) with **no driver, kext or libusb needed**.

This driver speaks only the published command protocol
(https://www.dataq.com/resources/pdfs/misc/di-188-protocol.pdf). It never
flashes firmware and never touches drivers.

Protocol rules that matter and are easy to get wrong:

* Commands are ASCII and **must be terminated with CR (0x0D)**; arguments are
  separated by a single space.
* The instrument **echoes every character you type while it is not scanning**.
  Responses therefore arrive prefixed by the echoed command.
* Echo stops while scanning, so ``start`` produces no echo but ``stop`` does.
* The command buffer is small: never send a new command before draining the
  previous echo.

Provenance: :class:`DI188Identity` and :class:`DeviceCalibration` describe
exactly which instrument and which calibration basis produced a number, so the
HUD can label it.
"""

from __future__ import annotations

import glob
import re
import time
from dataclasses import dataclass, field
from typing import Dict, Iterator, List, Optional, Sequence

try:
    import serial
except ImportError:  # pyserial is only needed to talk to a real instrument
    serial = None  # type: ignore[assignment]


# --- device flash struct (dqCal_type in dqwindaq.h) ------------------------

_FLASH_STRUCT_REV = 0
_FLASH_HW_REV = 2
_FLASH_KEY = 4            # char key[32]
_FLASH_SERIAL = 36        # char serial_n[16]
_FLASH_CAL_DATE = 52      # char lastCalDate[16]
_FLASH_SCALE = 68         # short adc_scale[8][4]
_FLASH_OFFSET = 132       # short adc_offset[8][4]
_FLASH_LEN = 196

#: Device ADC scale that marks the DI-188 +/-10 V analog front end.
SCALE_DI188_PM10V = 18850
#: Device ADC scale that marks a bare Seeed XIAO M0 (0-3.3 V ADC inputs).
SCALE_XIAO_0_3V3 = 16384


class DI188Error(RuntimeError):
    """Raised when the instrument misbehaves or the link drops."""


@dataclass
class DI188Identity:
    """Who is on the other end of the serial port."""

    port: str = ""
    usb_product: str = ""
    usb_vendor: str = ""
    usb_vid: Optional[int] = None
    usb_pid: Optional[int] = None
    usb_serial: str = ""
    model: str = ""            # protocol model, e.g. "188"
    vendor_tag: str = ""       # "DATAQ"
    firmware_rev: str = ""
    hardware_rev: str = ""
    serial_number: str = ""
    channel_count: int = 0

    @property
    def model_name(self) -> str:
        return f"DI-{self.model}" if self.model else "DI-188 (unknown model)"

    def as_dict(self) -> Dict:
        return {
            "port": self.port,
            "usb_product": self.usb_product,
            "usb_vendor": self.usb_vendor,
            "usb_vid": self.usb_vid,
            "usb_pid": self.usb_pid,
            "usb_serial": self.usb_serial,
            "model": self.model,
            "model_name": self.model_name,
            "vendor_tag": self.vendor_tag,
            "firmware_rev": self.firmware_rev,
            "hardware_rev": self.hardware_rev,
            "serial_number": self.serial_number,
            "channel_count": self.channel_count,
        }


@dataclass
class DeviceCalibration:
    """The instrument's own digital calibration, read from its flash.

    The firmware applies ``adc_scale``/``adc_offset`` to every sample before
    it reaches us, so the counts we receive are already offset-corrected and
    scaled. What is *not* known is how many volts one count represents - that
    needs a real reference source (see :mod:`.calibration`).
    """

    struct_rev: int = 0
    hardware_rev: int = 0
    key: str = ""
    serial_number: str = ""
    last_cal_date: str = ""
    scale: List[List[int]] = field(default_factory=list)
    offset: List[List[int]] = field(default_factory=list)
    read_ok: bool = False

    def channel_scale(self, ch: int) -> Optional[int]:
        if 0 <= ch < len(self.scale) and self.scale[ch]:
            return self.scale[ch][0]
        return None

    def channel_offset(self, ch: int) -> Optional[int]:
        if 0 <= ch < len(self.offset) and self.offset[ch]:
            return self.offset[ch][0]
        return None

    @property
    def profile(self) -> str:
        """Front-end profile implied by the device's ADC scale constant."""
        sc = self.channel_scale(0)
        if sc == SCALE_DI188_PM10V:
            return "di188_pm10v"
        if sc == SCALE_XIAO_0_3V3:
            return "xiao_0_3v3"
        return "unknown"

    def as_dict(self) -> Dict:
        return {
            "read_ok": self.read_ok,
            "struct_rev": self.struct_rev,
            "hardware_rev": self.hardware_rev,
            "key": self.key,
            "serial_number": self.serial_number,
            "last_cal_date": self.last_cal_date,
            "profile": self.profile,
            "scale": [list(r) for r in self.scale],
            "offset": [list(r) for r in self.offset],
        }


@dataclass
class Sample:
    """One scan-list frame: one value per enabled channel."""

    t: float                 # host monotonic seconds since stream start
    index: int               # frame counter since stream start
    values: List[int]        # device counts, already device-calibrated
    host_time: float = 0.0   # wall-clock time.time()

    def as_list(self) -> List[float]:
        return [float(v) for v in self.values]


def find_serial_ports() -> List[str]:
    """Candidate CDC-ACM nodes, on macOS and Linux.

    The instrument has been exercised on macOS only, but the discovery is
    not macOS-specific: Linux exposes CDC-ACM devices as ``/dev/ttyACM*`` and
    offers stable ``/dev/serial/by-id`` names, which are preferred because
    they survive re-plugging.
    """
    out: List[str] = []
    out.extend(sorted(glob.glob("/dev/serial/by-id/*")))
    for pattern in ("/dev/cu.usbmodem*", "/dev/cu.usbserial*", "/dev/cu.SLAB_USBtoUART*",
                    "/dev/cu.usb-FTDI*", "/dev/cu.wchusbserial*", "/dev/tty.usbmodem*",
                    "/dev/ttyACM*", "/dev/ttyUSB*"):
        out.extend(sorted(glob.glob(pattern)))
    seen, uniq = set(), []
    for p in out:
        if p not in seen:
            seen.add(p)
            uniq.append(p)
    return uniq


def usb_identity_for_port(port: str) -> Dict:
    """Best-effort USB descriptor lookup for a serial node (macOS/ioreg)."""
    info: Dict = {"usb_product": "", "usb_vendor": "", "usb_vid": None,
                  "usb_pid": None, "usb_serial": ""}
    try:
        import plistlib
        import subprocess
        raw = subprocess.run(["ioreg", "-p", "IOUSB", "-a", "-l"], capture_output=True,
                             text=True, timeout=15).stdout
        data = plistlib.loads(raw.encode())
    except Exception:
        return info

    nodes: List[Dict] = []

    def walk(node):
        if not isinstance(node, dict):
            return
        if "idVendor" in node and "idProduct" in node:
            nodes.append(node)
        for key in ("IORegistryEntryChildren", "IORegistryEntryParent"):
            child = node.get(key)
            if isinstance(child, dict):
                walk(child)
            elif isinstance(child, list):
                for c in child:
                    walk(c)

    # `ioreg -a` returns either the root dict or a list of roots
    if isinstance(data, dict):
        walk(data)
    elif isinstance(data, list):
        for entry in data:
            walk(entry)

    for n in nodes:
        info["usb_product"] = n.get("USB Product Name") or n.get("kUSBProductString") or ""
        info["usb_vendor"] = n.get("USB Vendor Name") or n.get("kUSBVendorString") or ""
        info["usb_vid"] = n.get("idVendor")
        info["usb_pid"] = n.get("idProduct")
        info["usb_serial"] = n.get("USB Serial Number") or ""
        if info["usb_product"]:
            return info
    return info


class DI188Driver:
    """Serial driver for one DI-188 (or DI-188-protocol) instrument."""

    def __init__(self, port: Optional[str] = None, baud: int = 115200, timeout: float = 1.0):
        self.port = port or self.default_port()
        self.baud = baud          # placeholder: CDC-ACM ignores the line rate
        self.timeout = timeout
        self.ser = None
        self.identity = DI188Identity(port=self.port)
        self.device_calibration = DeviceCalibration()
        self._streaming = False
        self.malformed_lines = 0
        # The instrument echoes typed characters while idle. `start` is typed
        # while idle, so its echo ("start", no CR) lands in the input buffer
        # just before the first data frame. It must be skipped, not parsed.
        self._pending_echo = b""

    # -- lifecycle ---------------------------------------------------------

    @staticmethod
    def default_port() -> str:
        ports = find_serial_ports()
        if not ports:
            raise DI188Error(
                "No DI-188 serial node found. Looked for /dev/cu.usbmodem* and "
                "/dev/cu.usbserial*. Is the device plugged in?")
        return ports[0]

    def open(self) -> "DI188Driver":
        if self.ser is not None:
            return self
        if serial is None:
            raise DI188Error(
                "pyserial is required to talk to a DI-188: pip install pyserial")
        try:
            self.ser = serial.Serial(self.port, baudrate=self.baud, timeout=self.timeout)
        except Exception as exc:
            raise DI188Error(f"cannot open {self.port}: {exc}") from exc
        self.identity = DI188Identity(port=self.port)
        for key, value in usb_identity_for_port(self.port).items():
            setattr(self.identity, key, value)
        return self

    def close(self) -> None:
        if self.ser is None:
            return
        try:
            if self._streaming:
                self.stop()
        except Exception:
            pass
        try:
            self.ser.close()
        finally:
            self.ser = None
            self._streaming = False

    def __enter__(self):
        return self.open()

    def __exit__(self, *exc):
        self.close()
        return False

    # -- low level ---------------------------------------------------------

    def _require(self):
        if self.ser is None:
            raise DI188Error("driver is not open")
        return self.ser

    def _read_available(self) -> bytes:
        """Read whatever is already buffered, without blocking.

        ``Serial.read(n)`` waits for n bytes or for the full port timeout, so
        asking for more than has arrived blocks for a whole second. Only ever
        asking for what is buffered keeps every read non-blocking.
        """
        s = self._require()
        waiting = s.in_waiting
        if not waiting:
            return b""
        return s.read(waiting)

    def _drain(self, seconds: float, stop_when=None) -> bytes:
        """Read for up to ``seconds``.

        ``stop_when`` is called with the accumulated bytes and lets a caller
        finish early once it has everything it needs - the instrument answers
        in milliseconds, so waiting out the full timeout is wasted time.
        """
        end = time.time() + seconds
        buf = bytearray()
        while time.time() < end:
            chunk = self._read_available()
            if chunk:
                buf += chunk
                if stop_when is not None and stop_when(bytes(buf)):
                    break
            else:
                time.sleep(0.002)
        return bytes(buf)

    def command(self, cmd: str, wait: float = 0.6, echo: bool = True) -> str:
        """Send one command and return the response body (echo removed).

        The instrument echoes every typed character while idle, so the echo is
        stripped here. While scanning, the instrument does not echo and
        ``echo`` must be False.

        The reply is read until it is *complete* rather than for a fixed
        window: the instrument terminates a response with CR, and the bare
        ``stop`` reply has no terminator at all, so a few milliseconds of
        silence also ends the reply. That is both faster and far less flaky
        than guessing a timeout.
        """
        s = self._require()
        s.reset_input_buffer()
        s.write((cmd + "\r\n").encode())
        s.flush()
        deadline = time.time() + wait
        buf = b""
        idle = 0
        while time.time() < deadline:
            chunk = self._read_available()
            if chunk:
                buf += chunk
                idle = 0
                if b"\r" in buf:
                    break
            else:
                idle += 1
                if buf and idle >= 3:
                    break
                time.sleep(0.002)
        raw = buf.decode("utf-8", "replace")
        if echo:
            # The instrument echoes every typed character (except the CR) as
            # they arrive, so the raw reply starts with the command text and
            # the response follows it. The echoed LF lands *after* the
            # response, so the prefix to strip is the bare command.
            if raw.startswith(cmd):
                raw = raw[len(cmd):]
        return raw.strip()

    # -- identity ----------------------------------------------------------

    def read_identity(self) -> DI188Identity:
        """Query the instrument identity (read-only commands only)."""
        ident = self.identity

        def once(cmd: str) -> str:
            for _ in range(3):
                body = self.command(cmd, wait=0.3)
                if body:
                    return body.split()[-1]
            return ""

        ident.vendor_tag = once("info 0")
        ident.model = once("info 1")
        ident.firmware_rev = once("info 2")
        ident.hardware_rev = once("info 3")
        ident.serial_number = once("info 6")
        chan = once("rchn")
        ident.channel_count = int(chan) if chan.isdigit() else 0
        return ident

    # -- device flash calibration -----------------------------------------

    def read_device_calibration(self) -> DeviceCalibration:
        """Read the instrument's own calibration block (read-only).

        Uses ``readflash``, which dumps the in-memory calibration struct as
        decimal bytes. ``writeflash`` is never used.
        """
        s = self._require()
        s.reset_input_buffer()
        s.write(b"readflash\r\n")
        s.flush()
        raw = self._drain(
            2.5,
            stop_when=lambda b: len(re.findall(r"-?\d+", b.decode("utf-8", "replace")))
            >= _FLASH_LEN,
        ).decode("utf-8", "replace")
        if raw.startswith("readflash"):
            raw = raw[len("readflash"):]
        nums = [int(x) for x in re.findall(r"-?\d+", raw)]
        if len(nums) < _FLASH_LEN:
            raise DI188Error(f"readflash returned {len(nums)} bytes, expected {_FLASH_LEN}")
        b = nums[:_FLASH_LEN]

        def s16(lo: int) -> int:
            v = b[lo] | (b[lo + 1] << 8)
            return v - 65536 if v >= 32768 else v

        def cstr(start: int, n: int) -> str:
            return bytes(b[start:start + n]).split(b"\x00")[0].decode("latin1", "replace")

        cal = DeviceCalibration(
            struct_rev=s16(_FLASH_STRUCT_REV),
            hardware_rev=s16(_FLASH_HW_REV),
            key=cstr(_FLASH_KEY, 32),
            serial_number=cstr(_FLASH_SERIAL, 16),
            last_cal_date=cstr(_FLASH_CAL_DATE, 16),
            scale=[[s16(_FLASH_SCALE + ch * 8 + j * 2) for j in range(4)] for ch in range(8)],
            offset=[[s16(_FLASH_OFFSET + ch * 8 + j * 2) for j in range(4)] for ch in range(8)],
            read_ok=True,
        )
        self.device_calibration = cal
        return cal

    # -- acquisition setup -------------------------------------------------

    def stop(self) -> None:
        try:
            s = self._require()
            s.write(b"stop\r\n")
            s.flush()
            self._drain(0.15)
        finally:
            self._streaming = False

    def configure(self, channels: Sequence[int], rate: float = 100.0) -> float:
        """Set up the scan list and sample rate. Returns the realised rate."""
        if not channels:
            raise DI188Error("no channels requested")
        self.stop()
        self.command("eol 0", wait=0.12)        # CR terminator
        self.command("encode 1", wait=0.12)     # ASCII output mode
        self.command(f"slist 0 {channels[0]}", wait=0.12)
        for pos, ch in enumerate(channels[1:], start=1):
            self.command(f"slist {pos} {ch}", wait=0.12)
        self.command(f"srate {rate:g}", wait=0.2)
        true_rate = self.command("srate", wait=0.2)   # no-arg form reports realised rate
        m = re.search(r"(\d+(?:\.\d+)?)", true_rate)
        return float(m.group(1)) if m else float(rate)

    def start(self) -> None:
        s = self._require()
        s.reset_input_buffer()
        self._pending_echo = b"start"
        s.write(b"start\r\n")
        s.flush()
        self._streaming = True

    def _consume_echo(self, buf: bytes) -> bytes:
        """Strip the expected ``start`` echo from the head of the buffer."""
        if not self._pending_echo:
            return buf
        echo = self._pending_echo
        n = min(len(buf), len(echo))
        if echo[:n] == buf[:n]:
            if len(buf) >= len(echo):
                self._pending_echo = b""
                return buf[len(echo) :]
            self._pending_echo = echo[n:]
            return b""  # wait for the rest of the echo
        # the instrument did not echo (it was already scanning) - keep the data
        self._pending_echo = b""
        return buf

    def read_snapshot(self) -> List[int]:
        """One-shot comma separated sample of the current scan list."""
        body = self.command("read", wait=0.5)
        out = []
        for tok in body.replace("\r", " ").split(","):
            tok = tok.strip()
            if tok:
                try:
                    out.append(int(float(tok)))
                except ValueError:
                    pass
        return out

    # -- streaming ---------------------------------------------------------

    def stream(self, max_frames: Optional[int] = None,
               stall_timeout: Optional[float] = None) -> Iterator[Sample]:
        """Yield :class:`Sample` frames until stopped.

        ``stall_timeout`` (seconds) aborts the iteration if no byte arrives
        for that long - used by the stability harness to detect a dead link.
        """
        s = self._require()
        buf = b""
        t0 = time.time()
        index = 0
        last_byte = time.time()
        while True:
            chunk = self._read_available()
            now = time.time()
            if chunk:
                last_byte = now
                buf += chunk
                buf = self._consume_echo(bytes(buf))
                parts = buf.split(b"\r")
                buf = parts.pop()
                for part in parts:
                    text = part.decode("utf-8", "replace").strip()
                    if not text:
                        continue
                    try:
                        values = [int(float(tok)) for tok in text.split()]
                    except ValueError:
                        self.malformed_lines += 1
                        continue
                    yield Sample(t=now - t0, index=index, values=values, host_time=now)
                    index += 1
                    if max_frames is not None and index >= max_frames:
                        return
            else:
                if stall_timeout is not None and (now - last_byte) > stall_timeout:
                    raise DI188Error(
                        f"stream stalled for {now - last_byte:.1f}s (link likely dropped)")
                time.sleep(0.002)
