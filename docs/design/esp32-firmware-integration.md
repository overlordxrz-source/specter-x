# Firmware integration design — Alpha 002-C (proposal only)

**Date:** 2026-10-21
**Branch:** `feature/alpha002-esp32-supervisor`
**Status:** a design, plus the measured criteria it must meet. **Nothing here
has been implemented, built or flashed.** The board still runs the original
`csi_recv_router` image.

---

## 1. The problem to solve

The host is ready for supervisor telemetry: the protocol, the parser, the
health model, the HUD block and the JSONL path all exist (checkpoints 003 and
006). What is missing is firmware that emits `HELLO` / `STAT` / `HB` on the
same USB CDC link the CSI stream uses.

The naive approach — a second task that calls `ets_printf` — is **not
serialised**. The CSI path writes with the ROM's `ets_printf`, which is not
reentrant, so a supervisor line can be torn by a concurrent CSI line (or the
other way round). The host would count the fragment as malformed, but silently
losing a supervisor heartbeat is exactly the kind of quiet dishonesty this
project does not accept.

So the design has to make the output **serialised by construction**.

---

## 2. Options considered

### Option 1 — one writer, a ring buffer *(recommended)*

All output goes through a single writer task. Producers hand it whole
records; it writes them one at a time.

```
  wifi_csi_rx_cb (unchanged)        supervisor_task (new)
        |                                  |
        |  dq_emit(record)                 |  dq_emit(record)
        +------------> ring buffer <--------+
                            |
                     writer task (new)
                            |
                       ets_printf()
```

* The CSI **capture callback's logic is untouched** — it still parses the CSI
  data exactly as upstream does. What changes is one line at the end: the
  `ets_printf` of the packet becomes a `dq_emit()` that copies the record
  into the ring buffer.
* The writer is the only task that calls `ets_printf`, so lines can never
  interleave. Serialisation is structural, not a hope.
* Cost: one extra copy per packet, at 178 packets/s of ~300 bytes. Trivial
  for the S3.

### Option 2 — a second CDC interface (fully isolated)

The ESP32-S3 has a USB-Serial/JTAG peripheral *and* a USB-OTG controller. A
composite device with two CDC ACM interfaces would put CSI on one and the
supervisor on the other: two nodes, two endpoints, no interleaving possible.

* **Uncertainty**: whether this board's USB-OTG D+/D- pins are broken out.
  The board's USB-C is wired to the USB-Serial/JTAG peripheral, and the S3's
  second controller needs its own pins. If they are not on headers, this
  option needs hardware work.
* Also a bigger change: TinyUSB instead of the ROM console, which changes how
  the app's output is routed — more risk to the CSI path than Option 1.

### Option 3 — one stream, unsynchronised *(cheapest, not recommended)*

The supervisor task just calls `ets_printf` once per second with a short
line. The collision window is small (one supervisor line per 178 CSI lines),
but it is not zero, and a torn line is a torn heartbeat.

* **Rejected** as the design of record. It is recorded here because it is
  the obvious first attempt, and it should be *measured* against Option 1
  rather than assumed equivalent.

---

## 3. The recommended design (Option 1) in detail

### 3.1 The ring buffer

```c
#define DQ_RING_BYTES  (16 * 1024)

typedef struct {          /* one record, copied whole */
    uint16_t len;         /* bytes, excluding the terminator */
    uint8_t  data[512];   /* a whole line: CSI packet or supervisor packet */
} dq_record_t;
```

A FreeRTOS queue of fixed-size records is simpler than a byte ring and
already guarantees whole-record atomicity. A queue of `dq_record_t` with
depth 32 costs 32 × 514 B ≈ 16 KB of heap — acceptable, and measurable.

**Overflow policy matters.** If the queue is full, the writer is behind.
Options: drop the *newest* (the supervisor packet) and count it, or drop the
*oldest* (a CSI packet) and count it. **The CSI stream must not be
interrupted for telemetry**, so: the supervisor's records are dropped first
and counted; a CSI record is only dropped if the queue is full of CSI records
too, and the drop is counted. The host sees the gap in the id sequence and
the drop count in the health record — never a silent loss.

### 3.2 The writer task

One task, one `ets_printf` per record, `vTaskDelay(1)` between records so it
cannot starve the CSI producer. It writes the record bytes and a terminator
together, so a line is never split.

### 3.3 The supervisor task

Unchanged from checkpoint 005's proposal, except that it now goes through
`dq_emit()` instead of `ets_printf`:

```
once, at start:
  HELLO,1,<board>,<chip>,<mac>,<fw_version>,<fw_build>
every second:
  HB,<seq>,<uptime_s>
  STAT,<uptime_s>,<heap_free>,<heap_min>,<health>
```

* `board` / `chip` / `fw_version` / `fw_build` come from
  `esp_app_get_description()`.
