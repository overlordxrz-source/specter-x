"""Bounded readout for the SPECTER-SYNC Shrike Lite event counter.

This is a future physical-bench script, not authorized to run yet. It never
loads an FPGA bitstream, changes factory files or configures the FPGA. It must
be used only after a separately authorized event-counter bitstream is already
loaded and the RP2040 owns the internal F17/F18 link.

Pin ownership assumed by the authorized staging sequence:

  RP2040 GPIO14 -> FPGA F18  (read clock; host output)
  FPGA F17      -> RP2040 GPIO15 (serial data; host input)

The FPGA reloads its snapshot after at least 1 ms of read-clock idle. If the
host pauses longer than that between rising edges, the shift register reloads
mid-read and the assembled word is a non-coherent mixture. This script
therefore measures the interval since the previous rising edge and aborts on a
gap above 250 us. It does not retry or reprogram automatically.

The event input F1 has no local bias resistor in the published PCB sources.
Counts are meaningful only when F1 is externally held at a defined 3.3 V CMOS
level under a separate electrical authorization. Do not connect external
wires to J2 pins 11/12/14/15; the F17/F18 links are internal.
"""

from machine import Pin
import time

RD_CLK_PIN = 14
RD_DATA_PIN = 15
LED_PIN = 4
SNAPSHOT_BITS = 64
IDLE_RESET_MS = 3
MAX_BIT_GAP_US = 250
POLL_MS = 100


class ReadoutError(RuntimeError):
    pass


def read_snapshot(rd_clk, rd_data, *, max_gap_us=MAX_BIT_GAP_US):
    """Read one 64-bit snapshot with bounded edge spacing.

    The host samples data while the clock is low, then raises and lowers it.
    A gap above ``max_gap_us`` since the previous rising edge would risk the
    FPGA's 1 ms idle reload; the read is aborted rather than returning a
    possibly mixed snapshot.
    """
    rd_clk.value(0)
    time.sleep_ms(IDLE_RESET_MS)
    bits = 0
    last_rise = None
    try:
        for _ in range(SNAPSHOT_BITS):
            now = time.ticks_us()
            if last_rise is not None:
                gap = time.ticks_diff(now, last_rise)
                if gap < 0 or gap > max_gap_us:
                    raise ReadoutError(
                        "readout edge gap %d us exceeds %d us; snapshot discarded"
                        % (gap, max_gap_us)
                    )
            bits = (bits << 1) | rd_data.value()
            rd_clk.value(1)
            last_rise = time.ticks_us()
            time.sleep_us(2)
            rd_clk.value(0)
            time.sleep_us(2)
    finally:
        rd_clk.value(0)
    return (bits >> 32) & 0xFFFFFFFF, bits & 0xFFFFFFFF


def read_stable(rd_clk, rd_data, *, attempts=2, max_gap_us=MAX_BIT_GAP_US):
    """Read until two consecutive snapshots agree; no event source assumed."""
    previous = None
    for _ in range(attempts):
        current = read_snapshot(rd_clk, rd_data, max_gap_us=max_gap_us)
        if previous is not None and current == previous:
            return current
        previous = current
    raise ReadoutError("snapshot did not repeat; no-event baseline is not stable")


def main():
    rd_clk = Pin(RD_CLK_PIN, Pin.OUT, value=0)
    rd_data = Pin(RD_DATA_PIN, Pin.IN)
    led = Pin(LED_PIN, Pin.OUT, value=0)
    print("host_us,event_count,fpga_ticks")
    last_count = None
    while True:
        try:
            event_count, event_timestamp = read_snapshot(rd_clk, rd_data)
        except ReadoutError as exc:
            rd_clk.value(0)
            print("READOUT_ABORT:", exc)
            return 2
        if event_count != last_count:
            led.toggle()
            last_count = event_count
        print("{},{},{}".format(time.ticks_us(), event_count, event_timestamp))
        time.sleep_ms(POLL_MS)


if __name__ == "__main__":
    raise SystemExit(main())
