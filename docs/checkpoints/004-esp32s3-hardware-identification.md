# SPECTER-X checkpoint 004 — ESP32-S3 hardware identification and recovery

**Date:** 2026-10-21
**Branch:** `feature/alpha002-esp32-supervisor` (pushed; **not** merged)
**Status:** the board is identified, its running firmware is identified, it was
recovered with a non-destructive restart, and its flash can be backed up and
restored. **Nothing was flashed, erased or modified.**

---

## 1. Exact hardware identity

Established with **read-only** esptool commands (`chip-id`, `flash-id`,
`get-security-info`) plus the USB descriptors.

| | |
|---|---|
| Chip | **ESP32-S3 (QFN56), revision v0.2** |
| Core | **Xtensa LX7** — dual core + LP core, 240 MHz (not RISC-V) |
| PSRAM | **8 MB embedded (AP_3v3)** |
| Crystal | 40 MHz |
| USB mode | **USB-Serial/JTAG** (native USB) |
| MAC | `14:c1:9f:26:52:ec` |
| Flash | **16 MB**, manufacturer `0x46`, device `0x4018`, quad, 3.3 V |
| ROM | `esp32s3-20210327` (build 2021-03-27) |
| Security | **secure boot disabled**, **flash encryption disabled**, all six eFuse key blocks `USER/EMPTY`, `SPI_BOOT_CRYPT_CNT=0x0` |

Two USB nodes belong to the board:

| Node | Identity | Use |
|---|---|---|
| `/dev/cu.usbmodem1101` | Espressif `0x303A:0x1001` "USB JTAG_serial debug unit" | **native USB CDC** — the CSI stream, and the supervisor's channel |
| `/dev/cu.usbmodem5B901602281` | WCH `0x1A86:0x55D3` "USB Single Serial" (CH343 family) | UART0 console, and the **only reliable flash transfer path** |

The USB descriptors alone (`0x303A:0x1001`) cannot distinguish an S2/S3 from a
C3/C6; `chip-id` settles it, and it says **S3**.

### Toolchain

The running firmware was built with **ESP-IDF v5.2.2** — the same version
installed on the bench machine — and the S3 must be built with
**`xtensa-esp-elf`** (`idf.py set-target esp32s3`). The `riscv32-esp-elf`
toolchain is for the C3/C6/P4 and is not used here.

---

## 2. Current firmware behaviour

Read from the ESP-IDF app descriptor at the factory app partition:

| | |
|---|---|
| `project_name` | **`csi_recv_router`** — Espressif's `esp-csi` example |
| `version` | `8633d67-dirty` (a git hash; the tree had uncommitted changes) |
| built | **2026-10-15 21:55:46** |
| `idf_version` | `v5.2.2` |

It is a **Wi-Fi CSI sniffer**: it streams one CSI callback per line over the
native USB CDC port at ~**170 packets/s (~73 KB/s)**.

### Flash layout (partition table at `0x8000`)

| Type | Offset | Size | Note |
|---|---|---|---|
| OTA | `0x009000` | 24 KB | |
| OTA | `0x00f000` | 4 KB | `phy_init` |
| APP | `0x010000` | 1 MB | **`factory` — the CSI application** |

Everything above `0x110000` is unused flash.

### Measured wire format

One packet per line, **CRLF**-terminated: 24 comma-separated fields plus a
quoted IQ tail.

```
CSI_DATA,10667,b8:62:1f:e5:ac:62,-60,9,0,0,0,0,0,0,0,0,-90,0,11,0,67768165,0,109,0,128,0,"[0,0,-3,-5,-5,-5,-6,-6,...]"
```

| Field | Observed | Meaning |
|---|---|---|
| 0 | `CSI_DATA` | tag |
| 1 | 10667 | **packet counter** — +1 per packet, so a host can detect gaps |
| 2 | `b8:62:1f:e5:ac:62` | source (AP) MAC |
| 3 | −60 | RSSI dBm |
| 4 | 9 | primary channel |
| 5–13 | 0/1 and constants | not identifiable from observation — left positional on purpose |
| 14 | −90 | constant (noise floor) |
| 15–17 | 0, 11, 0 | constant; field 16 is *not* the channel (field 4 varies, it does not) |
| 18 | 67768165 | **µs timestamp** (`esp_timer_get_time`); ~6000 µs between packets |
| 19 | 0 | constant |
| 20 | 64–1233 | varies widely (payload length?) |
| 21–23 | 0/1, 128, 0 | |
| tail | `"[0,0,-3,-5,...]"` | IQ pairs, quoted |

