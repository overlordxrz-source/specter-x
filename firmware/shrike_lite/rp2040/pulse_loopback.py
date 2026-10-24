"""Future RP2040 pulse-loopback source for SPECTER-SYNC Phase 0.

This is NOT an independent timing reference. It is only for checking that the
jumper, FPGA edge capture, event count and readout work. Do not run or connect
GPIO6 to FPGA F1 until the electrical setup is reviewed.

Default: 1 Hz, 10 ms high pulse on RP2040 GPIO6.
"""

from machine import Pin
import time

PULSE_PIN = 6
PERIOD_MS = 1000
HIGH_MS = 10


def main():
    pulse = Pin(PULSE_PIN, Pin.OUT, value=0)
    print("SPECTER-SYNC loopback pulse source; GPIO6; 1 Hz")
    while True:
        pulse.value(1)
        time.sleep_ms(HIGH_MS)
        pulse.value(0)
        time.sleep_ms(PERIOD_MS - HIGH_MS)


if __name__ == "__main__":
    main()
