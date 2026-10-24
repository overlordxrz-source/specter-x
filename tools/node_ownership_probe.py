"""Report host exclusivity behavior using an OS-created pseudo-terminal only.

This diagnostic deliberately records a noncooperating second-open outcome
instead of claiming that a successful TIOCEXCL request proves protection.
No argument can select a physical device.
"""
import json
import os
from pathlib import Path
import platform
import pty
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from specter.node.serial_owner import open_serial


def main():
    master, slave = pty.openpty()
    path = os.ttyname(slave)
    os.close(slave)
    owner = None
    result = dict(host=platform.system(), release=platform.release(),
        transport="OS-created pseudo-terminal; no physical device", physical_test=False)
    try:
        owner = open_serial(path, 115200)
        result["kernel_exclusive_request_succeeded"] = True
        try:
            other = open_serial(path, 115200)
        except OSError:
            result["cooperating_owner_rejected"] = True
        else:
            other.close()
            result["cooperating_owner_rejected"] = False
        try:
            descriptor = os.open(path, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        except OSError as exc:
            result["noncooperating_open_rejected"] = True
            result["noncooperating_errno"] = exc.errno
        else:
            os.close(descriptor)
            result["noncooperating_open_rejected"] = False
        owner.close()
        reopened = open_serial(path, 115200)
        reopened.close()
        result["ownership_released"] = True
    finally:
        if owner is not None:
            owner.close()
        os.close(master)
    result["physical_exclusive_ownership"] = "UNVERIFIED; operator preflight required"
    print(json.dumps(result, indent=2))
    return 0 if result["cooperating_owner_rejected"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
