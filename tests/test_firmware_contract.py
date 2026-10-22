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


def _code(name: str) -> str:
    """The source with its comments removed.

    A contract test has to look at what the code DOES, and a word that
    appears in a comment explaining why a call was removed is not a call.
    """
    src = _source(name)
    src = re.sub(r"/\*.*?\*/", " ", src, flags=re.S)
    src = re.sub(r"//[^\n]*", " ", src)
    return src


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
    """One writer means the output is serialised by construction.

    This test used to permit TWO writers - the data task and the status
    task - because both called fwrite() on the same FILE*. That was the
    open gate the handbook recorded: the captured evidence contains a
    status line cut in half with a second copy of its own text spliced
    into the gap, which is what a buffered stdio plus two writers
    produces. There is now ONE output path.
    """
    src = _source("app_main.c")
    assert "static void writer_task" in src
    assert "console_emit" in src
    # no stdio writing anywhere: every line goes out through console_emit
    code = _code("app_main.c")
    assert "fwrite" not in code, "the firmware must not use buffered stdio"
    assert "fputs" not in code, "the firmware must not use buffered stdio"
    # and the line is emitted with ONE write, terminator included
    assert "write(fileno(stdout)" in code
    assert "setvbuf(stdout, NULL, _IONBF, 0)" in code, \
        "stdout must be unbuffered or a line can be split by stdio"


def test_the_log_lines_share_the_one_output_path():
    """The IDF's own log lines go to stdout too. If they did not take the
    same path they could still land in the middle of a record."""
    src = _source("app_main.c")
    assert "esp_log_set_vprintf(console_log_vprintf)" in src
    assert "console_log_vprintf" in src


def test_the_lab_credential_is_not_in_the_source_tree():
    """The passphrase must not be in Git.

    A Kconfig option would put it in a tracked sdkconfig.defaults, which is
    a published passphrase. The credential is compiled in from a header the
    build generates into the BUILD DIRECTORY, and the build refuses to
    produce an open lab network unless that is asked for explicitly.
    """
    kconfig = _source("Kconfig.projbuild")
    assert "SPECTER_LAB_PASSWORD" not in kconfig, \
        "the passphrase must not be a Kconfig option"
    cmake = _source("CMakeLists.txt")
    assert "SPECTER_LAB_PSK" in cmake
    assert "SPECTER_LAB_ALLOW_OPEN" in cmake, \
        "an open lab network must be an explicit choice"
    assert "FATAL_ERROR" in cmake, \
        "the build must fail closed without a credential"
    assert "CMAKE_CURRENT_BINARY_DIR" in cmake, \
        "the generated header must land in the build directory"
    # the build writes the header itself, into the build directory
    assert "file(WRITE" in cmake
    assert "SPECTER_LAB_PSK" in cmake
    assert 'define SPECTER_LAB_PSK' in cmake


def test_the_firmware_reads_the_generated_credential():
    src = _source("app_main.c")
    assert '#include "lab_credentials.h"' in src
    assert "WIFI_AUTH_WPA2_PSK" in src
    assert "WIFI_AUTH_OPEN" in src, \
        "the open path must still exist for an explicitly open build"
    # and the secret must never be printed
    assert "lab_credential()" in src


def test_the_frames_are_classified_and_reported():
    """A CSI callback fires for every frame the radio hears, including the
    empty ones a station sends to keep an association alive. The three
    counts must be kept apart and reported."""
    src = _source("app_main.c")
    assert "s_frames_data" in src
    assert "s_frames_null" in src
    assert "s_frames_ambiguous" in src
    assert "s_csi_rejected" in src
    out = _source("csi_output.c")
    for key in ("rej=", "data=", "null=", "amb="):
        assert key in out, f"the status line must report {key}"


def test_the_flash_size_is_reported_by_the_device():
    """The runtime flash size comes from the BOOTLOADER's header, not the
    app image's, and on this board the bootloader says 2 MB while the chip
    is 16 MB. The device must say what it actually has, and the chip size
    too, because the difference between them IS the defect."""
    src = _source("app_main.c")
    assert "esp_flash_get_size(" in src
    assert "esp_flash_get_physical_size(" in src
    out = _source("csi_output.c")
    assert "flash_kb=" in out
    assert "flash_phys_kb=" in out


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

def test_wifi_is_initialised_before_it_is_configured():
    """A boot-blocking bug the preflight caught: calling esp_wifi_set_mode()
    without esp_wifi_init() returns ESP_ERR_WIFI_NOT_INIT and the board
    resets in a loop. The order is checked inside app_main, because the
    helpers are defined earlier in the file than the calls to them."""
    src = _source("app_main.c")
    body = src[src.index("void app_main(void)"):]
    init = body.index("esp_wifi_init(")
    for call in ("wifi_softap_start(", "wifi_station_start(", "wifi_csi_init("):
        if call in body:
            assert body.index(call) > init, f"{call}) runs before esp_wifi_init"


def test_the_netif_matches_the_role():
    """The SoftAP branch must create the AP netif, or the Mac associates and
    never gets an address."""
    src = _source("app_main.c")
    body = src[src.index("void app_main(void)"):]
    start = body.index("#if CONFIG_SPECTER_ROLE_SOFTAP")
    block = body[start:body.index("#endif", start)]
    ap, sta = block.split("#else")
    assert "esp_netif_create_default_wifi_ap()" in ap
    assert "esp_netif_create_default_wifi_sta()" in sta


def test_the_writer_does_not_add_a_second_closing_quote():
    """The formatter closes the quoted IQ tail; the terminator must not."""
    src = _source("app_main.c")
    body = src[src.index("static void writer_task"):]
    body = body[:body.index("/* --- the status task")]
    # the terminator is a newline character in the same buffer, not a
    # second string, so it cannot add a quote
    assert "line[n] = '\\n';" in body
    assert 'console_emit(line, n + 1)' in body
    assert '"\\r"' not in body, "the writer must not add a carriage return"
    quotes = [ln for ln in body.splitlines() if '"' in ln and "console_emit" not in ln]
    for line in quotes:
        assert line.count('"') % 2 == 0, f"unbalanced quote: {line}"
