"""DI-188 protocol driver: echo handling, identity, flash parsing, streaming.

The fake serial reproduces the instrument's actual quirks: it echoes every
typed character except CR, answers a command only when the CR arrives, and
emits CR-delimited frames once ``start`` has been received.
"""
import pytest

from specter.sensors.di188.driver import (DI188Driver, DI188Identity, DeviceCalibration,
                                           Sample)


class FakeSerial:
    """Emulates the DI-188's CDC-ACM behaviour."""

    def __init__(self, responses=None, frame_values=None):
        self.responses = responses or {}
        self.frame_values = frame_values or []
        self.buf = bytearray()
        self.pending = bytearray()
        self.written = bytearray()
        self.scanning = False
        self.timeout = 1.0
        self.baudrate = 0
        self.closed = False

    # -- pyserial-ish API -------------------------------------------------
    def write(self, data):
        self.written += data
        for b in data:
            if b == 0x0D:                       # CR terminates a command
                cmd = self.pending.decode("ascii", "replace")
                self.pending = bytearray()
                if cmd == "start":
                    self.scanning = True
                    self._emit_frames()
                else:
                    self.buf += self.responses.get(cmd, "").encode()
            elif b == 0x0A:                     # LF is echoed only when idle
                if not self.scanning:
                    self.buf += b"\n"
            else:
                self.pending += bytes([b])
                if not self.scanning:
                    self.buf += bytes([b])       # echo
        return len(data)

    def _emit_frames(self):
        for values in self.frame_values:
            self.buf += ("\r" + " ".join(str(v) for v in values)).encode()

    def read(self, size=1):
        if not self.buf:
            return b""
        out = bytes(self.buf[:size])
        del self.buf[:size]
        return out

    def reset_input_buffer(self):
        self.buf = bytearray()

    def close(self):
        self.closed = True

    def flush(self):
        pass


def make_driver(responses=None, frame_values=None):
    dev = DI188Driver(port="/dev/fake")
    dev.ser = FakeSerial(responses, frame_values)
    dev.identity = DI188Identity(port="/dev/fake")
    # fast drain: return whatever is buffered instead of waiting out the timeout
    def fast_drain(self, seconds):
        out = b""
        while True:
            chunk = self.ser.read(4096)
            if not chunk:
                break
            out += chunk
        return out
    dev._drain = fast_drain.__get__(dev)
    return dev


def test_command_strips_the_idle_echo():
    dev = make_driver({"info 1": " 188\r"})
    assert dev.command("info 1") == "188"


def test_read_identity_reads_every_info_field():
    dev = make_driver({
        "info 0": " DATAQ\r", "info 1": " 188\r", "info 2": " 0\r",
        "info 3": " 0\r", "info 6": " 022D9B0B\r", "rchn": " 4\r",
    })
    ident = dev.read_identity()
    assert ident.vendor_tag == "DATAQ"
    assert ident.model == "188"
    assert ident.model_name == "DI-188"
    assert ident.serial_number == "022D9B0B"
    assert ident.channel_count == 4


def _flash_bytes(scale=18850, offsets=(-78, -64, -72, -84)):
    # Layout of dqCal_type: structrev[2] hardwarerev[2] key[32]
    # serial_n[16] lastCalDate[16] adc_scale[8][4] adc_offset[8][4] = 196 bytes
    b = bytearray(196)
    b[0:2] = (1).to_bytes(2, "little")            # struct rev
    b[2:4] = (0).to_bytes(2, "little")            # hardware rev
    b[4:20] = b"0123456789ABCDEF"                 # key[32]
    b[36:44] = b"022D9B0B"                         # serial_n[16]
    b[52:60] = b"6214F19E"                         # lastCalDate[16]
    for ch in range(8):
        for j in range(4):
            off = 68 + ch * 8 + j * 2
            b[off:off + 2] = scale.to_bytes(2, "little", signed=True)
    for ch, off_val in enumerate(offsets):
        off = 132 + ch * 8
        b[off:off + 2] = int(off_val).to_bytes(2, "little", signed=True)
    assert len(b) == 196
    return b


def test_read_device_calibration_parses_the_flash_struct():
    raw = _flash_bytes()
    dev = make_driver({"readflash": " " + " ".join(str(x) for x in raw) + "\r"})
    cal = dev.read_device_calibration()
    assert cal.read_ok
    assert cal.key == "0123456789ABCDEF"
    assert cal.serial_number == "022D9B0B"
    assert cal.last_cal_date == "6214F19E"
    assert cal.channel_scale(0) == 18850
    assert [cal.channel_offset(i) for i in range(4)] == [-78, -64, -72, -84]
    assert cal.channel_offset(5) == 0
    assert cal.profile == "di188_pm10v"


def test_profile_is_unknown_for_an_unexpected_scale():
    raw = _flash_bytes(scale=12345)
    dev = make_driver({"readflash": " " + " ".join(str(x) for x in raw) + "\r"})
    assert dev.read_device_calibration().profile == "unknown"


def test_configure_sends_the_documented_command_sequence():
    dev = make_driver({"srate": " 500.000000\r"})
    realised = dev.configure([0, 1, 2, 3], rate=500)
    assert realised == 500.0
    sent = dev.ser.written.decode()
    for expected in ("stop", "eol 0", "encode 1",
                     "slist 0 0", "slist 1 1", "slist 2 2", "slist 3 3",
                     "srate 500"):
        assert expected in sent
    # the scan list must be built from position 0 upwards
    assert sent.index("slist 0 0") < sent.index("slist 1 1") < sent.index("slist 3 3")


def test_stream_skips_the_start_echo_and_yields_frames():
    # The instrument prefixes every frame with CR, so the last frame stays
    # buffered until the next one arrives - hence the extra frame.
    dev = make_driver(frame_values=[[-12, 5], [7, -3], [0, 0], [9, 9]])
    dev.start()
    frames = list(dev.stream(max_frames=3))
    assert [f.values for f in frames] == [[-12, 5], [7, -3], [0, 0]]
    assert [f.index for f in frames] == [0, 1, 2]
    assert dev.malformed_lines == 0


def test_stream_counts_malformed_lines():
    dev = make_driver()
    dev.ser.buf += b"\rnot-a-number\r12 34\r"
    dev._pending_echo = b""
    frames = list(dev.stream(max_frames=1))
    assert frames[0].values == [12, 34]
    assert dev.malformed_lines == 1


def test_stop_is_sent_when_closing():
    dev = make_driver()
    fake = dev.ser
    dev.start()
    dev.close()
    assert b"stop" in fake.written
