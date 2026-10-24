"""Read the Shrike Lite FPGA event snapshot over the internal 2-wire link.

This is a future bench script, not authorized to run yet. The board must be
reviewed and the FPGA design loaded first.

Physical assumption (manufacturer v1_r0.4/v1_r0.5 source):

  RP2040 GPIO14  -> FPGA F18  (read clock)
  FPGA F17       -> RP2040 GPIO15 (serial data)

These are internal board connections. Do not attach external wires to J2 pins
11, 12, 14 or 15. The snapshot is 64 bits:
``{event_count[31:0], last_timestamp[31:0]}``.

The FPGA reloads its shift register after at least 1 ms of read-clock idle,
then shifts on each rising edge. The host samples data while the clock is low.
"""

from machine import Pin
import time

RD_CLK_PIN = 14
RD_DATA_PIN = 15
LED_PIN = 4
SNAPSHOT_BITS = 64
IDLE_RESET_MS = 3
POLL_MS = 100


def read_snapshot(rd_clk, rd_data):
    rd_clk.value(0)
    time.sleep_ms(IDLE_RESET_MS)  # FPGA reloads its coherent snapshot.
    bits = 0
    for _ in range(SNAPSHOT_BITS):
        bits = (bits << 1) | rd_data.value()
        rd_clk.value(1)
        time.sleep_us(2)
        rd_clk.value(0)
        time.sleep_us(2)
    event_count = (bits >> 32) & 0xFFFFFFFF
    event_timestamp = bits & 0xFFFFFFFF
    return event_count, event_timestamp


def main():
    rd_clk = Pin(RD_CLK_PIN, Pin.OUT, value=0)
    rd_data = Pin(RD_DATA_PIN, Pin.IN)
    led = Pin(LED_PIN, Pin.OUT, value=0)
    print("host_us,event_count,fpga_ticks")
    last_count = None
    while True:
        event_count, event_timestamp = read_snapshot(rd_clk, rd_data)
        if event_count != last_count:
            led.toggle()
            last_count = event_count
        print("{},{},{}".format(time.ticks_us(), event_count, event_timestamp))
        time.sleep_ms(POLL_MS)


if __name__ == "__main__":
    main()
