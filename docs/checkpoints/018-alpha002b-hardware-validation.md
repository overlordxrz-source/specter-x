# Checkpoint 018 — Alpha 002-B hardware validation (pre-flash record)

**Date:** 2026-10-22
**Branch:** `feature/alpha002-esp32-supervisor` @ `a5d25d3`
**Authorisation:** controlled hardware validation of `a5d25d3`, following
checkpoint 017, staged, with an explicit pause before the bootloader write.
**Status at the time of writing:** **READY FOR FLASH AUTHORIZATION.**
Nothing on the board has been flashed, reset, erased or modified.

Every number below was measured in this session, not carried over.

---

## 1. Identity

| | measured |
|---|---|
| Chip | ESP32-S3 (QFN56), revision **v0.2** |
| PSRAM | 8 MB embedded (AP_3v3) |
| Crystal | 40 MHz |
| MAC | `14:c1:9f:26:52:ec` |
| Flash | JEDEC `46 4018`, **16 MB**, detected 16 MB |
| Flash mode in eFuse | quad (4 data lines), 3.3 V |
| Download mode | reachable on **both** ports (native USB-Serial/JTAG and CH343 at 921600) — recovery does not depend on the BOOT button |

## 2. What is on the board, and a provenance discrepancy

The bootloader (`0x0`), partition table (`0x8000`), NVS (`0x9000`–`0xF000`)
and PHY (`0xF000`–`0x10000`) are **byte-identical** to the verified backup
`51ae0968…`. Only the application region differs from that backup, because
the app was replaced in the previous session.

