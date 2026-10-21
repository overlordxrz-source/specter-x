# SPECTER-X checkpoint 005 — upstream source, dispatcher, firmware plan

**Date:** 2026-10-21
**Branch:** `feature/alpha002-esp32-supervisor` (pushed; **not** merged)
**Status:** the upstream source is located and the unknown "dirty" delta is
characterised; a single USB serial dispatcher is implemented and tested; the
minimal firmware change is specified. **No firmware was built or flashed.**

---

## 1. The upstream source, located exactly

The flashed application reports itself as `csi_recv_router`, version
`8633d67-dirty`. That version string is a `git describe` of the build tree,
and the tree is:

| | |
|---|---|
| Repository | **`https://github.com/espressif/esp-csi`** |
| Revision | **`8633d67152db2808f141cc1595970aa9cf406045`** |
| Commit | *"Merge branch 'update_csi_viewer_html' into 'master'"*, 2026-04-22 |
| Example | `examples/get-started/csi_recv_router/main/app_main.c` (221 lines) |
| Dependency | `esp_csi_gain_ctrl >= 0.1.4` (ESP Component Registry) |
| Sibling artefact | `examples/get-started/tools/csi_viewer.html` — the web CSI viewer that commit adds |

The commit also contains `examples/esp-radar/wifi_sensing_demo/` and the
`.gitlab-ci.yml` changes, which is how the build below is explained.

### The "dirty" delta: what it is *not*

The flashed binary was compared against the upstream source at that exact
revision:

* the image contains
  `CSI_DATA,%d,%02x:%02x:%02x:%02x:%02x:%02x,%d,…` — **byte-identical** to the
  expansion of upstream's `ets_printf("CSI_DATA,%d," MACSTR ",%d,…")`;
* the image contains upstream's CSV header
  `type,id,mac,rssi,rate,sig_mode,mcs,bandwidth,smoothing,not_sounding,aggregation,stbc,fec_coding,sgi,noise_floor,ampdu_cnt,channel,secondary_channel,local_timestamp,ant,sig_len,rx_format,len,first_word,data`;
* the `CSI RECV` banner, `esp_wifi_set_csi_config(&csi_config)` and
  `esp_wifi_set_csi_rx_cb(wifi_csi_rx_cb, s_ap_info.bssid)` are all present
  verbatim;
* the remaining application strings (`Please report this bug to the
  manufaturer of the router/mobile-hotspot.`, `selected router must have a
  neighbor entry`, `CSI not enabled in menuconfig!`, `Check that
  CONFIG_FREERTOS_UNICORE is enabled in menuconfig`) belong to the example's
  Wi-Fi setup code and to the `esp_csi_gain_ctrl` component — **not** to a
  local patch.

**So the dirty state did not change the CSI output path.** The CSI capture
callback, the printf format, the header and the log tags are upstream's.

### The "dirty" delta: what it *is*

The build paths embedded in the image are

```
/Users/brnomac003/.gitlab-runner/builds/qR2TxTby/0/idf/crosstool-NG/...
```

i.e. **the image was produced by a GitLab CI runner**, not by a local build.
The `-dirty` suffix is the CI working tree's state at build time. Its
*content* is not recoverable from the image: it could be a generated
`sdkconfig`, a patched `esp_csi_gain_ctrl`, or anything else the CI applies.

### Consequence: a rebuild is not byte-identical

**Do not assume an upstream rebuild reproduces this image.** The app descriptor
embeds a build date, the binary embeds build paths, and the `sdkconfig` is
unknown. A rebuild with the same IDF version (v5.2.2) should be *functionally*
equivalent — the CSI path is upstream's and unchanged — but it will differ
byte-for-byte. The backup, not a rebuild, is the ground truth.

**How to settle it (proposed, not done):** build upstream `8633d67` cleanly
with IDF v5.2.2 and the same `esp_csi_gain_ctrl` version, then compare the
resulting `.bin` against the backed-up app partition. A functional comparison
(does it stream the same format at the same rate?) is the acceptance test;
byte equality is not expected and is not the goal.

