# ESP32-S3 Wi-Fi CSI firmware (Stage 3)

The board on the bench runs **Espressif's `csi_recv_router` example** and
streams Wi-Fi CSI over its native USB CDC port. This file records what the
hardware actually does, measured on 2026-10-21, and how the SPECTER-X
controlled-link build is produced and flashed.

> **Alpha 002-B (checkpoint 017).** This repository now also carries the
> SPECTER-X **controlled-link firmware**, in `softap_csi/`, with two roles:
> the board as a **station** (joining a local access point) and the board as
> a **SoftAP** (the Mac or a phone is the station). The SoftAP role is the
> one that has been run on hardware: its CSI callback fires, and a 60-second
> acquisition preflight passes. The lab network is **WPA2**, and the
> passphrase is **not in Git**. The build, the credential and the flash
> procedure are below.

## Building

The credential is read from the environment, and the build **fails closed**
without one — an accidentally open lab network is impossible by accident.

```bash
source ~/esp/esp-idf/export.sh

# once: create the credential (gitignored, mode 600, never printed)
.venv/bin/python tools/lab_credentials.py init

# export it for this shell (this line IS the secret - do not paste it)
eval "$(.venv/bin/python tools/lab_credentials.py env)"

# the SoftAP role - the board is the access point
idf.py -C firmware/esp32-csi/softap_csi \
  -B firmware/esp32-csi/softap_csi/build-softap \
  -D SDKCONFIG=sdkconfig.softap \
  -D SDKCONFIG_DEFAULTS="sdkconfig.defaults;sdkconfig.softap.defaults" build

# the station role - the board joins a local access point
idf.py -C firmware/esp32-csi/softap_csi \
  -B firmware/esp32-csi/softap_csi/build-station \
  -D SDKCONFIG=sdkconfig.station \
  -D SDKCONFIG_DEFAULTS="sdkconfig.defaults;sdkconfig.station.defaults" build
```

The generated `lab_credentials.h` lands in the **build** directory, never in
the source tree. The resulting app image contains the passphrase, so **the
image and any backup taken from it are secrets**; the backups taken before
Alpha 002-B contain no credential.

To build an open lab image on purpose: `-DSPECTER_LAB_ALLOW_OPEN=ON`.

## Flashing

The **runtime** flash size is set by the **bootloader's** image header, not
by the app's: the ROM gives the driver the size from the image it loads
first. The bootloader in this device was built for 2 MB, so the device ran
with 2 MB of a 16 MB chip even though the app image declared 16 MB. The
Alpha 002-B build produces a 16 MB bootloader, so **the bootloader has to be
written too** — an app-only write cannot fix it.

```bash
# read the current state first; the rollback base must be what we think
esptool --port /dev/cu.usbmodem1101 read-flash 0x0 0x10000 boot-check.bin

# write all three regions, then verify independently
esptool --port /dev/cu.usbmodem1101 --after hard-reset write_flash \
  --flash_mode dio --flash_freq 80m --flash_size 16MB \
  0x0      firmware/esp32-csi/softap_csi/build-softap/bootloader/bootloader.bin \
  0x8000   firmware/esp32-csi/softap_csi/build-softap/partition_table/partition-table.bin \
  0x10000  firmware/esp32-csi/softap_csi/build-softap/specter_csi_lab.bin

esptool --port /dev/cu.usbmodem1101 verify_flash \
  0x0      firmware/esp32-csi/softap_csi/build-softap/bootloader/bootloader.bin
```

**The app partition is 1 MB** and the app is 745 KB — it fits, with 29% to
spare. Growing it means writing the partition table at `0x8000`.

The device reports what it actually has, so the configuration can be checked
from its own output rather than from a warning in a log:

```
flash: 2048 kB available at runtime, 16384 kB on the chip
```

## Hardware (identified with read-only esptool)

| | |
|---|---|
| Chip | **ESP32-S3 (QFN56), revision v0.2** — Xtensa LX7, dual core + LP core, 240 MHz |
| PSRAM | **8 MB embedded (AP_3v3)** |
| Crystal | 40 MHz |
| USB mode | **USB-Serial/JTAG** (native USB; no bridge needed for the supervisor) |
| MAC | `14:c1:9f:26:52:ec` |
| Flash | **16 MB**, manufacturer `0x46`, device `0x4018`, quad (4 data lines), 3.3 V |
| Security | **secure boot disabled, flash encryption disabled**, all eFuse key blocks empty, `SPI_BOOT_CRYPT_CNT=0` |
| ROM | `esp32s3-20210327` (build 2021-03-27) |

### Toolchain (corrected)

