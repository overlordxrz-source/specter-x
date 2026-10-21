"""USB serial discovery for the macOS bench tools.

Maps every USB serial node to the USB device behind it, so a tool can select
*its* device by USB identity instead of taking whichever node happens to sort
first. That distinction matters when several USB serial devices share the
bus: a DATAQ DI-188 (0x2846:0x8037) and an ESP32-S3 on its native USB
(0x303A:0x1001) look identical to a glob.

macOS only: the mapping comes from IOKit via ``ioreg``. On other platforms the
functions return empty results rather than guessing.
"""
from __future__ import annotations

import glob
import subprocess
from typing import Dict, List, Optional

__all__ = ["serial_port_usb_ids", "find_usb_serial_ports", "find_serial_ports"]


def serial_port_usb_ids() -> Dict[str, Dict]:
    """Map every USB serial node to its USB identity.

    Returns ``{callout_path: {product, vendor, vid, pid, serial}}``.
    """
    out: Dict[str, Dict] = {}
    try:
        import plistlib
        raw = subprocess.run(["ioreg", "-a", "-l"], capture_output=True,
                             text=True, timeout=20).stdout
        data = plistlib.loads(raw.encode())
    except Exception:
        return out

    def walk(node, usb=None):
        if not isinstance(node, dict):
            return
        if ("idVendor" in node and "idProduct" in node
                and "USB Product Name" in node):
            usb = node
        callout = node.get("IOCalloutDevice")
        if callout and usb:
            out[callout] = {
                "product": usb.get("USB Product Name") or "",
                "vendor": usb.get("USB Vendor Name") or "",
                "vid": usb["idVendor"],
                "pid": usb["idProduct"],
                "serial": usb.get("USB Serial Number") or "",
            }
        for child in (node.get("IORegistryEntryChildren") or []):
            walk(child, usb)

    walk(data)
    return out


def find_usb_serial_ports(vid: Optional[int] = None,
                          pid: Optional[int] = None) -> List[str]:
    """Serial nodes whose USB VID:PID matches (either field may be None)."""
    ids = serial_port_usb_ids()
    out = []
    for path, info in ids.items():
        if vid is not None and info["vid"] != vid:
            continue
        if pid is not None and info["pid"] != pid:
            continue
        out.append(path)
    return sorted(out)


def find_serial_ports() -> List[str]:
    """Candidate USB serial nodes, on macOS and Linux.

    Linux exposes CDC-ACM devices as ``/dev/ttyACM*`` and offers stable
    ``/dev/serial/by-id`` names, which are preferred because they survive
    re-plugging. Bluetooth and console nodes are never included.
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
