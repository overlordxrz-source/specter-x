# SPECTER-X checkpoint 012 — Alpha 002: controlled RF research

**Date:** 2026-10-22
**Branch:** `feature/alpha002-esp32-supervisor`
**Status:** the synthetic validation is done, the controlled-link firmware is
**built but not flashed**, and the campus gateway was not used.

**Nothing is claimed.** No motion detection, no vital-sign detection. The
16 MB backup is untouched, the board was not flashed, erased, reset or
modified, and `main` was not touched.

---

## 1. The synthetic validation

`tools/esp32_csi_sweep.py`, master seed **20261022**, 12 independent
experiments per effect size, 4 repetitions per condition, 12 s per trial,
two conditions (`stationary`, `hand`). The bench link
(`specter/sensors/esp32/synthetic_link.py`) has a **known** ground truth: a
static multipath profile with the board's real null band, a person modelled
as a **moving reflector** (a static reflector would change the amplitude
and nothing else), a drifting AGC, and a PHY rate that changes the
amplitude scale.

| effect | detection rate | held-out accuracy | median p | median \|d\| |
|---|---|---|---|---|
| 0.00 (null) | **0.000** | 0.521 | 0.483 | 0.529 |
| 0.01 | 0.000 | 0.479 | 0.422 | 0.613 |
| 0.02 | 0.000 | 0.458 | 0.646 | 0.343 |
| 0.05 | 0.000 | 0.521 | 0.290 | 0.822 |
| 0.10 | 0.083 | 0.750 | 0.154 | 1.154 |
| **0.20** | **0.917** | **0.979** | 0.006 | 2.943 |
| 0.40 | 1.000 | 1.000 | 0.000 | 13.253 |

| | |
|---|---|
| **false-positive rate** | **0.000** over 12 null experiments (and the per-run permutation estimate was 0.02-0.08, i.e. at the nominal α) |
| **sensitivity** | an effect of **≈ 0.2** - the person's perturbation has to be about a fifth of the carrier amplitude, on the six carriers the model perturbs |
| **held-out accuracy** | 0.52 (chance) at the null, 0.98 at effect 0.2 |
| **the null \|d\| band** | median **0.53**, 95th percentile **1.28** |

### The finding that changes the interpretation of checkpoint 011

Checkpoint 011 reported the real experiment's effect sizes as **d = 0.95**
(stationary vs walking) and **d = 1.28** (hand vs walking), and called
them large. **They are not large — they are inside the noise.**

The bench says the null \|d\| has a 95th percentile of **1.28**. The real
experiment's d of 0.95 is *below* that. So the effect sizes in the nine-trial
session are not evidence of an effect; they are what three trials of noise
look like.

This is the correction, and it is the reason the bench is worth building:
**an effect size is only meaningful against the null distribution of the
same statistic on the same link, and the real session cannot supply that
distribution** - with three trials per condition, a random split of the
stationary trials is 1-versus-2, and Cohen's d is not even estimable.

**Two consequences:**

1. **The nine-trial experiment measured nothing.** Not "no effect" -
   *nothing*, because the null band is wider than the effect.
2. **The next real run needs at least four, and preferably six, stationary
   trials**, so the null distribution can be estimated on the real link. That
   is a new requirement the earlier design did not have.

The sweep is reproducible from the seed alone:

```bash
python3 tools/esp32_csi_sweep.py --out runs/campaign/sweep --seed 20261022
```

and the evidence is in `docs/checkpoints/evidence/synthetic_sweep.{json,csv}`.

### Power

Simulated with the same omnibus test and critical value the analysis uses:

| effect size (d) | trials per condition | total | time at 30 s |
|---|---|---|---|
| 0.40 | 30 | 90 | 45 min |
| 0.60 | 14 | 42 | 21 min |
| 0.95 | 7 | 21 | 11 min |
| 1.28 | 4 | 12 | 6 min |

---

## 2. The controlled Wi-Fi link: feasibility, honestly

### What was established

* **Espressif ships no SoftAP CSI example.** All three of their documented
  architectures - "get router CSI", "get CSI between devices", "get CSI
  specific devices" - measure the CSI on a **station**, of a **downlink**.
  Both `csi_recv` and `csi_send` run `WIFI_MODE_STA`.
