"""Run the firmware's own formatter on the host, and parse its bytes.

`tests/test_firmware_contract.py` checks the C source *statically*. This
file checks the real thing: it compiles
``firmware/esp32-csi/softap_csi/main/csi_output.c`` with the host compiler
(a two-line FreeRTOS stub stands in for the queue header), runs it, and
feeds the bytes it prints to the **real** host parser.

If this passes, the wire format the device will emit is the format the
pipeline reads. That is the strongest statement available without hardware.
"""
from __future__ import annotations

import os
import shutil
import subprocess

import pytest

from specter.sensors.esp32.dispatcher import CSI_FIELD_NAMES, CsiParser
from specter.sensors.esp32.firmware_status import parse_status_line

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAIN = os.path.join(REPO, "firmware", "esp32-csi", "softap_csi", "main")
STUB = os.path.join(REPO, "tests", "firmware_host_stub")
HARNESS = os.path.join(REPO, "tests", "firmware_format_harness.c")

pytestmark = pytest.mark.skipif(
    shutil.which("clang") is None or not os.path.isdir(MAIN),
    reason="no host compiler, or the firmware source is absent")


@pytest.fixture(scope="module")
def lines(tmp_path_factory):
    exe = str(tmp_path_factory.mktemp("fw") / "harness")
    cmd = ["clang", "-std=c11", "-Wall", "-Wextra", "-O1",
           "-I", MAIN, "-I", STUB, HARNESS,
           os.path.join(MAIN, "csi_output.c"), "-o", exe]
    build = subprocess.run(cmd, capture_output=True, text=True)
    assert build.returncode == 0, f"the formatter did not compile:\n{build.stderr}"
    assert build.stderr.strip() == "", f"the formatter has warnings:\n{build.stderr}"
    run = subprocess.run([exe], capture_output=True, text=True, check=True)
    return run.stdout.splitlines()


def test_the_header_matches_the_host_field_names(lines):
    assert lines[0].split(",") == list(CSI_FIELD_NAMES)


def test_a_128_byte_record_parses_with_every_field_intact(lines):
    rec = CsiParser().feed(lines[1])
    assert rec is not None, "the parser rejected the firmware's own line"
    assert rec.seq == 42
    assert rec.mac == "b8:62:1f:e5:ac:62"
    assert rec.rssi == -62
    assert rec.rate == 11
    assert rec.sig_mode == 1
    assert rec.fields["mcs"] == "6"
    assert rec.fields["not_sounding"] == "1"
    assert rec.fields["sgi"] == "1"
    assert rec.noise_floor == -96
    assert rec.channel == 6
    # the timestamp that is negative under %d and correct as unsigned
    assert rec.local_timestamp == 3122514817
    assert rec.sig_len == 67
    assert rec.fields["len"] == "128"
    assert rec.first_word_invalid is False
    assert len(rec.iq) == 128
    # the values are the pattern the harness wrote: (i % 5) - 2
    assert rec.iq[:5] == [-2, -1, 0, 1, 2]


def test_the_quoted_tail_is_closed_exactly_once(lines):
    """The bug this catches: the writer adding a second closing quote."""
    line = lines[1]
    assert line.endswith(']"'), line[-8:]
    assert '""' not in line, "the IQ tail is closed twice"
    assert line.count('"') == 2, "exactly one opening and one closing quote"


def test_first_word_invalid_and_gain_compensation_are_carried(lines):
    rec = CsiParser().feed(lines[2])
    assert rec is not None
    assert rec.seq == 43
    assert rec.first_word_invalid is True
    assert rec.fields["len"] == "4"
    # 0.5 * {10, -20, 30, -40}
    assert rec.iq == [5, -10, 15, -20]


def test_a_256_byte_ht40_record_still_formats_and_parses(lines):
    """A 40 MHz peer doubles the record; the line buffer must allow it
    rather than silently drop the packet."""
    rec = CsiParser().feed(lines[3])
    assert rec is not None, "the 256-byte line did not format or did not parse"
    assert rec.seq == 44
    assert rec.fields["len"] == "256"
    assert len(rec.iq) == 256


def test_the_status_line_parses(lines):
    st = parse_status_line(lines[4])
    assert st is not None
    assert st["role"] == "softap"
    assert st["peer"] == "b8:62:1f:e5:ac:62"
    assert st["channel"] == 6
    assert st["rssi"] == -62
    assert st["csi_callbacks"] == 1200
    assert st["printed"] == 1180
    assert st["dropped_old"] == 0
    assert st["queue_high"] == 7


def test_the_status_line_reports_the_three_counts_apart(lines):
    """The counts must be separable: a callback, a record on the wire, a
    rejected callback, and the frames that carried a payload."""
    st = parse_status_line(lines[4])
    assert st["rejected"] == 5
    assert st["frames_data"] == 980
    assert st["frames_null"] == 200
    assert st["frames_ambiguous"] == 0
    assert st["flash_kb"] == 16384
    assert st["flash_physical_kb"] == 16384
