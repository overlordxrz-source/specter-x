# Firmware preflight: flash plan, hardware test, rollback

**Date:** 2026-10-22
**Branch:** `feature/alpha002-esp32-supervisor`
**Verdict:** **READY — conditional.** Nothing has been flashed. This document
is the review that had to happen first, and it changed the firmware.

> **What "READY" means here.** Safe to *attempt* the first flash, because the
> recovery path does not depend on the new firmware working and the original
> image can be restored byte for byte. It does **not** mean the firmware is
> known to work: it has still never executed on hardware.

---

## 1. What was verified, and how

| Check | Result | Method |
|---|---|---|
| Original 16 MB backup | **intact** — 16 777 216 B, `sha256 51ae0968…602458f0` | `shasum` against the recorded value; file mtime unchanged (21 Oct 17:24) |
| Running image identity | `csi_recv_router`, version `8633d67-dirty`, **idf_ver v5.2.2**, built 15 Oct 2026 21:55:46 | parsed from the app descriptor inside the backup (read-only) |
| Build toolchain | **ESP-IDF v5.2.2**, `xtensa-esp-elf 13.2.0_20230928` | `idf.py --version`, `xtensa-esp32s3-elf-gcc --version` |
| Target | `esp32s3` — entry point `0x403753b0` | `esptool image_info` on the built app |
| Bootloader compatibility | new bootloader entry `0x403c9918` **identical** to the running image's | header parse of both |
| Partition layout | **byte-identical** to the running image: `nvs` 0x9000/24 K, `phy_init` 0xF000/4 K, `factory` 0x10000/1 M | 0xC00-byte compare at 0x8000 |
| Flash geometry | DIO, 80 MHz, **16 MB** (matches the verified part) | sdkconfig + image headers |
| App fit | 743 744 B of the 1 048 576 B partition — **29 % free** | `check_sizes.py` |
| Console paths | UART0 (GPIO43/44) **@ 921600** *and* secondary USB-Serial/JTAG — the same dual path the 40-minute capture used | generated sdkconfig |
| Serial nodes present | `/dev/cu.usbmodem1101` (native), `/dev/cu.usbmodem5B901602281` (CH343) | `ls /dev/cu.*` |
| Wire format | the **actual C formatter**, compiled on the host, parsed by the **actual** Python parser | `tests/test_firmware_format_native.py` |
| Test suite | **278 passed, 1 skipped** | `pytest` |

---

## 2. The defects this review found

This is the part that matters. Every one of these compiled cleanly, and the
first two would have wasted the flash session.

### 2.1 The SoftAP role was never built

`idf.py -D SDKCONFIG_DEFAULTS=…` only applies defaults **when the sdkconfig
file does not exist**. It existed, so the second build silently reused the
station configuration. The "SoftAP" binary in `build-softap/` was a second
station binary, and checkpoint 012's claim that both roles compile was wrong.

**Fixed:** each role now has its own `SDKCONFIG` *and* its own defaults file.

### 2.2 A clean build produced ESP32 images, not ESP32-S3 images

With `sdkconfig` deleted, `idf.py` has no target and defaults to `esp32`:

```
-- IDF_TARGET not set, using default target: esp32
0x1000 bootloader/bootloader.bin     <- wrong offset for the S3
Entry point: 4008125c                <- ESP32 address range
```

Flashing that would have written a bootloader at the wrong offset and an app
for the wrong chip. It compiled with **zero errors**, which is exactly why
"I built it" is not a preflight.

**Fixed:** `CONFIG_IDF_TARGET="esp32s3"` is in `sdkconfig.defaults`, and the
build log is now checked for `Building ESP-IDF components for target esp32s3`.

### 2.3 No `esp_wifi_init()` — the board would have boot-looped

`esp_wifi_set_mode()` was called straight after `esp_netif_init()`. Without
`esp_wifi_init()` every `esp_wifi_*` call returns `ESP_ERR_WIFI_NOT_INIT`, and
`ESP_ERROR_CHECK` aborts: the board would reset in a loop, forever.

The upstream example hid this: it called `example_connect()`, which does the
init. Our firmware is standalone and never did.

**Fixed:** `esp_wifi_init()` + `esp_wifi_set_storage(WIFI_STORAGE_RAM)` before
any configuration, and a contract test that fails if the order regresses.

### 2.4 The SoftAP role created the station netif

`esp_netif_create_default_wifi_sta()` was called unconditionally. In the AP
role that leaves the access point with **no IP stack and no DHCP server**, so
the Mac would associate and then never get an address — which looks exactly
like "the CSI callback doesn't work", i.e. it would have corrupted the very
experiment this build exists to run.

