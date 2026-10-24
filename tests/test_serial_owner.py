"""No physical ports: fake constructors and OS-created virtual terminals only."""
import os
from pathlib import Path
import subprocess
import sys
import types

import pytest

from specter.node.serial_owner import open_serial


def fake_serial(monkeypatch):
    calls = []
    class Fake:
        def __init__(self, **kwargs):
            calls.append(kwargs)
            self.closed = False
            self.opened = False

        def open(self):
            assert self.dtr is False and self.rts is False
            self.opened = True

        def close(self):
            self.closed = True

        def fileno(self):
            return 12345

        def read(self, size):
            return b"x"[:size]

    instances = []
    def factory(**kwargs):
        instance = Fake(**kwargs)
        instances.append(instance)
        return instance
    monkeypatch.setitem(sys.modules, "serial", types.SimpleNamespace(Serial=factory))
    return calls, instances


def test_exclusivity_acquire_release_and_line_policy(monkeypatch):
    import fcntl
    import termios
    calls, instances = fake_serial(monkeypatch)
    ioctls = []
    monkeypatch.setattr(fcntl, "ioctl", lambda *args: ioctls.append(args))
    owner = open_serial("FAKE_ONLY", 115200)
    assert calls == [dict(port=None, baudrate=115200, timeout=.1, exclusive=True)]
    assert instances[0].port == "FAKE_ONLY"
    assert owner.read(1) == b"x"
    owner.close()
    owner.close()
    assert ioctls == [(12345, termios.TIOCEXCL), (12345, termios.TIOCNXCL)]
    assert instances[0].closed


def test_failed_kernel_exclusivity_closes_without_reading(monkeypatch):
    import fcntl
    _, instances = fake_serial(monkeypatch)
    def reject(*args):
        raise OSError("injected kernel lock failure")
    monkeypatch.setattr(fcntl, "ioctl", reject)
    with pytest.raises(OSError, match="kernel lock"):
        open_serial("FAKE_ONLY", 115200)
    assert instances[0].closed


def test_release_failure_still_closes_underlying_transport(monkeypatch):
    import fcntl
    import termios
    _, instances = fake_serial(monkeypatch)
    def ioctl(fd, command):
        if command == termios.TIOCNXCL:
            raise OSError("injected release failure")
    monkeypatch.setattr(fcntl, "ioctl", ioctl)
    owner = open_serial("FAKE_ONLY", 115200)
    with pytest.raises(OSError, match="release failure"):
        owner.close()
    assert instances[0].closed


def test_cooperating_process_is_rejected_and_lock_is_released():
    # This is an OS pseudo-terminal, never an attached USB/serial device.
    pytest.importorskip("serial")
    import pty
    master, slave = pty.openpty()
    path = os.ttyname(slave)
    os.close(slave)
    owner = None
    try:
        owner = open_serial(path, 115200)
        child = subprocess.run([sys.executable, "-c", """
import sys
from specter.node.serial_owner import open_serial
try:
    owner = open_serial(sys.argv[1],115200)
except OSError as exc:
    print('REJECTED:',exc)
    sys.exit(0)
else:
    owner.close()
    sys.exit(1)
""", path], cwd=Path(__file__).resolve().parents[1],
            capture_output=True, text=True, timeout=10)
        assert child.returncode == 0 and "REJECTED:" in child.stdout
        owner.close()
        reopened = open_serial(path, 115200)
        reopened.close()
    finally:
        if owner is not None:
            owner.close()
        os.close(master)
