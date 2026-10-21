"""Read-only diagnostics for a stalled USB CDC link.

The ESP32-S3's native USB link has wedged several times: the device keeps
enumerating with the right VID/PID and serial, but the CDC data path stops
delivering bytes in either direction. These helpers gather evidence to tell a
**device-side** stall apart from a **host-side** USB problem.

Everything here is read-only. Nothing resets the device, enters the
bootloader, or re-opens the node under diagnosis (re-opening it would
re-enumerate the device and destroy the evidence).
"""
from __future__ import annotations

import plistlib
import subprocess
import time
from typing import Dict, List

ESP32_USB_VID = 0x303A
ESP32_USB_PID = 0x1001
#: The board's other USB path: the CH343 UART0 bridge.
UART_NODE = "/dev/cu.usbmodem5B901602281"


def usb_enumeration() -> List[Dict]:
    """Every USB device the host can still see (read-only)."""
    out: List[Dict] = []
    try:
        raw = subprocess.run(["ioreg", "-p", "IOUSB", "-a", "-l"],
                             capture_output=True, text=True, timeout=20).stdout
        data = plistlib.loads(raw.encode())
    except Exception:
        return out

    def walk(node):
        if not isinstance(node, dict):
            return
        if "idVendor" in node and "idProduct" in node:
            out.append({"product": node.get("USB Product Name"),
                        "vendor": node.get("USB Vendor Name"),
                        "vid": node["idVendor"], "pid": node["idProduct"],
                        "serial": node.get("USB Serial Number")})
        for c in (node.get("IORegistryEntryChildren") or []):
            walk(c)

    walk(data)
    return out


def esp32_still_enumerates() -> Dict:
    """Is the ESP32-S3 still visible to the host's USB stack?"""
    for d in usb_enumeration():
        if d["vid"] == ESP32_USB_VID and d["pid"] == ESP32_USB_PID:
            return {"enumerated": True, **d}
    return {"enumerated": False}


def uart_console_alive(timeout: float = 3.0, node: str = UART_NODE) -> Dict:
    """Is the MCU still running? Read the UART0 console passively.

    The console is opened with DTR and RTS held **low** so the board's
    auto-reset circuit is not triggered. This must never reset the device.
    """
    result: Dict = {"bytes": 0, "readable": False, "note": ""}
    try:
        import serial
    except ImportError:
        result["note"] = "pyserial missing"
        return result
    try:
        s = serial.Serial(node, 115200, timeout=0.3)
    except Exception as exc:
        result["note"] = f"{type(exc).__name__}: {exc}"
        return result
    try:
        s.dtr = False
        s.rts = False
        time.sleep(0.2)
        buf = bytearray()
        end = time.time() + timeout
        while time.time() < end:
            try:
                n = s.in_waiting
            except Exception:
                break
            if n:
                buf += s.read(n)
            time.sleep(0.05)
        result["bytes"] = len(buf)
        result["readable"] = True
        result["sample"] = bytes(buf[:300]).decode("utf-8", "replace")
    finally:
        try:
            s.close()
        except Exception:
            pass
    return result


def recent_usb_errors(lookback_s: float = 180) -> List[str]:
    """Kernel-level USB messages around the stall (read-only)."""
    try:
        r = subprocess.run(
            ["log", "show", "--last", f"{int(lookback_s)}s",
             "--predicate", 'subsystem == "com.apple.iokit.IOUSBHostFamily"'],
            capture_output=True, text=True, timeout=25)
        lines = [l for l in r.stdout.splitlines()
                 if l.strip() and not l.startswith("Filtering")
                 and not l.startswith("Timestamp")]
        return lines[-20:]
    except Exception as exc:
        return [f"log query failed: {exc}"]


def collect_stall_evidence(silence_s: float = 0.0) -> Dict:
    """The full evidence set for one stall."""
    ev = {
        "silent_for_s": round(silence_s, 2),
        "esp32_enumeration": esp32_still_enumerates(),
        "uart_console": uart_console_alive(),
        "kernel_usb_log": recent_usb_errors(180),
    }
    ev["diagnosis"] = diagnose(ev)
    return ev


def diagnose(ev: Dict) -> str:
    """A one-line reading of the evidence."""
    enum = ev.get("esp32_enumeration") or {}
    console = ev.get("uart_console") or {}
    if not enum.get("enumerated"):
        return ("device no longer enumerates: the USB link dropped at the host, "
                "or the device was unplugged/power-cycled")
    if console.get("readable") and console.get("bytes", 0) > 0:
        return ("device still enumerates AND the UART0 console is still "
                "producing output: the MCU is alive, so the fault is in the "
                "USB CDC path (device-side) - not in the application and not "
                "a host-wide bus failure")
    if console.get("readable"):
        return ("device still enumerates but the UART0 console is silent: the "
                "MCU may be halted; a device-side USB fault and an application "
                "hang cannot be separated without a reset")
    return ("device still enumerates; the UART0 console could not be read, so "
            "the MCU's state is unknown")