**Fixed:** the netif is chosen by role.

### 2.5 Every CSI line had two closing quotes

The formatter closed the quoted IQ tail (`]"`), and the writer appended
another `"`. Every line would have ended `]""` and the host parser would have
had to reject it.

**Fixed**, and now checked by running the C formatter rather than reading it:
`tests/test_firmware_format_native.py` compiles `csi_output.c` with a
two-line FreeRTOS stub and feeds its bytes to `CsiParser`.

### 2.6 Smaller things, fixed in the same pass

| | |
|---|---|
| flash size declared 2 MB on a 16 MB part | now 16 MB |
| no reconnect after a disconnect | reconnects and logs it — the campus link's 5-minute silence must not be inherited |
| `esp_event_base_t *` instead of `esp_event_base_t` | 6 "distinct pointer types" warnings, gone |
| `printed` in the status line reported the *accepted* count | now reports what actually reached the wire |
| `dq_ring.c` used `calloc` without `<stdlib.h>` | included |

Both roles now build with **zero warnings and zero errors**.

---

## 3. The flash plan: app only

Write **one region**, at `0x10000`. Not the bootloader, not the partition
table.

| Region | Offset | Write it? | Why |
|---|---|---|---|
| bootloader | `0x0000` | **no** | running one is IDF v5.2.2 and its entry point is identical to the new build's |
| partition table | `0x8000` | **no** | byte-identical to what is already there — writing it would be a no-op with risk and no benefit |
| `nvs` / `phy_init` | `0x9000`, `0xF000` | **no** | untouched; the new firmware keeps Wi-Fi state in RAM and does not write to flash |
| factory app | `0x10000` | **yes** | this is the whole change |

This is the smallest possible change to the board, and it makes the rollback
a single 1 MB write.

### Exact commands

```bash
cd /Users/overlord/sideprojects/specter-x/firmware/esp32-csi/softap_csi
BRIDGE=/dev/cu.usbmodem5B901602281     # the CH343 bridge; esptool at 115200

# 0. a second backup, before anything (repeatable, 16 MB)
esptool --port $BRIDGE --baud 115200 read-flash 0x0 0x1000000 /tmp/backup-preflash.bin
shasum -a 256 /tmp/backup-preflash.bin
#    must equal 51ae09689e19217aa52ff7d136313d2354345f9faf42ec50ee75324e602458f0

# 1. write the app only
esptool --port $BRIDGE --baud 115200 write-flash 0x10000 build-softap/specter_csi_lab.bin

# 2. prove what is on the board now matches what was built
esptool --port $BRIDGE --baud 115200 verify-flash 0x10000 build-softap/specter_csi_lab.bin
#    sha256 a713864ec11927f164eef5dc9a9fa9936b60067572bb6ac0fbb178ef686af9fb
```

`write-flash` at 115200 takes about 90 s for 743 KB. The baud is deliberately
low: 921600 does not work for esptool on this bridge, and reliability matters
more than speed on the one operation that changes the board.

Use `build-softap/` for the SoftAP role (the capability probe) and `build/`
for the station role:

| Role | Binary | Size | SHA-256 |
|---|---|---|---|
| SoftAP | `build-softap/specter_csi_lab.bin` | 743 984 B | `a713864e…686af9fb` |
| Station | `build/specter_csi_lab.bin` | 743 744 B | `78d5eb18…85d90b` |
| Original app (rollback) | `~/Downloads/esp32s3-csi-app-original.bin` | 1 048 576 B | `54ef5eeb…6c8a065` |

---

## 4. SoftAP with no Internet Sharing — yes

**This is the answer to the question that decides the lab design.** The board
in the SoftAP role *is* the access point. It runs the AP netif, which gives it
`192.168.4.1` and runs a DHCP server. The Mac joins the SSID like any other
network. There is no uplink, no router, no Internet Sharing, and nothing on
the campus network is involved.

```
   Mac (station)  ──802.11──  ESP32-S3 (SoftAP, 192.168.4.1)
        │                            │
        └── ping 192.168.4.1 ────────┘   the controlled stimulus
```

* macOS will say **"No Internet Connection"**. That is correct and harmless;
  it stays associated, because association and reachability are different
  things.
* DHCP is the board's own (`192.168.4.x`), so the ping is on-link: no route,
  no DNS, no internet.
* **The stimulus is the Mac's own traffic.** `ping -i 0.05 192.168.4.1` gives
  20 uplink frames a second, each with a preamble the board measures. The
  packet rate is chosen by us, which is the property the campus link never
  had.

