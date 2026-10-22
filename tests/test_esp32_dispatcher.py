"""The single USB serial dispatcher: interleaving, isolation, bounded queues.

A CSI capture and the supervisor telemetry share one CDC link, so the
dispatcher has to keep them apart, count them separately, and never let one
of them grow without bound.
"""
import pytest

from specter.sensors.esp32.firmware_status import parse_status_line
from specter.sensors.esp32.dispatcher import (CSI_FIELD_NAMES, BoundedQueue,
                                              CsiParser, SerialDispatcher,
                                              classify)


#: The upstream packet is 24 fields plus a quoted data blob; the names are the
#: ones the upstream example prints in its CSV header.
def csi_line(seq=1, mac="b8:62:1f:e5:ac:62", rssi=-60, iq=None, n_bytes=128):
    """A realistic CSI line.

    The upstream prints exactly ``info->len`` values - one per BYTE of the
    CSI buffer - so the tail length has to match the ``len`` field, and the
    parser checks it. The default is the board's real 128-byte HT20 LLTF
    buffer: 64 complex subcarriers, with subcarrier 0 (DC) and 27..37 (the
    guard band) unpopulated.
    """
    if iq is None:
        iq = [0] * n_bytes
        for n in range(1, 27):
            iq[2 * n] = -12 + (n % 5)
            iq[2 * n + 1] = 11 - (n % 4)
        for n in range(38, 64):
            iq[2 * n] = -9 + (n % 4)
            iq[2 * n + 1] = 7 - (n % 3)
    fields = [
        "CSI_DATA", str(seq), mac, str(rssi),
        "9", "0", "0", "0", "0", "0", "0", "0", "0", "0",
        "-90", "0", "11", "0", "67768165", "0", "109", "0",
        str(len(iq)), "0",
    ]
    return ",".join(fields) + ",\"" + "[" + ",".join(str(v) for v in iq) + "]\""


HELLO = "HELLO,1,esp32s3-devkitc-1,ESP32-S3,14:C1:9F:26:52:EC,0.1.0,abc123"
STAT = "STAT,123.456,180000,170000,OK"
HB = "HB,42,123.456"


# --- classification --------------------------------------------------------

@pytest.mark.parametrize("line,expected", [
    (csi_line(), "csi"),
    (HELLO, "supervisor"),
    (STAT, "supervisor"),
    (HB, "supervisor"),
    ("garbage", "unknown"),
    ("", "unknown"),
    ("I (169) esp_image: segment 4", "unknown"),
])
def test_classification(line, expected):
    assert classify(line) == expected


# --- interleaving ----------------------------------------------------------

def test_interleaved_records_reach_the_right_consumer():
    d = SerialDispatcher()
    d.feed_line(HELLO)
    d.feed_line(csi_line(1))
    d.feed_line(STAT)
    d.feed_line(csi_line(2))
    d.feed_line(HB)

    csi = d.drain_csi()
    sup = d.drain_supervisor()
    assert [c.seq for c in csi] == [1, 2]
    assert len(sup) == 3
    assert sup[0].board == "esp32s3-devkitc-1"
    assert sup[1].uptime_s == pytest.approx(123.456)
    assert sup[2].seq == 42

    c = d.snapshot()
    assert c["csi_parsed"] == 2
    assert c["supervisor_parsed"] == 3
    assert c["unknown_lines"] == 0


def test_a_malformed_csi_line_does_not_taint_the_supervisor_counters():
    d = SerialDispatcher()
    d.feed_line("CSI_DATA,notanumber,mac,-60,9,1,0,0,0,1,0,0,0,1,-90,0,11,0,1,0,109,0,128,0")
    d.feed_line(HB)
    c = d.snapshot()
    assert c["csi_malformed"] == 1
    assert c["csi_parsed"] == 0
    assert c["supervisor_parsed"] == 1
    assert c["supervisor_malformed"] == 0


def test_a_malformed_supervisor_line_does_not_taint_the_csi_counters():
    d = SerialDispatcher()
    d.feed_line("HB,notanumber,1.0")
    d.feed_line(csi_line(1))
    c = d.snapshot()
    assert c["supervisor_malformed"] == 1
    assert c["csi_parsed"] == 1
    assert c["csi_malformed"] == 0


def test_unknown_lines_are_counted_separately():
    d = SerialDispatcher()
    d.feed_line("I (169) esp_image: segment 4: paddr=000c08b4")
    d.feed_line("something else entirely")
    c = d.snapshot()
    assert c["unknown_lines"] == 2
    assert c["csi_parsed"] == 0
    assert c["supervisor_parsed"] == 0