* **The IDF does not document the mode.** `esp_wifi_set_csi_rx_cb()` on the
  S3 has no mode qualifier, and the Wi-Fi guide's CSI section only ever
  describes a station.
* **The S3's Wi-Fi is a precompiled library**
  (`components/esp_wifi/lib/esp32s3/libpp.a`), so the source cannot answer
  the question either way.
* **The S3 does support SoftAP** as a Wi-Fi mode, and `SOC_WIFI_CSI_SUPPORT`
  is 1 - but neither fact says anything about the *combination*.
* **There are field reports** of the S3's CSI callback never firing at all.

**So the SoftAP role's CSI support is UNKNOWN, and it cannot be settled
without the board.** That is a real limitation of this milestone, stated
rather than papered over.

### What was built to settle it in a minute

The new firmware **probes the capability at runtime**: the `SPECTER_STAT`
line carries `csi_cb`, the number of times the CSI callback fired. Flash
it, join the SoftAP from the Mac, have the Mac send traffic, and read one
line a second. If `csi_cb` stays at zero while the Mac is pinging the
board, the answer is no.

**The known-good alternative is in the same build**: the **station** role,
where the board joins a *local* access point - the Mac, or a second board -
and measures the downlink. That is the role the original image used, so the
behaviour is known and the data is comparable with the archive. The Mac, as
the access point, generates the controlled traffic (it pings the board at a
fixed rate; the board's ACKs are the downlink frames whose CSI is
measured), so **the stimulus is known by construction** - which is the thing
the campus link could never offer.

---

## 3. The firmware

`firmware/esp32-csi/softap_csi/` - **built, not flashed.**

| | |
|---|---|
| Toolchain | ESP-IDF **v5.2.2**, target `esp32s3`, Xtensa LX7 |
| App binary | **449 216 bytes** - 57 % of the 1 MB app partition free |
| Layout | **unchanged**: bootloader 0x0, table 0x8000, app 0x10000 |
| Roles built | station **and** SoftAP, both compile |
| Component | `esp_csi_gain_ctrl` from the registry, the same one the original image used |
| Artefacts | `docs/checkpoints/012` §7 |

### Preserved

* the CSV header and every field, in Espressif's order - including the two
  upstream quirks the host parser documents: the **second copy of
  `sig_mode`** in the `rx_format` slot, and `first_word` carrying the
  `first_word_invalid` flag;
* the CSI configuration: **LLTF only, channel filter on, manual scale**;
* the **gain compensation**, applied to the same bytes, so the amplitude
  values on the wire are the values the original image printed.

### Fixed

* **The callback no longer formats or prints.** The IDF is explicit:
  *"The CSI receiving callback function runs from Wi-Fi task. So, do not do
  lengthy operations in the callback function. Instead, post necessary data
  to a queue and handle it from a lower priority task."* The original image
  printed 128 formatted numbers inside that callback - which is the
  behaviour behind the host-side loss in checkpoint 008. The callback now
  copies the raw bytes and the radio metadata into a record and pushes it.
* **One writer task does all the output.** The output is serialised by
  construction; a record can never be torn by a concurrent write.
* **The queue is bounded and its losses are counted.** When it is full the
  *oldest* record goes (a live time series wants the newest data) and the
  loss is reported in `SPECTER_STAT` as `drop_old` / `drop_new`. **A slow
  host now costs counted packet loss instead of a corrupted stream** - which
  is the "continuous draining and serialized output" requirement, met on
  the device side as well as the host side.

### The contract is tested, not promised

`tests/test_firmware_contract.py` (10 tests) checks the firmware against
the host parser: the header string, the field count, the field order, the
quoted tail, the bounded queue and its counting, the callback's restraint,
the single writer, the unchanged CSI configuration, and the gain
compensation. **The two cannot drift apart silently.**

---

## 4. The firmware and the backup

The 16 MB backup is **untouched**:

```
~/Downloads/esp32s3-csi-flash-backup-20261021-full.bin
  16 777 216 bytes
  sha256 51ae09689e19217aa52ff7d136313d2354345f9faf42ec50ee75324e602458f0
```