### Every CSI field is now named

The upstream CSV header gives the authoritative names, and they line up with
what was measured on the wire:

| idx | name | idx | name | idx | name |
|---|---|---|---|---|---|
| 0 | type | 8 | smoothing | 16 | channel |
| 1 | id | 9 | not_sounding | 17 | secondary_channel |
| 2 | mac | 10 | aggregation | 18 | local_timestamp |
| 3 | rssi | 11 | stbc | 19 | ant |
| 4 | rate | 12 | fec_coding | 20 | sig_len |
| 5 | sig_mode | 13 | sgi | 21 | rx_format |
| 6 | mcs | 14 | noise_floor | 22 | len |
| 7 | bandwidth | 15 | ampdu_cnt | 23 | first_word |
| | | | | 24 | data (the quoted IQ blob) |

24 fields plus the data blob = 25, exactly the header's 25 names. A captured
packet is kept verbatim as a fixture at
`tests/fixtures/csi_packet_sample.txt` and is parsed by the test suite.

---

## 2. The single USB serial dispatcher

`specter/sensors/esp32/dispatcher.py`. One reader, several record types, no
cross-talk.

```
bytes ──> line splitter ──> classifier ──┬──> CsiParser      ──> bounded queue (CSI)
                                          ├──> supervisor parser ──> bounded queue (supervisor)
                                          └──> unknown ──> counted, dropped
```

| Property | How it is met |
|---|---|
| **Independent parsing** | `CsiParser` and the supervisor parser are separate; a malformed CSI line increments `csi_malformed` and nothing else, and vice versa |
| **Independent counters** | `DispatcherCounters` accounts for every line: `lines`, `csi_parsed`, `csi_malformed`, `supervisor_parsed`, `supervisor_malformed`, `unknown_lines`, `headers_seen`, `bytes`, plus `csi_sequence_gaps` / `csi_missing_packets` |
| **Bounded queues** | `BoundedQueue` has a fixed capacity, keeps the **newest** items and counts what it dropped (`csi_dropped`, `supervisor_dropped`). A consumer that stops reading cannot grow memory or stall the reader |
| **Transport agnostic** | the dispatcher consumes bytes, so it is driven by the simulator, a file, or a real port |

Details worth noting:

* The **CSI field names** come from the upstream header, and the dispatcher
  adopts a header if one appears on the wire.
* The **IQ tail** is quoted and never contains a newline, so the line splitter
  is safe; a packet split across two USB reads is reassembled.
* **Sequence gaps** are counted from the upstream `id` counter; a *restart*
  (the counter going backwards) is counted as a gap but **not** as missing
  packets, so a reboot is not mistaken for packet loss.
* The **supervisor records** are the same `HELLO`/`STAT`/`HB` packets the
  host half already parses, so the dispatcher is the natural place for them.

Tests: `tests/test_esp32_dispatcher.py` — **22 tests** covering
classification, interleaving, per-type isolation of malformed input, unknown
lines, header recognition, split packets, CRLF/LF, sequence gaps, restarts,
bounded-queue overflow and a saturated consumer not starving the other.

**Not yet done:** the dispatcher is not yet wired into `specter/app.py`; the
app still uses the standalone `SupervisorSource` (which owns its own port).
Doing both at once would put two readers on one CDC node. The next step is to
give the app a single reader and hang both consumers off the dispatcher.

---

## 3. The reproducible CSI baseline

`tools/esp32_csi_baseline.py` measures, over a fixed window:

* **throughput** — packets/s, link bytes/s, CSI bytes/s;
* **sequence gaps** — missing packets from the upstream `id` counter;
* **timing** — inter-arrival median/p95/max and the device's own
  `local_timestamp` spacing;
* **USB recovery** — outages (a second with no bytes), their length, and
  whether the link came back by itself.

It is read-only: a "recovery" means the link returned without intervention,
and the report records the outage so it can be compared against a manual
reset. It exits non-zero if packets went missing.

```bash
python3 tools/esp32_csi_baseline.py --seconds 60 --rate 100 --out runs/csi_baseline.json
```

