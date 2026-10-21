# ESP32-S3 Wi-Fi CSI firmware (Stage 3)

Planned: ESP-IDF v5.x project based on Espressif's `esp-csi` examples
(https://github.com/espressif/esp-csi). The board runs as a station/sniffer,
enables `esp_wifi_set_csi(true)`, and streams one line per CSI callback over
USB-serial.

## Toolchain (corrected)

**The ESP32-S3 is a Xtensa LX7 part.** Build it with the Xtensa toolchain
(`xtensa-esp-elf`) and `idf.py set-target esp32s3`. The `riscv32-esp-elf`
toolchain that also ships with ESP-IDF is for the RISC-V parts (ESP32-C3,
C6, P4) and is **not** for the S3.

ESP-IDF v5.2.2 is installed on the bench machine with both toolchains
present, so nothing needs installing - only the correct target.

## Wire format

The format documented here was the *planned* one. The board that is actually
on the bench emits a different shape - measured from its native USB port
(Espressif 0x303A:0x1001):

    CSI_DATA,<esp_timer_us>,<mac>,<rssi>,<channel>,<len>,<noise>,<...>,"[<i0 q0 i1 q1 ...>]"

for example:

    CSI_DATA,7182,b8:62:1f:b4:a5:62,-73,11,1,4,0,0,1,0,0,0,1,-95,0,6,0,85322850,0,67,1,128,0,"[0,0,-8,4,-8,5,-8,5,..."

Differences from the original plan:

* the tag is `CSI_DATA`, not `CSI`;
* the field layout is longer than `timer,mac,rssi,channel,len` and the
  IQ pairs arrive as one quoted blob rather than a space separated tail.

A host parser must therefore be written against the **measured** format, not
the one below. The host side that consumes these lines
(`specter/sensors/wifi_csi`) has not been written yet.

## Two roles, one board

The same ESP32-S3 is also planned to act as the **supervisor**: a device
that reports its own identity, uptime, heartbeat and health over USB so
SPECTER-X can show that the board is alive. That role is specified in
`docs/checkpoints/003-alpha002a-esp32-supervisor.md` and its host half is
implemented in `specter/sensors/esp32/`; the firmware for it does not exist
yet.

The two workloads share one board and one USB CDC link, so the firmware
milestone has to decide whether they share a port. Until then, note that the
supervisor's packets (`HELLO` / `STAT` / `HB`) and the CSI packets
(`CSI_DATA`) are distinct and a host reader must tolerate both interleaved.