**Caveats, all of which are physical, not software:**

1. Joining the board's SSID **takes the Mac off its current network**. If this
   session is over the network, the commands have to be run from a local
   terminal.
2. macOS may ask for confirmation before joining a network with no internet.
   Accept it; the board is the network.
3. macOS uses a **private (randomised) Wi-Fi address** per network by default.
   The firmware learns the station MAC from the association event, so the
   filter works either way — but the address must be recorded with the run,
   because it changes if the setting is reset.
4. The band is 2.4 GHz only (the S3 has no 5 GHz radio). `SPECTER-LAB` on
   channel 6 by default.

Internet Sharing is only needed for the **station fallback**, where the Mac
itself must become the access point. It is not needed for this test.

---

## 5. The hardware test: 60 seconds, scored

`tools/esp32_lab_preflight.py` reads both USB paths at once and scores five
things. Every threshold is written down with its reason.

```bash
python3 tools/esp32_lab_preflight.py --seconds 60 \
        --ping 192.168.4.1 --expect-rate 20 \
        --out runs/lab/preflight-softap.json
```

| Check | Criterion | Why this threshold |
|---|---|---|
| CSI callback activity | ≥ 5 callbacks/s | below this the link is not really carrying traffic |
| **CSI callback fires at all** | > 0 | **the SoftAP capability probe** — zero means the S3 does not do AP-side CSI |
| Packet continuity | ≥ 95 % of the expected rate | 5 % loss is tolerable; more means the stimulus or the drain is broken |
| Longest gap | ≤ 1.0 s | a 1 s hole already invalidates a 30 s trial |
| Malformed lines | 0 | a reject means the wire format changed |
| Sequence gaps | 0 | the firmware's own counter; gaps mean device-side loss |
| RSSI | −85 … −15 dBm | outside this the geometry is wrong or the radio is saturating |
| Noise floor | ≤ −80 dBm | a noisy channel invalidates the features |
| Channel | exactly one value | a silent roam would change the physics mid-trial |
| Subcarrier map | ≥ 99 % of records with exactly 52 used | confirms the null set `{0} ∪ {27…37}` — the format contract |
| PHY rate | recorded; ≤ 2 distinct rates is PASS | it is a confound, not a failure, but it must be known |
| Device queue drops | 0 | the writer is keeping up |
| USB vs console byte drift | ≤ 0.5 % | confirms both console paths carry the same stream |
| **Supervisor telemetry** | **DEFERRED** | `HELLO`/`STAT`/`HB` is **not in this build** — see §6 |

`PASS` requires every check to pass; `DEFERRED` does not block; `UNKNOWN`
makes the result `INCONCLUSIVE`, never `PASS`.

### The RF check that needs a tape measure

The tool measures the radio, not the room. Do this once, by hand, after the
link is up:

1. Board on the bench, Mac at **1.0 m**, line of sight, `ping` running.
2. Record mean RSSI over 30 s.
3. Move to **3.0 m** on the same bearing. Record again.

**Pass:** RSSI at 3 m is **at least 3 dB lower** than at 1 m, and the channel
is unchanged. That is a physical measurement agreeing with a physical fact —
if it fails, the numbers on screen are not measuring distance and nothing
downstream can be trusted.

---

## 6. Supervisor telemetry: not in this image

The test asks for it; the firmware does not have it, and this preflight did
**not** add it, because that is the supervisor milestone's work and not this
experiment's.

What exists instead is `SPECTER_STAT`: one line a second, from the device,
about the device (role, peer MAC, channel, RSSI, callback count, printed
count, queue drops). It is **deliberately not** the `HELLO`/`STAT`/`HB`
protocol — different tag, different meaning — so a host can never mistake
device health for supervisor state.

The seam is already right for SPECTER-OS: the record queue, the single writer
and this status line are exactly where a supervisor transport would attach.
Nothing in the CSI path would change.

---

## 7. Rollback

Three levels, fastest first. **None of them depends on the new firmware
running** — esptool talks to the ROM loader.

### Level 1 — restore the original app (≈ 90 s)

The 1 MB original app region was extracted from the verified backup and
checked:

```
~/Downloads/esp32s3-csi-app-original.bin
  1 048 576 B, sha256 54ef5eebe09a0a3d3af5cc022c98a79e1dc100eef4d520651180c3ca72c8a065
  app descriptor: csi_recv_router, idf_ver v5.2.2
```

