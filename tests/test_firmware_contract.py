"""The firmware and the host parser must agree, and the test enforces it.

The new firmware in ``firmware/esp32-csi/softap_csi`` reproduces
Espressif's ``csi_recv_router`` wire format so that the host parser in
``specter/sensors/esp32/dispatcher.py`` needs no change. That is a promise
made in two languages, in two files, in two languages of code - so it is
tested rather than trusted.

If the firmware's header, its field count or its field order drifts, these
tests fail rather than the archive silently becoming unreadable.
"""
from __future__ import annotations

import os
import re

import pytest

from specter.sensors.esp32.dispatcher import CSI_FIELD_NAMES, CsiParser

FIRMWARE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "firmware", "esp32-csi", "softap_csi", "main")


def _source(name: str) -> str:
    path = os.path.join(FIRMWARE, name)
    if not os.path.exists(path):
        pytest.skip(f"the firmware source is not present at {path}")
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def test_the_firmware_header_is_the_host_header():
    """The CSV header the firmware prints is the header the parser expects."""
    src = _source("csi_output.c")
    m = re.search(r'csi_output_header\(void\)\s*\{(.*?)\n\}', src, re.S)
    assert m, "the header function was not found"
    body = m.group(1)
    parts = re.findall(r'"([^"]*)"', body)
    header = "".join(parts)
    assert header.split(",") == list(CSI_FIELD_NAMES)


def test_the_firmware_emits_the_same_number_of_fields_as_the_parser_reads():
    """21 values after the MAC: 19 metadata, then len, then first_word."""
    src = _source("csi_output.c")
    body = src[src.index("size_t csi_format_line"):]
    body = body[:body.index("size_t csi_format_status")]
    # the metadata fields are emitted one per line, each with a comment
    emits = re.findall(r'line_addf\(&l,\s*"[^"]*"[^;]*\);\s*/\*\s*([a-z_]+)\s*\*/',
                       body)
    names = [n for n in emits]
    # rssi .. sig_mode (the duplicate) is 19 values
    assert len(names) == 19, f"expected 19 metadata values, found {len(names)}"
    # and the order must be the upstream's
    expected = ["rssi", "rate", "sig_mode", "mcs", "cwb", "smoothing",
                "not_sounding", "aggregation", "stbc", "fec_coding", "sgi",
                "noise_floor", "ampdu_cnt", "channel", "secondary_channel",
                "local_timestamp", "ant", "sig_len", "sig_mode"]
    assert names == expected, f"the field order drifted: {names}"


def test_the_firmware_emits_len_and_first_word_after_the_metadata():
    src = _source("csi_output.c")
    assert re.search(r'line_addf\(&l, ",%u,%u",\s*\(unsigned\)rec->len,', src), \
        "len and first_word_invalid must be emitted together, after the metadata"
    assert "rec->first_word_invalid ? 1u : 0u" in src


def test_the_iq_tail_is_quoted_and_one_value_per_byte():
    src = _source("csi_output.c")
    assert '",\\"["' in src or '",\\"[' in src, "the IQ tail must open with a quote"
    assert '"\\"]\\""' in src or '"]\\""' in src, "the IQ tail must close with a quote"
    # one value per byte of the CSI buffer
    assert re.search(r"for \(uint16_t i = 0; i < rec->len; i\+\+\)", src)


def test_the_queue_is_bounded_and_its_losses_are_counted():
    """A slow host must cost counted loss, never a corrupted stream."""
    src = _source("dq_ring.c")
    assert "dropped_old" in src and "dropped_new" in src
    # the push must never block: a zero timeout on the send
    assert re.search(r"xQueueSend\(st->queue, rec, 0\)", src)
    # and the drop-oldest path
    assert re.search(r"xQueueReceive\(st->queue, &discard, 0\)", src)


def test_the_callback_does_not_format_or_print():
    """The IDF says the callback runs in the Wi-Fi task and must not do
    lengthy work. The firmware must therefore not format or print there."""
    src = _source("app_main.c")
    cb = src[src.index("static void wifi_csi_rx_cb"):]
    cb = cb[:cb.index("/* --- the writer task")]
    assert "printf" not in cb, "the CSI callback must not format"
    assert "fwrite" not in cb and "fputs" not in cb, \
        "the CSI callback must not print"
    assert "dq_push" in cb, "the callback must hand the record to the queue"


def test_only_the_writer_task_writes():
    """One writer means the output is serialised by construction."""
    src = _source("app_main.c")
    assert "static void writer_task" in src
    # every fwrite/fputs in the file must be inside the writer or the status
    writer = src[src.index("static void writer_task"):]
    writer = writer[:writer.index("/* --- the status task")]
    assert "fwrite" in writer
    # the status task writes its own line, and that is the only other writer
    status = src[src.index("static void status_task"):]
    status = status[:status.index("/* --- Wi-Fi setup")]
    assert "fwrite" in status
    # nothing else
    rest = src.replace(writer, "").replace(status, "")
    assert "fwrite" not in rest and "fputs" not in rest, \
        "only the writer and the status task may write"


def test_the_csi_configuration_is_unchanged_from_the_original_image():
    """LLTF only, the channel filter on, the manual scale: the same
    configuration the original `csi_recv_router` used."""
    src = _source("app_main.c")
    m = re.search(r"wifi_csi_config_t config = \{(.*?)\};", src, re.S)
    assert m, "the CSI configuration was not found"
    body = m.group(1)
    assert ".lltf_en           = true" in body
    assert ".htltf_en          = false" in body
    assert ".channel_filter_en = true" in body
    assert ".manu_scale        = true" in body
    assert ".shift             = true" in body


def test_a_line_in_the_firmware_format_parses_on_the_host():
    """The end-to-end contract: a line shaped like the firmware's parses."""
    line = ('CSI_DATA,42,b8:62:1f:e5:ac:62,-62,11,1,6,0,0,1,0,0,0,1,-96,0,1,0,'
            '3122514817,0,67,1,128,0,"['
            + ",".join(["0", "0", "31", "-23"] * 32) + ']"')
    rec = CsiParser().feed(line)
    assert rec.seq == 42
    assert rec.mac == "b8:62:1f:e5:ac:62"
    assert rec.rssi == -62
    assert rec.rate == 11
    assert rec.channel == 1
    assert rec.local_timestamp == 3122514817
    assert rec.fields["len"] == "128"
    assert len(rec.iq) == 128
    assert rec.first_word_invalid is False


def test_the_firmware_keeps_the_gain_compensation():
    """The amplitude values on the wire must be the same values the original
    image printed, so the archives stay comparable."""
    src = _source("app_main.c")
    assert "esp_csi_gain_ctrl_get_gain_compensation" in src
    assert "esp_csi_gain_ctrl_record_rx_gain" in src
    assert "esp_csi_gain_ctrl_get_rx_gain_baseline" in src
    # and it is applied to the bytes, as the upstream did
    out = _source("csi_output.c")
    assert "rec->gain_compensation * (float)rec->iq[i]" in out