**The discrepancy, recorded rather than smoothed over:** the running
application is an Alpha 002 build whose own descriptor says
`95eae17-dirty`, built **2026-10-22 01:44:15**. The archived artefact
`firmware/esp32-csi/softap_csi/build/specter_csi_lab.bin` is a *different*
binary — same commit string, built **01:43:29** (`elf_sha 6df7cbd4…` against
the device's `a1c9942a…`). 684 747 of 743 744 bytes differ.

So the archived build artefact is **not** the exact image that is running.
The exact running image is preserved instead as flash bytes
(§5), which is the stronger form of preservation: it is what the device
actually held. This does not affect the validation — the board is running
Alpha 002 firmware, and Alpha 002-B replaces it wholesale — but the record
should not claim the archived binary is the running one.

## 3. Images to be written, and rollback compatibility

| property | bootloader | application |
|---|---|---|
| path | `build-softap/bootloader/bootloader.bin` | `build-softap/specter_csi_lab.bin` |
| size | 21 072 B | 745 056 B |
| SHA-256 | `36c01f506c2916da9b45b26204afc40c27c247634ba6cb2e8a96a15a810e84bf` | `77313e00af7c5b570b32a5910d5112e34979323ced667f2a910b12b17773c5ae` |
| header flash size | **16 MB** (`0x4F` = dio, 80 MHz, 16 MB) | **16 MB** |
| checksum / SHA-256 in image | valid | valid |

* the app occupies `0x10000`–`0xC5E60` inside a factory partition of
  `0x10000`–`0x110000` (1 MB), leaving **303 520 B** free, so it fits with
  room for the rollback image;
* the **partition table is byte-identical** to the one on the device
  (`7f00b6c4…` over its 3072-byte table; the remaining 1024 B of the 4 KB
  region is `0xFF`), so writing `0x8000` would change nothing;
* secure boot **off**, flash encryption **off**, eFuse flash mode quad/3.3 V
  — no encryption or mode mismatch between the images and the chip;
* the new code is confirmed present in the image (strings `WPA2`,
  `flash: %u kB available at runtime`, `,rej=%lu`), so it is not a stale
  artefact;
* provenance of the build: it postdates every firmware source file, and the
  working tree equals `a5d25d3`. The embedded version string reads
  `933e856-dirty` only because the build ran minutes before the commit.

Compatibilities checked:

* bootloader 21 072 B fits the `0x0`–`0x8000` window;
* the bootloader's partition-table offset is `0x8000`, matching the device;
* the original application is exactly 1 048 576 B and fits the same
  partition, so rollback needs no layout change;
* rollback of the bootloader alone is safe: the original 2 MB-header
  bootloader will boot either app, and the new 16 MB-header bootloader will
  also boot the original app (the app header size is advisory to the ROM,
  and the image validates on its own checksum).

## 4. Credential hygiene

* the credential lives in `firmware/esp32-csi/softap_csi/lab.env`, mode
  **600**, gitignored; SSID `SPECTER-LAB`, passphrase length 20 (WPA2 wants
  8–63);
* the passphrase appears in **no tracked file in any commit**;
* no `.bin` or build artefact is tracked; the generated
  `lab_credentials.h` exists only under the gitignored build tree;
* the new application image **does** contain the passphrase, by design, so
  **the image and any backup of it are secrets** and stay gitignored;
* the pre-flash backup of the *current* state (`aae96f58…`) contains the
  Alpha 002 image, which was built with an empty password, so it is **not**
  credential-bearing. It must still be handled as lab data.

## 5. Backup of the current state — integrity verified

`…/Downloads/esp32s3-csi-preflash-20261022b-full.bin`, 16 777 216 bytes,
SHA-256 `aae96f58a3841b4ec6e640356077a292232ce3faa7a239a6011b31a00d222458`.

**Two independent reads, on two different ports, agree** on the whole used
region: the CH343 16 MB read and the earlier native-USB read of
`0x0`–`0x110000` are byte-for-byte identical (`3e071f3e…`). That is the
integrity check that matters: a single bad read cannot silently become the
rollback base.

Region hashes inside the backup:

| region | SHA-256 (first 16) | note |
|---|---|---|
| bootloader `0x0`–`0x8000` | `1e9791f71ef7ecc4` | original, 2 MB header |
| partition `0x8000`–`0x9000` | `b9118aa3840f7c04` | table identical to the build's |
| NVS `0x9000`–`0xF000` | `7b78d61e4e2671f2` | untouched by the write |
| PHY `0xF000`–`0x10000` | `9749381a19fe46e3` | untouched by the write |
| app `0x10000`–`0x110000` | `a53df7ae1e308cdc` | the exact running image |

**One fact worth recording:** the flash is not empty beyond the declared
partitions. `0x110000`–`0x143EA0` holds 212 640 bytes of non-`0xFF` data
(3 689 short runs) outside every partition. It is unused by the bootloader
and by any partition, it is preserved in the backup, and the write below
does not touch it. If the app partition is ever enlarged, that region would
need re-examination first.

## 6. The exact write plan

Two regions. No chip erase, no `erase_flash`, no partition-table write.

| # | region | content | bytes | sectors erased |
|---|---|---|---|---|
| 1 | `0x000000` | new bootloader (16 MB header) | 21 072 | `0x0`–`0x6000` |
| 2 | `0x010000` | new application | 745 056 | `0x10000`–`0xC6000` |

```bash
esptool.py --port /dev/cu.usbmodem1101 --baud 460800 \
  --before default_reset --after hard_reset \
  write_flash --flash_mode dio --flash_freq 80m --flash_size 16MB \
  0x0      firmware/esp32-csi/softap_csi/build-softap/bootloader/bootloader.bin \
  0x10000  firmware/esp32-csi/softap_csi/build-softap/specter_csi_lab.bin
```

Then, independently:

```bash
esptool.py --port /dev/cu.usbmodem1101 --baud 460800 verify_flash \
  0x0      firmware/esp32-csi/softap_csi/build-softap/bootloader/bootloader.bin
esptool.py --port /dev/cu.usbmodem1101 --baud 460800 verify_flash \
  0x10000  firmware/esp32-csi/softap_csi/build-softap/specter_csi_lab.bin
```

The bootloader header already declares dio / 80 MHz / 16 MB, so esptool's
flash-parameter patch at `0x0` is a no-op; the file hash is the flash
content.

**What is provably untouched:** the write ranges end at `0x6000` and
`0xC6000`. The partition table (`0x8000`), NVS (`0x9000`–`0xF000`), PHY
(`0xF000`–`0x10000`) and everything from `0x110000` onward are outside both
ranges and outside every erased sector. Immediately after the write, before
the first boot, `0x8000`–`0x10000` will be read back and compared with the
backup to prove it. (After the new firmware boots, NVS may legitimately
change as the Wi-Fi driver stores calibration data; that is runtime
behaviour, not a write-side effect, and will be reported as such.)

## 7. Rollback

Material extracted from the verified backup, kept in the gitignored
`runs/alpha002_hw_validation_20261022b/rollback/`:

| file | bytes | SHA-256 |
|---|---|---|
| `bootloader-preflash-2mb.bin` | 32 768 | `1e9791f71ef7ecc4487de017f7318937876b1762b8d9845412316285611cca52` |
| `app-preflash-alpha002-95eae17.bin` | 1 048 576 | `a53df7ae1e308cdc56e41d1dd7b1b56ebd2307e522995923b35c08931299d936` |
| `partition-preflash-0x8000.bin` | 4 096 | `b9118aa3840f7c042a4dea8dae339d07a6e69f3716102174cc87b18046276295` |

**Return to the exact pre-validation state** (original bootloader + the
Alpha 002 image that is running now):

```bash
# 1. bootloader. --flash_size 2MB is REQUIRED: esptool patches the header of
#    the image written at 0x0, and 2 MB is what the original header declares,
#    so the patch reproduces the original bytes instead of quietly upgrading
#    the rollback image to a 16 MB header.
esptool.py --port /dev/cu.usbmodem1101 --baud 460800 \
  write_flash --flash_mode dio --flash_freq 80m --flash_size 2MB \
  0x0 runs/alpha002_hw_validation_20261022b/rollback/bootloader-preflash-2mb.bin

# 2. application
esptool.py --port /dev/cu.usbmodem1101 --baud 460800 \
  write_flash --flash_mode dio --flash_freq 80m --flash_size 16MB \
  0x10000 runs/alpha002_hw_validation_20261022b/rollback/app-preflash-alpha002-95eae17.bin
```

**Return to the factory application** (bootloader as above, then the
original Espressif image, `54ef5eebe09a0a3d…`, 1 048 576 B):

```bash
esptool.py --port /dev/cu.usbmodem1101 --baud 460800 \
  write_flash --flash_mode dio --flash_freq 80m --flash_size 16MB \
  0x10000 /Users/overlord/Downloads/esp32s3-csi-app-original.bin
```

**Full restore** if the flash is ever damaged beyond those regions: write
the 16 MB backup at `0x0` (this rewrites every partition, including NVS, so
it is the last resort, not the first).

The partition table never changes, so it needs no rollback. All rollback
files are hash-verified against the backup they came from, and each write is
followed by `verify_flash` against the same file.

## 8. Acceptance checks for the write and the boot

1. `verify_flash` matches for both images.
2. `0x8000`–`0x10000` read back byte-identical to `b9118aa3…`/`7b78d61e…`/
   `9749381a…` — the partition table, NVS and PHY were not touched.
3. Boot log shows `flash: 16384 kB available at runtime, 16384 kB on the
   chip` and **no** "Detected size … larger than the size in the binary
   image header" warning.
4. The SoftAP comes up as WPA2; the phone joins with the passphrase and gets
   an address on `192.168.4.0/24`.
5. The status line carries `rej=`, `data=`, `null=`, `amb=`,
   `flash_kb=16384`, `flash_phys_kb=16384`.
6. The v3 preflight passes with `flash size` **PASS** — the check that was
   failing — and `0 ambiguous` frames.

## 9. Status

All pre-flight checks passed. The write plan is two regions, the partition
table is provably identical, the backup is verified by two independent
reads, and the rollback commands are hash-verified. **Nothing has been
written to the board.**

**READY FOR FLASH AUTHORIZATION.**