The new images are **not** flashed, and the board was not reset, erased or
modified. (It is currently in its quiet state - the campus AP has dropped
it again - which is why the console reader returns nothing. That is the
condition the lab steps start by fixing.)

---

## 5. The exact physical steps for the first controlled experiment

The full script is in
[`firmware/esp32-csi/softap_csi/README.md`](../firmware/esp32-csi/softap_csi/README.md) §5.
In order:

1. **Take a second backup** over the UART bridge - 16 MB, chunked.
2. **Flash** the new image over the UART bridge (not the native USB):
   `esptool --port /dev/cu.usbmodem5B901602281 --baud 115200 write-flash 0x0
   build/bootloader/bootloader.bin 0x8000
   build/partition_table/partition-table.bin 0x10000 build/specter_csi_lab.bin`
3. **Read the console at 921600 baud** (`tools/esp32_console.py`) and look
   for `SPECTER-X controlled-link firmware ready`.
4. **Read the CSI stream and the status line**
   (`tools/esp32_csi_baseline.py --seconds 30`): `csi_cb` must climb and
   `drop_old` must stay 0.
5. **Answer the SoftAP question** (SoftAP role only): have the Mac send
   traffic and watch `csi_cb`. Zero means the S3 does not do AP-side CSI →
   use the station role.
6. **Put the Mac on the air.** macOS 27 has no `airport`, so: give one of
   the unused USB Ethernet adapters (`en2`/`en3`) an address, then use
   Internet Sharing to publish the SoftAP named **`SPECTER-LAB`**. *This
   takes over the Wi-Fi radio and will drop the session's own connectivity -
   do it from a local terminal.*
7. **The first controlled measurement**: the Mac pings the board at a fixed
   rate, the subject stands at a **marked distance**, and the experiment
   runs exactly as checkpoint 011 specifies - **7-10 repetitions per
   condition, randomised, blinded, with the subject's position recorded, the
   PHY rate conditioned on, and at least four stationary trials so the null
   distribution can be estimated.**

---

## 6. What is *not* claimed

* **No motion detection.** The bench's sensitivity is an effect of ~0.2 and
  the real session's effect sits inside the null band. Nothing is detected.
* **No vital-sign detection.** Out of scope here and still scoped in
  `docs/design/vital-signs-scope.md`; it needs the controlled link first.
* **The SoftAP role is unverified.** It is built, it compiles, and it
  carries the probe that will answer the question in a minute.
* **The station role needs a local access point**, which the Mac can
  provide with Internet Sharing - at the cost of the session's own network.
* **The firmware has not been run.** It compiles and it is contract-tested,
  but a build that has never executed is not a working build.

---

## 7. Artefacts

| Path | What |
|---|---|
| `tools/esp32_csi_sweep.py` | the synthetic sweep |
| `tools/esp32_console.py` | the 921600 console reader |
| `firmware/esp32-csi/softap_csi/` | the firmware project (source, not the build) |
| `tests/test_firmware_contract.py` | the firmware ↔ parser contract (10 tests) |
| `tests/test_csi_analysis_bench.py` | the analysis and bench (20 tests) |
| `docs/checkpoints/evidence/synthetic_sweep.json` | the sweep, every run seeded |
| `docs/checkpoints/evidence/synthetic_sweep.csv` | the sweep, as a table |

**Build artefacts** (not committed; the build directories are git-ignored):

| Artefact | SHA-256 (first 16) | Size |
|---|---|---|
| `build/specter_csi_lab.bin` (station) | `46771939a9ea95f5` | 449 216 B |
| `build-softap/specter_csi_lab.bin` (SoftAP) | `abacd2fd8e2a6c6a` | 449 216 B |
| `build/bootloader/bootloader.bin` | `7b5d346104a896e6` | 21 072 B |
| `build/partition_table/partition-table.bin` | `7f00b6c042a89b15` | 3 072 B |

**Rebuild them with:**

```bash
cd firmware/esp32-csi/softap_csi
source ~/esp/esp-idf/export.sh
idf.py set-target esp32s3 && idf.py build
idf.py -D SDKCONFIG_DEFAULTS="sdkconfig.defaults;sdkconfig.softap.defaults" \
       -B build-softap build
```
