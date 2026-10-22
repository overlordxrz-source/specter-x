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

## 9. Status at the pre-flash gate

All pre-flight checks passed. The write plan was two regions, the partition
table provably identical, the backup verified by two independent reads, and
the rollback commands hash-verified. At that point nothing had been written
to the board. **READY FOR FLASH AUTHORIZATION.** (Authorised and executed;
results below.)

---

# 10. Post-flash results

Written and verified on 2026-10-22 after explicit authorisation of the
two-region plan.

## 10.1 Write

| region | bytes | verification |
|---|---|---|
| `0x0` bootloader | 21 072 | `-- verify OK (digest matched)` |
| `0x10000` application | 745 056 | `-- verify OK (digest matched)` |

Untouched regions read back after the write **and after several boots**:

| region | SHA-256 (first 16) | unchanged |
|---|---|---|
| partition `0x8000`–`0x9000` | `b9118aa3840f7c04` | yes |
| NVS `0x9000`–`0xF000` | `7b78d61e4e2671f2` | yes |
| PHY `0xF000`–`0x10000` | `9749381a19fe46e3` | yes |

The partition table was not rewritten, and NVS was unchanged even after the
new firmware had booted — the firmware does not write to NVS.

## 10.2 Boot

`ESP-IDF v5.2.2 2nd stage bootloader`, **`SPI Flash Size : 16MB`**, **no**
"Detected size … larger than the size in the binary image header" warning,
`Loaded app from partition at offset 0x10000`, app `933e856-dirty`, compile
`03:45:27`, ELF SHA `9261de6e…` (matching the built image). No abort, no
watchdog, `Returned from app_main()`.

`specter_csi: flash: 16384 kB available at runtime, 16384 kB on the chip` —
**the flash defect is fixed at the bootloader, as diagnosed in 017.**

One provenance note: the flashed bootloader's embedded banner says
`01:44:31`, not `03:45`. `build-softap/bootloader/bootloader.bin` is an
incremental artefact retained from the previous session because no
bootloader input changed during the 03:45 build. It declares 16 MB, its
hash matches what was written and verified, and the running banner confirms
the 16 MB configuration.

Also noted: the 01:43 `build/` bootloader (`a17d5ca5…`) is a different
binary from the 01:44 `build-softap/` one (`36c01f50…`), which is consistent
with the app-provenance discrepancy in §2 — the two build trees were not
interchangeable.

## 10.3 WPA2, peer and DHCP

* `SoftAP 'SPECTER-LAB' on channel 6, WPA2`, DHCP server on `192.168.4.1`.
* The iPhone associated with the new passphrase — the definitive proof that
  the AP is WPA2-PSK, not merely configured as such.
* Peer: `de:1c:7e:d8:26:70` — an **iOS private Wi-Fi address**, so it differs
  from the `38:9c:b2:7e:37:a2` recorded in checkpoint 015. The firmware locks
  onto whatever MAC associates, so this is expected, but a reader comparing
  the two checkpoints should know the MAC changed by design on the phone.
* RSSI −48 to −55 dBm, channel 6, `amb=0` throughout.
* DHCP is established functionally: the ping traffic that produced the data
  frames below requires a leased address and a working ARP/ICMP path.

## 10.4 The v3 scored run — PASS

60 s, `--expect-rate 10`, phone pinging `192.168.4.1` at 100 ms.

| check | measured | result |
|---|---|---|
| csi callback activity | 25.1/s | PASS |
| packet continuity | **100.3% of 10/s (602 data frames)** | PASS |
| frame mix | **602 data, 900 null, 0 ambiguous** | PASS |
| data frame rate | 10.0/s | PASS |
| device vs host records | 1502 host, 1487 device (1.01%) | PASS |
| longest gap | 0.209 s | PASS |
| malformed / rescued / spliced | 0 / 0 / 0 | PASS |
| sequence gaps | 0 | PASS |
| RSSI | −48 dBm (−68…−43) | PASS |
| noise floor | −94 dBm | PASS |
| subcarrier nulls | 1502/1502 clean | PASS |
| active coverage | 52/52 slots | PASS |
| queue drops | 0 | PASS |
| usb vs console byte drift | 0.06% | PASS |
| flash size | 16 MB (chip 16 MB) | **PASS** |

This is the check that was failing before the bootloader write, now passing
on the same metric.

**Signal-length histogram:** `28 → 900`, `138 → 599`, `125 → 2`, `82 → 1`.
The payload frames are now **138 B**, against **122 B** in the checkpoint-016
trial. That is a 16-byte larger ICMP payload — independent evidence that the
traffic app changed between the two experiments, which is exactly the
confound recorded in 017 §5.

## 10.5 USB/UART integrity, analysed independently of the tool

| | console (CH343) | native USB-JTAG |
|---|---|---|
| bytes | 655 020 | 655 391 |
| records | 1 501 | 1 502 |
| head fields | 24 (all) | 24 (all) |
| IQ values | 128 (all) | 128 (all) |
| malformed | **0** | **0** |
| sequence gaps | **0** | **0** |
| sequence span | 2687–4187 | 2687–4188 |

The streams differ by exactly **one record — the final one (seq 4188)** —
which is present on the native path and absent from the console because the
console reader closed first. That is a capture-stop boundary, 0.057% of
bytes, not a mid-stream loss: both streams have zero internal gaps and zero
malformed records. The single-writer change is consistent with this result —
no torn or spliced line appeared in 60 s of dense output.

## 10.6 Evidence

| artefact | SHA-256 |
|---|---|
| `preflight-v3-phone.raw` (console) | `52f9fe583ebfa8302bd62d71df17da2dfadeeff12acf445d7e4f894aab0d6c5d` |
| `preflight-v3-phone.raw.csi` (native) | `5625eecbc3bc4235f0053a9688118c54703d05484cc07449905ce7ba879728e2` |
| `preflight-v3-phone.json` | `cfc4981e63e4992811ce6dadac150101c9fbc9aa1971309ab55260bdc111ae75` |

Also preserved: `boot-after-flash.raw`, `association-check.raw`,
`ap-state-20s.raw`, `preflight-prejoin.{raw,raw.csi,json}`,
`postflash-0x8000-0x10000.bin`, and the `rollback/` images — all under the
gitignored `runs/alpha002_hw_validation_20261022b/`.

## 10.7 What this proves, and what it does not

**Proven on hardware:** the hardened firmware boots; the runtime sees all
16 MB; WPA2 association with a real iPhone works; CSI records are produced
with correct subcarrier structure; the three counts are separated and close
exactly; the transport delivered 1 502 records with no malformed line and no
sequence gap.

**Not proven:** motion or vital-sign detection (nothing measured); sustained
unattended reliability (the phone is still the weak element); performance
superiority (no comparison); and the metadata/IQ-boundary splice remains
undetectable without a checksum.
