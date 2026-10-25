"""POSIX serial owner: cooperative lock plus a kernel exclusivity request.

No device is opened at import. This cannot evict or prove absence of an
already-open noncooperating reader; operator ownership review is required.
"""
from __future__ import annotations


class SerialOwner:
    ownership = "pyserial_flock_with_kernel_exclusivity_requested"

    def __init__(self, stream, ioctl, release):
        self._stream = stream
        self._ioctl = ioctl
        self._release = release
        self._closed = False

    def read(self, size):
        return self._stream.read(size)

    def close(self):
        if self._closed:
            return
        self._closed = True
        try:
            self._ioctl(self._stream.fileno(), self._release)
        finally:
            self._stream.close()


def open_serial(port, baud):
    """Open only the caller's explicit port, with a fixed 100 ms timeout.

    Fail closed if the kernel exclusivity request fails. A successful ioctl
    is not proof that the host/driver blocks all other opens (the Mac PTY
    probe demonstrates that distinction). Inactive DTR/RTS
    are requested before opening; OS/USB-driver line glitches are still a
    physical acceptance question, not a guaranteed reset-free operation.
    """
    import fcntl
    import termios
    if not all(hasattr(termios, name) for name in ("TIOCEXCL", "TIOCNXCL")):
        raise OSError("kernel serial exclusivity is unavailable")
    import serial  # optional dependency, only after explicit hardware opt-in
    stream = serial.Serial(port=None, baudrate=baud, timeout=.1, exclusive=True)
    try:
        stream.dtr = False
        stream.rts = False
        stream.port = port
        stream.open()
        fcntl.ioctl(stream.fileno(), termios.TIOCEXCL)
    except BaseException:
        stream.close()
        raise
    return SerialOwner(stream, fcntl.ioctl, termios.TIOCNXCL)