### Measured baseline (2026-10-21, board idle, 60 s window)

```
port                     /dev/cu.usbmodem1101
packets                  10690          (178.15 packets/s)
link throughput          81124.8 B/s    (IQ values: 524288)
sequence                 first_id 37222, last_id 47911
gaps                     0
missing packets          0
arrival interval         median 5.203 ms, p95 8.022 ms, max 68.321 ms
device interval          median 5218 us, p95 14922 us
outages (>1 s silent)    0
malformed lines          0
unknown lines            1   (the truncated final line of the read)
queue dropped            6594 (the bounded CSI queue, capacity 4096)
```

Readings:

* **The link is stable.** 10 690 packets in 60 s with **zero sequence gaps and
  zero missing packets**, and not one second of silence. The `id` counter is
  provably consecutive across the whole window.
* The device's own cadence is ~5.2 ms per packet (≈192 packets/s); the host
  sees ~178 packets/s, the difference being the USB link's batching.
* The largest arrival gap was 68 ms — the CDC link delivers in bursts, and
  the *count* is unaffected.
* **The upstream CSV header is not printed on the wire** (`headers_seen: 0`),
  so the dispatcher must rely on its built-in field names. Good to know: the
  header exists in the binary but the example does not emit it here.
* The bounded queue dropped 6 594 records during the run — which is the
  dispatcher behaving as designed (the consumer is slower than 178 packets/s),
  and the counters still account for every packet.

A baseline of **178 packets/s with zero loss and zero outages** is now the
reference to compare against after any firmware change.

---

## 4. The minimal ESP-IDF firmware change

**Goal:** 1 Hz supervisor telemetry on the same USB link, **without touching
the CSI capture callback**.

### The change

One new file, `main/supervisor_task.c`, and **one added line** in
`app_main.c`:

```c
xTaskCreate(supervisor_task, "supervisor", 4096, NULL, 4, NULL);
```

The task, once per second:

```c
static void supervisor_task(void *arg) {
    const esp_app_desc_t *desc = esp_app_get_description();
    uint8_t mac[6]; esp_read_mac(mac, ESP_MAC_WIFI_STA);
    const int64_t boot_us = esp_timer_get_time();
    /* once, at start */
    ets_printf("HELLO,1,csi_recv_router,ESP32-S3,%02x:%02x:...,%s,%s\r\n", ...);
    for (;;) {
        vTaskDelay(pdMS_TO_TICKS(1000));
        ets_printf("HB,%u,%lld\r\n", seq++, (esp_timer_get_time() - boot_us) / 1000);
        ets_printf("STAT,%lld,%u,%u,%s\r\n", uptime_s,
                   esp_get_free_heap_size(), esp_get_minimum_free_heap_size(), health);
    }
}
```

`esp_app_get_description()` supplies the project name, version, build date and
IDF version; `esp_read_mac()` the MAC; `esp_timer_get_time()` the uptime;
`esp_get_free_heap_size()` / `esp_get_minimum_free_heap_size()` the heap; and
`esp_reset_reason()` the health word.

### Why this is the minimal change

* **The CSI capture callback is not touched.** `wifi_csi_rx_cb` and the
  `CSI_DATA` printf stay byte-for-byte as upstream. The CSI format and rate
  cannot change, because nothing in that path changed.
* The supervisor's lines are ~40 bytes/s against a ~73 KB/s CSI stream —
  a 0.05 % addition.
* The host already tolerates the mix: the CSI parser ignores non-`CSI_DATA`
  lines and the supervisor parser ignores non-supervisor lines, and the
  dispatcher counts both.

### Known risk in this design, stated plainly

The CSI path writes with the ROM's `ets_printf`, which is not reentrant. A
supervisor line could in principle be torn by a concurrent CSI line. The
minimal change accepts that risk (the host counts a torn line as malformed
and drops it). Making it impossible needs a mutex **in the CSI callback
too** — which the brief excludes, so it is out of scope here. A second,
safe variant: have the supervisor publish into a ring buffer that a *single*
writer task drains, and have the CSI callback keep using `ets_printf`
unchanged — the tearing window then only exists between two `ets_printf`
calls, not across the supervisor's own line. That variant is one extra file
and no CSI change either.