Fields that could not be named are left positional **on purpose** — a parser
must not invent meanings. The two a host actually needs are field 1 (a
gap-detecting counter) and field 18 (a device clock).

The earlier `CSI,<timer>,<mac>,...` format in the repo was the *planned* one,
not the measured one; `firmware/esp32-csi/README.md` has been corrected.

---

## 3. Recovery diagnostic

### What was wrong

At 16:26 the board **enumerated normally** but its native USB CDC port
delivered **zero bytes** — the same symptom as the DI-188 lockup in
checkpoint 003, on a completely different device:

* the USB device node was present with the correct VID:PID, product and serial;
* the CDC data path returned nothing in either direction;
* the CSI stream that had been running at 15:50 (270 KB in 6 s) had stopped.

### What fixed it

A **non-destructive restart**: esptool's `--after hard-reset` resets the chip
through the ROM. After that:

* the ROM log on UART0 showed `rst:0x15 (USB_UART_CHIP_RESET)` then
  `boot:0x8 (SPI_FAST_FLASH_BOOT)` — the application booted from flash
  normally, so the flash image was intact;
* the CSI streamer **resumed immediately**, at the same rate and in the same
  format as before.

So the fault was in the running application's USB state, not in the flash, and
a reset cleared it. No erase, no reflash, no firmware modification.

### The lesson worth carrying

**Two unrelated devices, the same symptom: the USB CDC data path went dead
while the device still enumerated.** For the DI-188 the software now treats
"opens but silent" as a distinct `SILENT` state with a bounded stall timeout
and a guaranteed port release. The same class of fault should be expected on
any USB-CDC instrument.

**Open question for the DI-188:** the SAMD21 also has a hardware reset path
(DTR/RTS, and the 1200-baud touch). The attempt made during checkpoint 003
used a DTR/RTS *sequence* at 1200 baud and did not recover it; the next thing
to try, when the instrument is reconnected, is a plain **1200-baud open with
DTR asserted** (the documented Arduino touch), then a bare DTR/RTS reset
pulse. This has not been tested, because the instrument is currently
disconnected.

---

## 4. Backup and restore

### Can it be done? Yes — and the procedure is now known.

Because **secure boot is off and flash encryption is off**, the image can be
read in the clear and written back verbatim.

**The native USB path is not usable for this.** A single `read-flash` of
1 MB dies with *"Serial data stream stopped"*; 256 KB chunks fail part-way
through; even 128 KB fails at some offsets, repeatedly. The failure is
**time-based, not offset-based**: the USB CDC link drops after roughly
**1.5 s** of continuous transfer, and the running CSI application leaves
stale bytes in the host's buffer that corrupt the next connection.

**The UART bridge works.** `esptool --port /dev/cu.usbmodem5B901602281
--baud 115200` reads reliably at ~87.6 kbit/s. 921600 does not work.

### Backups taken

| File | Region | Size | SHA-256 |
|---|---|---|---|
| `~/Downloads/esp32s3-csi-image-0x0-0x110000.bin` | `0x0`–`0x110000` (bootloader + partition table + the CSI app) | 1 114 112 B | `c99b6ab650d0ad4310c65fd4cd07dec8ee2429a2e73987b52458853d83b50833` |
| `~/Downloads/esp32s3-csi-flash-backup-20261021-full.bin` | the whole 16 MB | **16 777 216 B** | **`51ae09689e19217aa52ff7d136313d2354345f9faf42ec50ee75324e602458f0`** |

The full-flash backup was read as **128 chunks of 128 KB, every one of them
succeeding on the first attempt** over the UART bridge.

### Read-back integrity: **MATCH**

A fresh 16 KB read of `0x10000` (the start of the app partition) was taken
after the backup and compared with the same region of the backup file:

```
full image  : 16777216 bytes  sha256 51ae09689e19217aa52ff7d136313d2354345f9faf42ec50ee75324e602458f0
re-read     :     16384 bytes  sha256 21644cad048995a73ed9295494e3c7f7424cd3e0b43bd9f8a34889759f5bb31c
from backup :     16384 bytes  sha256 21644cad048995a73ed9295494e3c7f7424cd3e0b43bd9f8a34889759f5bb31c
READ-BACK MATCH
```

The backup is therefore a faithful copy of the device's flash and can be
written back verbatim.

### Restore procedure (not executed — it is a write)

