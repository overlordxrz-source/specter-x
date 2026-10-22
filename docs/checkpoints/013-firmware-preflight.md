# Checkpoint 013 — firmware preflight

**Date:** 2026-10-22
**Branch:** `feature/alpha002-esp32-supervisor`
**Verdict:** **READY — conditional.** Nothing flashed, nothing erased, nothing
merged, no hardware reset. The 16 MB backup still verifies.

Full detail: [`docs/design/flash-preflight-and-rollback.md`](../design/flash-preflight-and-rollback.md).

---

## 1. The review changed the firmware

Six defects, all of which compiled with zero errors. This is the reason the
preflight exists.

| # | Defect | Consequence if flashed |
|---|---|---|
| 1 | **No `esp_wifi_init()`** | every `esp_wifi_*` returns `ESP_ERR_WIFI_NOT_INIT`, `ESP_ERROR_CHECK` aborts → **boot loop** |
| 2 | **Every CSI line had two closing quotes** (`]""`) | the host parser rejects or mis-parses every packet |
| 3 | **SoftAP role created the station netif** | no AP IP stack, no DHCP → the Mac associates and gets no address, which looks exactly like "CSI does not work in AP mode" |
| 4 | **The SoftAP role had never been built** | `-D SDKCONFIG_DEFAULTS` is ignored when `sdkconfig` exists; both build dirs held station images (checkpoint 012's claim was wrong) |
| 5 | **A clean build produced ESP32 images** | bootloader at 0x1000, entry point `0x4008xxxx` — wrong chip, would not boot |
| 6 | Flash size declared 2 MB on a 16 MB part | bootloader header would describe the wrong part |

Also fixed: no reconnect after a disconnect (the campus link's 5-minute
silence must not be inherited), `esp_event_base_t *` instead of
`esp_event_base_t` (6 warnings), `printed` reporting the accepted rather than
the written count, a missing `<stdlib.h>`.

Both roles now build with **zero warnings, zero errors**.

## 2. Compatibility with the exact hardware

| | |
|---|---|
| Target | `esp32s3`, entry point `0x403753b0` |
| Running image | `csi_recv_router`, `8633d67-dirty`, **idf_ver v5.2.2** (parsed from the backup) |
| Build toolchain | ESP-IDF **v5.2.2** — the same |
| Bootloader entry point | `0x403c9918` in **both** the running image and the new build |
| Partition table | **byte-identical** to the running image |
| Console | UART0 GPIO43/44 @ **921600** *and* secondary USB-Serial/JTAG |
| App size | 743 984 B (SoftAP) / 743 744 B (station) of 1 048 576 B — **29 % free** |

Because the bootloader and the table already match, the flash plan writes
**one region: the app at `0x10000`**. Nothing else on the board changes, so
the rollback is one 1 MB write.

## 3. SoftAP without Internet Sharing — yes

The board is the access point. It holds `192.168.4.1` and runs its own DHCP
server; the Mac joins `SPECTER-LAB` directly and pings the board. No uplink,
no router, no sharing, nothing on the campus network. macOS reports "No
Internet Connection", which is true and irrelevant.

Internet Sharing is needed only for the **station fallback**, where the Mac
must become the access point.

## 4. The test, and its thresholds

`tools/esp32_lab_preflight.py` reads both USB paths for 60 s and scores:
callback activity (≥ 5/s), **callback fires at all** (the SoftAP probe),
continuity (≥ 95 % of the expected rate), longest gap (≤ 1 s), malformed (0),
sequence gaps (0), RSSI (−85…−15 dBm), noise floor (≤ −80 dBm), single
channel, 52 used subcarriers (≥ 99 % of records), queue drops (0), and
USB/console byte drift (≤ 0.5 %).

**Supervisor telemetry is DEFERRED**: `HELLO`/`STAT`/`HB` is not in this
image and was not added here. `SPECTER_STAT` is device status, deliberately a
different tag so it cannot be mistaken for supervisor state.

The scoring logic is tested against a healthy link, a dead callback, a USB
stall, queue loss, a wrong subcarrier map, a silent console, and a missing
status line (`tests/test_lab_preflight.py`, 8 tests). It can say FAIL.

## 5. Rollback

1. **App only** — `~/Downloads/esp32s3-csi-app-original.bin` (1 048 576 B,
   `sha256 54ef5eeb…6c8a065`), extracted from the verified backup, written to
   `0x10000`. ≈ 90 s.
2. **Full 16 MB** — the backup at `0x0`, then read back 0x0–0x110000 and
   compare. ≈ 23 min.
3. **Download mode** — hold BOOT, tap RESET, release; or
   `--before usb-reset` on the native port. The ROM loader does not depend on
   the app, so a boot loop is recoverable.

## 6. What was verified about the backup

```
~/Downloads/esp32s3-csi-flash-backup-20261021-full.bin
  16 777 216 B, mtime 21 Oct 17:24 (unchanged)
  sha256 51ae09689e19217aa52ff7d136313d2354345f9faf42ec50ee75324e602458f0  ✓
```

## 7. Still not claimed

* The firmware **has never executed**. "READY" means *safe to attempt with a
  verified rollback*, not *known to work*.
* **SoftAP-mode CSI on the ESP32-S3 remains unknown.** The probe answers it
  in 60 seconds; it is the main open question.
* No supervisor telemetry in this image (deferred, not forgotten).
* The two-board option is still blocked on the second board.
* No motion or vital-sign claim of any kind.

## 8. Next action

Awaiting authorization to run §9 of the preflight document: second backup,
app-only flash of the SoftAP image, join `SPECTER-LAB`, and answer the
capability question.