```bash
esptool --port /dev/cu.usbmodem5B901602281 --baud 115200 \
        write-flash 0x10000 ~/Downloads/esp32s3-csi-app-original.bin
esptool --port /dev/cu.usbmodem5B901602281 --baud 115200 \
        verify-flash 0x10000 ~/Downloads/esp32s3-csi-app-original.bin
```

This restores the exact bytes the board had, because nothing else was written.

### Level 2 — restore the whole 16 MB (≈ 23 min at 115200)

```bash
esptool --port /dev/cu.usbmodem5B901602281 --baud 115200 \
        write-flash 0x0 ~/Downloads/esp32s3-csi-flash-backup-20261021-full.bin
```

Then prove it, by reading the first 1.0625 MB back and comparing:

```bash
esptool --port /dev/cu.usbmodem5B901602281 --baud 115200 \
        read-flash 0x0 0x110000 /tmp/restore-check.bin
python3 - <<'EOF'
import hashlib, os
a = open("/tmp/restore-check.bin","rb").read()
b = open(os.path.expanduser("~/Downloads/esp32s3-csi-flash-backup-20261021-full.bin"),"rb").read()[:0x110000]
print("match:", hashlib.sha256(a).hexdigest() == hashlib.sha256(b).hexdigest())
EOF
```

### Level 3 — the board will not enumerate, or the app crash-loops

The ROM loader is independent of the app, so a boot loop is recoverable. In
order:

1. `esptool --port /dev/cu.usbmodem5B901602281 --baud 115200 --after hard-reset chip-id`
   — this is the command that recovered the board from its previous wedged
   state, and it works while the app is misbehaving.
2. If the bridge is silent: **hold BOOT, tap RESET, release BOOT**, then
   `esptool --port … --before no-reset write-flash …` at 115200.
3. If the native USB path is the only one present: `esptool --port
   /dev/cu.usbmodem1101 --before usb-reset …` (USB-Serial/JTAG can enter
   download mode without the buttons).

**Abort rule:** if the 60-second test returns `FAIL` on *CSI callback fires at
all* **and** the station fallback also returns zero, stop. Rolling back is
then the correct next action, and the SoftAP question is answered: no.

---

## 8. Remaining risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| The app boot-loops for a reason the build cannot show | low | board appears dead | Level 1/2 rollback; ROM loader is independent |
| SoftAP-mode CSI does not fire on the S3 | **unknown, and the main open question** | the SoftAP role is unusable | the `csi_cb` probe answers it in 60 s; station fallback exists |
| NVS is corrupt on the board | low | boot abort | the firmware repairs NVS and otherwise keeps state in RAM |
| The Mac's private Wi-Fi address changes between sessions | medium | peer filter mismatch | the firmware learns it at association; record it per run |
| 743 KB app vs 1 MB partition | — | 29 % headroom | adding the supervisor transport will need a check before it is merged |
| `esp_csi_gain_ctrl` version drift from the original image | low | absolute amplitudes differ | all analysis uses normalised features, which a constant scale cannot move |
| The firmware has never executed | **certain** | unknown behaviour | that is what the first flash is for, with a verified rollback |

---

## 9. What you do, physically, in order

1. **Say go.** Nothing below happens without authorization.
2. **Second backup** (§3, step 0) and check the SHA-256 against `51ae0968…`.
3. **Put the Mac's network out of the way** — be on a local terminal, because
   step 6 takes the Mac off its current network.
4. **Flash the SoftAP app only** (`0x10000`), then `verify-flash`.
5. **Read the console at 921600** and look for:
   `SPECTER-X controlled-link firmware ready`, then
   `SoftAP 'SPECTER-LAB' on channel 6`.
6. **Join `SPECTER-LAB` from the Mac** (no Internet Sharing). Note the
   address it gets (`192.168.4.x`) and the Wi-Fi MAC it used.
7. **Ping the board** (`ping -i 0.05 192.168.4.1`) and watch `SPECTER_STAT`:
   `csi_cb` must climb. **This is the SoftAP answer.**
8. **Run the scored test** (§5) with `--ping` and `--expect-rate 20`.
9. **Do the 1 m / 3 m RF check** (§5).
10. **Decide:** if `csi_cb` climbs, the SoftAP architecture is real and the
    experiment can be designed on it. If it does not, roll back with Level 1
    and we design on the station role instead.
11. **Ten-minute soak** (optional but cheap): run the preflight with
    `--seconds 600` and confirm `drop_old = 0` and no gap above 1 s. That is
    the USB-stability evidence the campus link never gave us.

**Stop point:** after step 1 there is nothing else this document can decide.