```bash
# 1. put the chip in the bootloader
esptool --port /dev/cu.usbmodem5B901602281 --baud 115200 chip-id
# 2. write the image back (this ERASES and REWRITES - needs authorisation)
esptool --port /dev/cu.usbmodem5B901602281 --baud 115200 \
         write-flash 0x0 ~/Downloads/esp32s3-csi-image-0x0-0x110000.bin
# 3. the app reboots into the CSI streamer
esptool --port /dev/cu.usbmodem5B901602281 --baud 115200 --after hard-reset chip-id
```

`write-flash` erases the affected sectors before writing. It is a **write**
and has not been run. The backup is the safety net that makes a firmware
change recoverable.

### Backup integrity

Verified by read-back: a fresh 16 KB read of the app partition matches the
backup byte-for-byte (see §4). **The flash can be backed up and restored.**

---

## 5. Smallest path to combined CSI + supervisor telemetry

The supervisor's host half is done and tested (checkpoint 003). The missing
piece is firmware that emits `HELLO` / `STAT` / `HB`.

**Constraint: preserve CSI.** That rules out a separate supervisor application
— flashing one would destroy the CSI streamer, and the board has a single
1 MB app slot.

### Three options

| Option | Change | CSI risk | Verdict |
|---|---|---|---|
| **A. Host-only** | Derive supervisor telemetry on the host from the CSI stream: identity from the USB descriptor and the app descriptor in flash; liveness from the packet counter advancing | none | Works, but the "heartbeat" would be a **host-observed** liveness, not a device heartbeat, and **uptime is unavailable** (field 18 is a free-running timer, not uptime). It also breaks the rule that the device heartbeat and the network heartbeat are separate things — it would blur them. |
| **B. Fork the app** | Rebuild `csi_recv_router` with the supervisor packets added to the same stdout | low, but requires a rebuild of the CSI app | Works, but touches the CSI application for no good reason. |
| **C. One extra task in the existing app** | Add a single 1 Hz FreeRTOS task to the existing `csi_recv_router` build that prints `HELLO` once and `STAT`/`HB` every second **to the same stdout**. The CSI callback path is not touched at all. | **minimal by construction** — the CSI code path is unchanged, so the packet format and rate cannot change | **recommended** |

### Recommendation: Option C

* The CSI code path is **not modified**, so CSI functionality is preserved by
  construction rather than by testing. The only change is an added task that
  writes ~40 bytes/s into the same stream.
* The supervisor's identity comes from the app's own
  `esp_app_get_description()` (project, version, IDF version, build) plus
  `esp_read_mac()`; uptime from `esp_timer_get_time()` at boot; heap from
  `esp_get_free_heap_size()`; health from the heap and `esp_reset_reason()`.
* The host already tolerates interleaved packet types: the supervisor parser
  ignores lines that are not supervisor packets and counts them as malformed
  for the CSI reader. **Both readers must be taught to skip the other's
  packets** — that is a host-side change in the next milestone.
* The flash backup makes it recoverable: if the rebuilt app misbehaves, the
  original image is written back.

### Cost of Option C

One task, roughly 30 lines of C, in an existing ESP-IDF project that is
already buildable with the installed toolchain. The build source is Espressif's
`esp-csi` example at revision `8633d67` (the hash in the app descriptor); the
repo does not contain that source yet, so Alpha 002-B must vendor it.

---

## 6. What was NOT done

* No flash, no erase, no firmware modification, no `write-flash`.
* No reflash of the CSI application.
* The only state changes were **read-only esptool commands** and
  **non-destructive resets** (`--after hard-reset`), which the board recovered
  from immediately.

---

## 7. Blockers

1. **The ESP32-S3 source is not in the repo.** The running firmware is
   Espressif's `esp-csi` example at `8633d67` (built from a dirty tree). To
   add a task, that source has to be vendored — and the *dirty* state means
   the exact build cannot be reproduced without knowing what was changed.
2. **UART0 is not a usable second channel.** It carries a continuous
   non-text binary stream that is neither the CSI format nor ESP-IDF log
   output, and its origin is not established. The supervisor must share the
   USB CDC port.
3. **The flash backup over USB is unreliable**; the UART path is slow
   (~87.6 kbit/s, ~25 min for the full 16 MB) but works.
4. **The DI-188 is still disconnected**, so the DI-188 acceptance test
   skips, and the 1200-baud/DTR reset hypothesis for its lockup is untested.
5. **Both branches remain unmerged.** `main` is untouched at `b5e1875`.