def test_the_csv_header_is_recognised_not_counted_as_unknown():
    d = SerialDispatcher()
    d.feed_line(",".join(CSI_FIELD_NAMES))
    c = d.snapshot()
    assert c["headers_seen"] == 1
    assert c["unknown_lines"] == 0


# --- parsing ---------------------------------------------------------------

def test_csi_fields_are_named_from_the_upstream_header():
    rec = CsiParser().feed(csi_line(seq=7, rssi=-61))
    assert rec.seq == 7
    assert rec.mac == "b8:62:1f:e5:ac:62"
    assert rec.rssi == -61
    assert rec.rate == 9
    assert rec.noise_floor == -90
    assert rec.channel == 11
    assert rec.local_timestamp == 67768165
    assert rec.sig_len == 109
    assert rec.fields["rx_format"] == "0"
    assert rec.fields["len"] == "128"
    assert rec.fields["first_word"] == "0"
    assert rec.fields["ant"] == "0"
    assert rec.fields["secondary_channel"] == "0"
    assert rec.fields["ampdu_cnt"] == "0"
    assert rec.fields["sgi"] == "0"
    assert rec.fields["type"] == "CSI_DATA"
    # the tail carries exactly ``len`` values - one per byte of the CSI buffer
    assert len(rec.iq) == 128
    # and the board's real HT20 layout: DC and the guard band are unpopulated
    assert rec.iq[0:2] == [0, 0]
    assert all(v == 0 for v in rec.iq[54:76])
    assert rec.has_iq


def test_a_real_packet_captured_from_the_board_parses_with_the_right_names():
    """The exact line observed on the hardware on 2026-10-21, from a fixture."""
    import os
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, "fixtures", "csi_packet_sample.txt")) as fh:
        line = fh.read().strip()
    rec = CsiParser().feed(line)
    # the fixture is a packet captured from the board on 2026-10-22
    assert rec.seq == 299155
    assert rec.mac == "40:f4:ec:7e:37:22"
    assert rec.rssi == -62
    assert rec.rate == 11
    assert rec.noise_floor == -96
    assert rec.channel == 1
    assert rec.sig_len == 67
    assert rec.fields["rx_format"] == "1"      # a second copy of sig_mode
    assert rec.fields["len"] == "128"          # the valid CSI length, in bytes
    assert rec.fields["first_word"] == "0"     # the first_word_invalid flag
    # the tail carries exactly `len` values
    assert len(rec.iq) == 128
    # and the board's real HT20 layout: DC and the guard band unpopulated
    amps = [float(abs(v)) for v in rec.iq[:4]]
    assert rec.iq[0] == 0 and rec.iq[1] == 0
    assert all(v == 0 for v in rec.iq[54:76])
    # the device's 32-bit microsecond counter, printed signed
    assert rec.local_timestamp == 3122514817
    assert 0 <= rec.local_timestamp < 2 ** 32


def test_a_csi_packet_split_across_two_chunks_is_reassembled():
    d = SerialDispatcher()
    line = csi_line(1) + "\r\n"
    d.feed(line[:30].encode())
    assert d.snapshot()["csi_parsed"] == 0
    d.feed(line[30:].encode())
    assert d.snapshot()["csi_parsed"] == 1
    assert d.drain_csi()[0].seq == 1


def test_crlf_and_lf_line_endings_both_work():
    d = SerialDispatcher()
    d.feed((csi_line(1) + "\r\n").encode())
    d.feed((csi_line(2) + "\n").encode())
    assert d.snapshot()["csi_parsed"] == 2


# --- sequence gaps ---------------------------------------------------------

def test_sequence_gaps_and_missing_packets_are_counted():
    p = CsiParser()
    p.feed(csi_line(1))
    p.feed(csi_line(2))
    p.feed(csi_line(9))          # 3..8 are missing
    assert p.gaps == 1
    assert p.missing == 6


def test_a_restart_is_not_counted_as_missing_packets():
    p = CsiParser()
    p.feed(csi_line(100))
    p.feed(csi_line(1))           # the device rebooted
    assert p.gaps == 1
    assert p.missing == 0