* `mac` from `esp_read_mac(mac, ESP_MAC_WIFI_STA)`.
* `uptime_s` from `esp_timer_get_time()` captured at boot.
* `heap_free` / `heap_min` from `esp_get_free_heap_size()` /
  `esp_get_minimum_free_heap_size()`.
* `health` from the heap and `esp_reset_reason()`:
  `OK` normally, `DEGRADED` if the minimum free heap falls below a
  threshold, `FAULT` if the last reset was a panic.

### 3.4 What must not change

* The CSI **capture callback's logic** — the parsing, the gain compensation,
  the field order.
* The CSI **packet format** — byte-identical, including the 24 fields and the
  quoted IQ tail.
* The `id` counter's meaning — it must stay consecutive, because the host
  uses it to detect loss.

---

## 4. Measured performance criteria

The acceptance thresholds are derived from the numbers measured on this board
(checkpoints 005 and 006), so they are not arbitrary:

| Metric | Measured now | Criterion after the change |
|---|---|---|
| CSI rate, integrated app | **176.37 packets/s** | **≥ 174.6 packets/s** (≥ 99 % of now) |
| CSI rate, reader alone | **185.94 packets/s** | ≥ 184.1 packets/s (≥ 99 %) |
| Sequence gaps | 0 | **0** over a 60 s window |
| Missing packets | 0 | **0** over a 60 s window |
| Malformed records | 0 | **0** over a 10 min window — this is the tearing test |
| Dropped queue entries | 0 | 0 for the CSI stream; supervisor drops counted and reported |
| Link outages | 0 | 0 in a 60 s window |
| Supervisor heartbeat | — | **1.0 Hz ± 10 %**, 0 missed in 10 min |
| Supervisor identity | — | `HELLO` received within 2 s of the link coming up |
| Free heap | — | no downward trend over 10 min (no leak); report the slope |
| Host frame rate | 41.8 FPS in CSI mode | ≥ 30 FPS |
| The instrument still works after a reset | yes | yes — the stream must resume within 20 s, as today |

**Explicitly measured, not assumed:**

* the cost of the ring buffer and the writer task on the CSI rate;
* the cost of the supervisor task on the free heap;
* that the supervisor's `STAT`/`HB` lines never appear interleaved inside a
  CSI line (the host's malformed count is the proof);
* that the CSI `id` counter is still consecutive.

### The measurement procedure

1. `tools/esp32_csi_baseline.py --seconds 60 --rate 100` before and after.
2. The integrated app run (as in checkpoint 006) before and after.
3. `tools/esp32_csi_visualize.py` on the recorded session, to see the
   subcarrier spectrum and the statistics side by side.
4. Ten minutes of continuous streaming with the supervisor enabled, checking
   the heartbeat count, the missed-heartbeat count, the malformed count and
   the heap trend.

---

## 5. Build and flash plan (not executed)

| | |
|---|---|
| Source | `espressif/esp-csi` @ `8633d67152db2808f141cc1595970aa9cf406045`, example `examples/get-started/csi_recv_router` |
| Dependency | `esp_csi_gain_ctrl` — **pin the exact version actually used**, which is still unknown (checkpoint 005) |
| Toolchain | **ESP-IDF v5.2.2**, `xtensa-esp-elf`, target `esp32s3` |
| Change | `main/supervisor_task.c` (new) + `main/dq_ring.c` (new) + one line in the CSI output path (`ets_printf` → `dq_emit`) |
| Flash | over the **UART bridge** — the only reliable path (checkpoint 004) |
| Backup before flashing | already taken and verified: `~/Downloads/esp32s3-csi-flash-backup-20261021-full.bin`, 16 777 216 B, SHA-256 `51ae0968…`, read-back MATCH |
| Rollback | `esptool write-flash 0x0 <backup>` over the UART bridge; the ROM download mode is the worst-case path and is proven to work |

**The build will not be byte-identical** to the current image (build date and
paths are embedded), so the acceptance test is *functional* — the criteria in
§4 — not a hash comparison. The backup is the ground truth for rollback.

---

## 6. Open questions this design does not answer

1. **Which `esp_csi_gain_ctrl` version is in the current image?** It is not
   recorded in the binary. It must be found (upstream CI history, or by
   building candidates and comparing behaviour) before a rebuild, because
   that component does the gain control and the router/mobile-hotspot
   handling — it is part of the CSI path, not a detail.
2. **What was the CI's "dirty" delta?** Unknown and not recoverable from the
   image. If it touched the CSI path, a clean rebuild could change the CSI
   behaviour — which is exactly why the functional criteria in §4 must be
   measured, not assumed.
3. **Is the USB-OTG broken out on this board?** Decides whether Option 2
   (a second CDC interface) is even possible.
4. **Can the writer task keep up?** At 178 packets/s of ~300 bytes it is
   ~53 KB/s of output — easy, but it must be *measured*, not assumed.
5. **The heap budget.** The ESP32-S3 has 8 MB PSRAM but the app's internal
   heap is much smaller; the ring buffer's 16 KB must be checked against
   what the app already uses.
