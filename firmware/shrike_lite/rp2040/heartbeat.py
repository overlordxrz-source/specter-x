"""Shrike Lite RP2040 proof-of-life (MicroPython).

This file is not to be flashed until the physical board revision, power and
toolchain are reviewed. It uses only the onboard RP2040 user LED on GPIO4.
"""

from machine import Pin
import time

LED_PIN = 4


def main():
    led = Pin(LED_PIN, Pin.OUT, value=0)
    print("SPECTER-SYNC Shrike Lite RP2040 heartbeat; LED=GPIO4")
    while True:
        led.toggle()
        print("heartbeat", time.ticks_ms())
        time.sleep_ms(500)


if __name__ == "__main__":
    main()
