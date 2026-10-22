# Checkpoint 014 — first hardware validation

**Date:** 2026-10-22
**Branch:** `feature/alpha002-esp32-supervisor`
**Verdict:** **FIRMWARE RUNS. SoftAP CSI emission UNPROVEN.** One application
partition written, verified twice. No rollback required. No station was ever
attached, so the record path is untested, not failed.

Evidence: `runs/alpha002_hw_validation_20261022/` (gitignored raw captures).

---

## 1. Authorisation and scope

Explicit authorisation was given for the flash-and-probe experiment in
checkpoint 013, with instructions to proceed one step at a time and to pause
before irreversible or unexpected operations.

Authorised: app-partition flash at `0x10000`, boot, SoftAP link test off the
campus network, CSI measurement, rollback if needed.
Not authorised, and not done: campus-gateway experiments, branch merge,
changes to unrelated software.

The step-4 join was **declined at the pause**, after two facts appeared that
were not in the preflight: the AP is open, and the Mac's only radio was on Kent
State Wireless. No network change was made on the host machine.

## 2. Pre-write verification

Everything below was read, not assumed.

| Check | Value |
|---|---|
| Device | ESP32-S3 QFN56 rev **v0.2**, 8 MB PSRAM, MAC `14:c1:9f:26:52:ec` |
| Flash | JEDEC `46 4018`, detected **16 MB**, quad, 3.3 V by eFuse |
| Second 16 MB backup | `esp32s3-csi-flash-backup-20261022-verify.bin`, **byte-identical** to the 2026-10-21 backup, both `51ae0968…602458f0` |
| App in flash at `0x10000` | `54ef5eeb…6c8a065` — identical to the rollback image |
| Bootloader entry at `0x0` | `0x403c9918`, unchanged |
| Partition table `0x8000` (0xC00) | `7f00b6c0…b7c820`, byte-identical to the new build |
| SoftAP image | 743 984 B, `a713864e…686af9fb` |
| Station image | 743 744 B, `78d5eb18…85d90b` |

The re-read backup matching the earlier one exactly also proves the flash
contents had not drifted in the intervening day.

## 3. What was written

Exactly one region, via `write_flash --flash_mode dio --flash_freq 80m
--flash_size 16MB 0x10000 specter_csi_lab.bin` at 115 200 baud.

- Erase range reported: `0x00010000`–`0x000c5fff` (the app partition only).
- 743 984 bytes, in-line hash verified.
- Independent `verify_flash` read-back: **`-- verify OK (digest matched)`**.
- Post-flash read of `0x0`–`0x9000` is **byte-identical** to the pre-flash
  backup: bootloader and partition table were not touched.

## 4. Boot

Captured on the CH343 console at 921 600 baud, raw bytes preserved.

```
I (182) boot: Loaded app from partition at offset 0x10000
I (194) cpu_start: Project name:     specter_csi_lab
I (194) cpu_start: App version:      95eae17-dirty
I (196) cpu_start: ESP-IDF:          v5.2.2
I (337) wifi:mode : softAP (14:c1:9f:26:52:ed)
I (340) specter_csi: SoftAP 'SPECTER-LAB' on channel 6, waiting for a station
I (341) esp_netif_lwip: DHCP server started on interface WIFI_AP_DEF with IP: 192.168.4.1
I (342) specter_csi: CSI enabled (LLTF only, 20 MHz, channel filter on)
I (342) specter_csi: SPECTER-X controlled-link firmware ready
I (343) specter_csi: the wire format is Espressif's csi_recv_router, unchanged
I (344) main_task: Returned from app_main()
```

No boot loop, no abort, no watchdog. The four things that had never executed
before — `esp_wifi_init`, SoftAP bring-up, AP netif, CSI enable — all executed.

## 5. What the CSI callback actually did

Two captures, no station attached, no campus traffic.

| Window | `csi_cb` | `printed` | `ch` | `peer` | drops | queue |
|---|---|---|---|---|---|---|
| first 25 s after boot | 0 → 2 | 0 | 0 | `-` | 0 | 0 |
| 120 s null baseline | 13 → 30 | 0 | 0 | `-` | 0 | 0 |

`csi_cb` rose monotonically, +17 events in 120 s (~0.14/s), with no station.
Source inspection confirms `s_csi_callbacks++` runs **before** the peer filter,
so these are genuine CSI callbacks, not a keep-alive counter.

`printed = 0` for the whole run. `s_last_channel` is only updated after a packet
is accepted, and `s_peer_mac` is only set by `WIFI_EVENT_AP_STACONNECTED`.
With no station, `peer_is()` returns false for every frame and the callback
returns early. This fully explains `ch=0`, `rssi=0`, `peer=-`, `printed=0`.

**Interpretation.** SoftAP-mode CSI is *not* dead: the callback is installed and
firing on ambient 2.4 GHz traffic on channel 6. What remains unproven is
everything downstream of the peer filter — whether an associated station
produces accepted records, correct channel metadata, sane RSSI, and a clean
CSI line on the wire.

## 6. Two defects found, neither fatal

1. **The SoftAP is open.** `CONFIG_SPECTER_LAB_PASSWORD=""` selects
   `WIFI_AUTH_OPEN`. This conflicts with the instruction to use secured local
   networking. It is baked into the verified image, so it was not changed
   mid-experiment. Fix before any further sharing of this AP.
2. **App image header advertises no flash size.** The runtime falls back to
   2 MB and logs `Detected size(16384k) larger than the size in the binary
   image header(2048k)` on every boot. Harmless here — the app partition is
   1 MB at `0x10000` — but the build should declare 16 MB properly.

## 7. Rollback

Not used. The firmware did not fail, so exercising the rollback path would have
destroyed working state for no evidence.

All three levels remain available and verified from this session:

1. App-only write of `esp32s3-csi-app-original.bin` (`54ef5eeb…`) at `0x10000`.
2. Full 16 MB restore from a backup that verified byte-identical twice.
3. ROM download mode via the UART bridge, which was used repeatedly today.

None of them depends on the new firmware running.

## 8. State at the end of this checkpoint

- Board: running the new SoftAP firmware, `SPECTER-LAB` on channel 6, isolated,
  open, no uplink.
- Host: still on Kent State Wireless; no interface, route or sharing change.
- Repository: working tree gains this checkpoint only; `main` untouched.
- SoftAP CSI question: **narrowed, not closed.**

## 9. The one honest sentence

The firmware boots and the radio works; whether it produces usable CSI records
for a real peer is still an open question, and it is the only question that
matters for Alpha 002.