**The ESP32-S3 is a Xtensa LX7 part.** Build with the Xtensa toolchain
(`xtensa-esp-elf`) and `idf.py set-target esp32s3`. The `riscv32-esp-elf`
toolchain that also ships with ESP-IDF is for the RISC-V parts (ESP32-C3, C6,
P4) and is **not** for the S3.

The running firmware was built with **ESP-IDF v5.2.2**, which is the version
installed on the bench machine, so the existing toolchain is already correct
for a rebuild.

## Running firmware

Read from the app descriptor at the factory app partition (`0x10000`):

| | |
|---|---|
| `project_name` | **`csi_recv_router`** (Espressif's `esp-csi` example) |
| `version` | `8633d67-dirty` (a git hash; the tree had uncommitted changes) |
| built | **2026-10-15 21:55:46** |
| `idf_version` | `v5.2.2` |
| image | ESP image, 5 segments, SPI mode 0x2 (DIO) |

## Flash layout

Single-slot OTA layout. Partition table at `0x8000`:

| Label | Type | Offset | Size |
|---|---|---|---|
| (OTA slot) | OTA | `0x009000` | 24 KB |
| (OTA slot) | OTA | `0x00f000` | 4 KB |
| `factory` | APP | `0x010000` | 1 MB |

Everything above `0x110000` is unused flash. **The CSI application is the
1 MB factory app at `0x10000`.**

## Measured wire format

One packet per line, terminated with **CRLF**. 24 comma-separated fields
followed by a quoted IQ tail:

```
CSI_DATA,10667,b8:62:1f:e5:ac:62,-60,9,0,0,0,0,0,0,0,0,-90,0,11,0,67768165,0,109,0,128,0,"[0,0,-3,-5,-5,-5,-6,-6,...]"
```

| Field | Observed | Meaning |
|---|---|---|
| 0 | `CSI_DATA` | tag |
| 1 | 10667 | **packet counter** — increments by exactly 1 per packet, so a host can detect gaps |
| 2 | `b8:62:1f:e5:ac:62` | source (AP) MAC, constant per AP |
| 3 | −60 | RSSI, dBm |
| 4 | 9 | primary channel |
| 5 | 0/1 | — |
| 6 | 0–6 | — |
| 7, 8 | 0 | constant |
| 9 | 0/1 | — |
| 10–12 | 0 | constant |
| 13 | 0/1 | — |
| 14 | −90 | constant (noise floor) |
| 15 | 0 | constant |
| 16 | 11 | constant (not the channel — field 4 varies while this does not) |
| 17 | 0 | constant |
| 18 | 67768165 | **µs timestamp** (`esp_timer_get_time`); ~6000 µs between packets at ~170 packets/s |
| 19 | 0 | constant |
| 20 | 64–1233 | varies widely (payload length?) |
| 21 | 0/1 | — |
| 22 | 128 | constant |
| 23 | 0 | constant |
| tail | `"[0,0,-3,-5,...]"` | the IQ pairs, quoted, one packet per line |

Fields that could not be named from observation are left positional on
purpose — a host parser must not invent meanings for them. Field 1 and field
18 are the two a host really needs: a gap-detecting counter and a device
clock.

Earlier revisions of this file described a `CSI,<timer>,<mac>,...` format.
**That was the planned format, not the measured one.** The tag is `CSI_DATA`
and the field layout is longer.

## Measured throughput

~170 CSI packets/s, ~73 KB/s on the native USB port.

## Backup and restore

The flash is **not encrypted and secure boot is off**, so the image can be
read in the clear and written back verbatim.

```bash
# backup, in chunks that the USB CDC link can actually carry
esptool --port /dev/cu.usbmodem1101 --after hard-reset \
         read-flash 0x0 0x40000 chunk.bin      # 256 KB per call
# restore
esptool --port /dev/cu.usbmodem1101 --after hard-reset \
         write-flash 0x0 esp32s3-csi-flash-backup-20261021-full.bin
```

**Chunking is mandatory.** A single 1 MB `read-flash` over the native USB
CDC link dies with *"Serial data stream stopped"*; 256 KB chunks are
reliable at ~1.2 Mbit/s. The 16 MB flash needs 64 chunk reads.

## Two roles, one board

The same ESP32-S3 is also planned to act as the **supervisor**: a device that
reports its own identity, uptime, heartbeat and health so SPECTER-X can show
that the board is alive. That role is specified in
`docs/checkpoints/003-alpha002a-esp32-supervisor.md`; its host half lives in
`specter/sensors/esp32/` and its firmware does not exist yet.

UART0 (the WCH CH343 bridge, `/dev/cu.usbmodem5B901602281`) was checked as a
possible second channel and is **not usable**: it carries a continuous
non-text binary stream that is neither the CSI packet format nor ESP-IDF log
output, and its origin is not established. The supervisor must therefore
share the one USB CDC port with CSI, and the host reader must tolerate both
packet types interleaved.