def test_the_dispatcher_reports_the_gap_counters():
    d = SerialDispatcher()
    d.feed_line(csi_line(1))
    d.feed_line(csi_line(5))
    c = d.snapshot()
    assert c["csi_sequence_gaps"] == 1
    assert c["csi_missing_packets"] == 3
    assert c["csi_last_seq"] == 5


# --- bounded queues --------------------------------------------------------

def test_a_bounded_queue_keeps_the_newest_and_counts_drops():
    q = BoundedQueue(3)
    for i in range(10):
        q.push(i)
    assert len(q) == 3
    assert q.peek() == [7, 8, 9]
    assert q.dropped == 7


def test_an_overflowing_consumer_cannot_grow_the_queue():
    d = SerialDispatcher(csi_capacity=4, supervisor_capacity=2)
    for i in range(50):
        d.feed_line(csi_line(i))
        d.feed_line(HB)
    c = d.snapshot()
    assert c["csi_queued"] == 4
    assert c["supervisor_queued"] == 2
    assert c["csi_dropped"] == 46
    assert c["supervisor_dropped"] == 48
    # the counters still account for everything that arrived
    assert c["csi_parsed"] == 50
    assert c["supervisor_parsed"] == 50


def test_a_full_consumer_does_not_stop_the_other():
    d = SerialDispatcher(csi_capacity=1, supervisor_capacity=64)
    for i in range(20):
        d.feed_line(csi_line(i))
    d.feed_line(HB)
    assert d.snapshot()["supervisor_parsed"] == 1
    assert len(d.drain_supervisor()) == 1


# --- surviving a damaged line ------------------------------------------------


def _csi_line(seq: int = 610, mac: str = "16:01:cc:d5:06:18") -> str:
    iq = ",".join(["0", "0", "14", "9"] * 32)
    return (f'CSI_DATA,{seq},{mac},-36,9,0,0,0,0,0,0,0,0,0,-96,0,6,0,'
            f'402520000,0,28,0,128,0,"[{iq}]"')


def test_a_damaged_line_does_not_end_the_stream():
    """The requirement from the captured evidence: a malformed record must
    not cost the records that follow it."""
    parser = CsiParser()
    outcome = parser.feed_resilient(_csi_line(seq=1))
    assert len(outcome.records) == 1 and not outcome.malformed

    # the same line with its middle cut out and a status line spliced in
    damaged = _csi_line(seq=2)[:60] + "role=softap"
    outcome = parser.feed_resilient(damaged)
    assert outcome.malformed
    assert not outcome.records

    # the next good record is still parsed
    outcome = parser.feed_resilient(_csi_line(seq=3))
    assert len(outcome.records) == 1
    assert outcome.records[0].seq == 3
    assert not outcome.malformed


def test_both_records_survive_a_lost_newline():
    """A splice joins two records. Both are intact, and throwing one away
    would lose a measurement that was really made."""
    parser = CsiParser()
    spliced = _csi_line(seq=7) + _csi_line(seq=8)
    outcome = parser.feed_resilient(spliced)
    assert outcome.spliced, "the lost newline must be noticed"
    assert not outcome.malformed, "no data was lost"
    assert [r.seq for r in outcome.records] == [7, 8]
    assert all(len(r.iq) == 128 for r in outcome.records)


def test_a_status_line_spliced_into_a_csi_line_is_salvaged_as_text():
    parser = CsiParser()
    damaged = _csi_line(seq=9)[:50] + (
        "SPECTER_STAT,role=softap,peer=16:01:cc:d5:06:18,ch=6,rssi=-36,"
        "csi_cb=4221,printed=3859,drop_old=0,drop_new=0,q=0,q_high=13")
    outcome = parser.feed_resilient(damaged)
    assert outcome.malformed
    assert not outcome.records
    assert outcome.salvaged is not None
    assert outcome.salvaged.startswith("SPECTER_STAT,")
    st = parse_status_line(outcome.salvaged)
    assert st is not None and st["role"] == "softap"
    assert st["csi_callbacks"] == 4221


def test_the_damage_is_counted_and_the_sequence_gap_is_visible():
    """A lost record must show up as a gap, not be closed silently."""
    parser = CsiParser()
    parser.feed_resilient(_csi_line(seq=100))
    parser.feed_resilient(_csi_line(seq=102))     # 101 never arrived
    assert parser.gaps == 1
    assert parser.missing == 1


def test_a_line_with_one_record_is_not_a_splice():
    parser = CsiParser()
    outcome = parser.feed_resilient(_csi_line(seq=11))
    assert not outcome.spliced
    assert not outcome.malformed