### What the firmware milestone (Alpha 002-B) would deliver

1. Vendor upstream `esp-csi` at `8633d67` (the `csi_recv_router` example and
   the `esp_csi_gain_ctrl` dependency pinned to the version actually used).
2. Add `main/supervisor_task.c` and the single `xTaskCreate` line.
3. Build with IDF **v5.2.2** and **`xtensa-esp-elf`**, target `esp32s3`.
4. Flash over the **UART bridge** (the only reliable path).
5. Verify: the CSI stream is unchanged in format and rate, and the
   supervisor's `HELLO`/`STAT`/`HB` appear once a second.
6. Record the new image's hash alongside the old one.

---

## 5. Rollback plan

| Step | Action |
|---|---|
| 0 | **Before any flash**, take the backup. `~/Downloads/esp32s3-csi-image-0x0-0x110000.bin` (bootloader + partition table + app, 1 114 112 B, SHA-256 `c99b6ab650d0ad4310c65fd4cd07dec8ee2429a2e73987b52458853d83b50833`) is done and hashed. The full 16 MB image is in progress. |
| 1 | Flash the new image. |
| 2 | If it misbehaves, restore: `esptool --port /dev/cu.usbmodem5B901602281 --baud 115200 write-flash 0x0 <backup>`. This **erases** the affected sectors, so it is a write and needs authorisation. |
| 3 | Verify the restore: the board boots from flash (`boot:0x8 SPI_FAST_FLASH_BOOT` on the UART console) and streams `CSI_DATA` again with the upstream format; the `id` counter continues. |
| 4 | **Worst case (bricked board):** the ROM download mode over the UART bridge's DTR/RTS has been exercised many times today and always worked, so the board is always recoverable — even a board that will not enumerate USB, because the ROM is reachable over the bridge. |
| 5 | If the backup itself is suspect: re-read the flash and compare against the recorded SHA-256 before trusting it. |

The rule that makes this safe: **the backup is taken and verified before any
flash, and the restore path is the same path (UART) that is proven to work
for reading.** No step depends on the native USB link that has been failing.

---

## 6. Remaining uncertainties

1. **The content of the "dirty" delta is unknown.** It was a CI tree state,
   not a local patch, and the image cannot say what it contained. The
   `sdkconfig` used and the `esp_csi_gain_ctrl` version actually vendored are
   also unknown. Only a clean rebuild and a functional comparison can settle
   it.
2. **A rebuild will not be byte-identical** (build date and paths are
   embedded). Functional equivalence is the acceptance criterion, not hash
   equality.
3. **`ets_printf` tearing** between the CSI callback and the supervisor task
   is possible and is accepted by the minimal change (§4).
4. **The full-flash backup is done and verified** — 16 777 216 B, SHA-256
   `51ae09689e19217aa52ff7d136313d2354345f9faf42ec50ee75324e602458f0`, and a
   fresh read-back of the app partition matches it byte-for-byte. The
   baseline has been measured on the idle board: **178 packets/s, 0 gaps, 0
   missing packets, 0 outages in 60 s** (§3).
5. **The DI-188 is still disconnected**, so its 1200-baud-touch hypothesis
   remains untested.
6. **UART0's binary stream is unexplained** — not the CSI format, not
   ESP-IDF logs, origin unknown. It is not usable as a second channel, but it
   is not understood either.
7. **The dispatcher is not yet wired into the app** (§2). The app still runs
   the standalone `SupervisorSource` with its own reader, because two readers
   on one CDC node would fight. The next step is one reader, two consumers.

---

## 7. Branches

```
main                                b5e1875   untouched
 └─ fix/di188-acquisition-shutdown  25b2948
     └─ feature/alpha002-esp32-supervisor          Alpha 002-A + this work
```

**Neither branch is merged into main.**
