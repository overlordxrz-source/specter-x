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

### 1.1 The second problem, found later: the device's TX path overflows

Checkpoint 008 established, by controlled experiment, that the current
firmware's USB TX path **cannot be overrun**:

* when the host reads the CDC endpoint continuously, the link is clean
  (0 gaps, 0 missing, 0 malformed over twenty minutes);
* when the host reads it slowly, the device **drops whole CSI packets** —
  their ids are skipped — and prints **truncated lines**;
* if the slow reading is sustained, the device's TX path **wedges
  permanently**: neither continuous reading nor reopening the port revives
  it, and only a device reset does.

The firmware therefore needs three properties the current image does not
have, and they are as important as the serialisation:

1. **The capture path must never block on the CDC path.** A CSI callback
   that waits for the USB FIFO is a callback that stops keeping up with the
   radio — and the observed failure mode is exactly the device falling
   behind and dropping.
2. **The device must own its overflow policy and report it.** If the
   firmware drops a record, the host must be able to tell that apart from
   the link losing it. Today it cannot: the host sees an id gap and has to
   guess.
3. **The device must report its own health while the link is quiet.** The
   device pauses its whole output path for ~5.5 minutes at a time
   (checkpoint 008, Fault B). During such a pause the device's log is
   silent along with its data, so the pause is currently unattributable.
   A heartbeat and a "time since last CSI callback" counter turn an
   unattributable silence into a device-reported one.

This is why the writer task below is not optional polish: **it is the
back-pressure mechanism.** A bounded queue in front of a single writer, with
a counted drop policy, converts "the host is slow" from a fatal, silent,
device-killing condition into a bounded, counted, recoverable loss.

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

**Checkpoint 008 adds a second, harder requirement: the queue depth is what
keeps the USB FIFO from overflowing, so it must be sized against the
*measured* link, not guessed.** The device currently prints ~178 packets/s of
~433 B, i.e. **~77 KB/s of output**. The queue must absorb the difference
between the radio's callback rate and what the host drains, and the writer
must apply back-pressure to the producer *before* the FIFO overflows.

The mechanism must be **counting and bounded**, never silent:

* the CSI callback **never blocks** — it copies into the queue and returns;
* when the queue is full, the oldest CSI record is dropped and a counter is
  incremented;
* the `id` is assigned **when the record is produced**, so a dropped record
  leaves a gap in the id sequence — the host can see the loss, and the
  firmware's own drop counter says whether the device or the link lost it.

### 3.1.1 The overflow counters the host needs

The host currently cannot distinguish "the device dropped it" from "the USB
link lost it" — it sees an id gap and nothing else. The firmware must close
that gap, because checkpoint 008 shows the device *does* drop:

```
STAT,<uptime_s>,<heap_free>,<heap_min>,<health>,<csi_dropped>,<sup_dropped>
```

* `csi_dropped` — CSI records dropped by the firmware's own queue, since
  boot. Non-zero means the device was overrunning and the *host* is
  blameless for the corresponding id gap.
* `sup_dropped` — supervisor records dropped, which should be zero because
  CSI is dropped first.

With these two counters, the host's `gaps` and `missing` become
attributable: a gap with `csi_dropped` rising is the device; a gap with
`csi_dropped` flat is the link.

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
  STAT,<uptime_s>,<heap_free>,<heap_min>,<health>,<csi_dropped>,<sup_dropped>
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
* `csi_dropped` / `sup_dropped` are the firmware's own queue-drop counters
  (see §3.1.1) — the host needs them to attribute an id gap to the device
  or to the link.

### 3.4 What must not change

* The CSI **capture callback's logic** — the parsing, the gain compensation,
  the field order.
* The CSI **packet format** — byte-identical, including the 24 fields and the
  quoted IQ tail.
* The `id` counter's meaning — it must be assigned per *record produced*, so
  that a firmware-side drop leaves a visible gap. (Checkpoint 007 said the
  id must "stay consecutive"; checkpoint 008 shows the current device's id
  *does* skip when it drops, and that skipping is the only way the host can
  see the loss. The requirement is that the id is honest and monotonic, not
  that it is gap-free.)

### 3.5 The writer task must also survive a slow host

The writer writes into a USB FIFO that has no flow control. If the host
stops reading, the FIFO fills, and the current firmware wedges. The new
writer must therefore:

* watch its own queue depth and the age of the oldest queued record;
* when the queue is full, **drop and count** rather than block, so the
  writer never stalls the radio;
* report the drop count, so the host and the operator can see it;
* leave the *capture* path entirely unaffected — dropping an output record
  is strictly better than losing a CSI callback or wedging the device.

This is the design's answer to the failure mode in checkpoint 008: a slow
host should cost us **counted, bounded packet loss**, not a wedged device
that needs a human with a reset cable.

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
| **Host reads slowly (50 ms poll)** | **47.8 % of packets arrive, 777 gaps, 481 malformed** | **the device must stay alive and report its drops: no wedge, `csi_dropped` matches the observed id gap** |
| **Host stops reading for 5 min** | **the device wedges permanently; only a reset recovers it** | **the device must stay alive, drop and count, and resume cleanly when the host reads again** |
| **Host reads continuously for 20 min** | 0 gaps, 0 missing, 0 malformed | **unchanged: 0 gaps, 0 missing, 0 malformed** |
| **The device's own 5.5-minute pause** | **the whole CDC path goes silent for ~320–331 s and resumes by itself; the host sees a 331 s arrival gap** | **the device must report the pause: the heartbeat must keep flowing and a `STAT` must carry a "no CSI callback for N s" counter, so the pause is attributable to the device** |

The last three rows are the checkpoint-008 tests. They are the *hostile*
cases, and they are the ones the current firmware fails.

The final row is the one the supervisor is really for. Right now a
5.5-minute pause is invisible from the device side: the CDC path is silent,
so the device's log is silent with it, and the host can only say "the bytes
stopped". A heartbeat that survives the pause, plus a counter of how long it
has been since the last CSI callback, turns an unattributable silence into a
**device-reported** one.

**Explicitly measured, not assumed:**

* the cost of the ring buffer and the writer task on the CSI rate;
* the cost of the supervisor task on the free heap;
* that the supervisor's `STAT`/`HB` lines never appear interleaved inside a
  CSI line (the host's malformed count is the proof);
* that the CSI `id` counter is still monotonic, and that a firmware-side
  drop is visible as an id gap **and** as a rise in `csi_dropped`, so the
  two are not confused;
* that the device survives the hostile-host rows above.

### The measurement procedure

1. `tools/esp32_csi_baseline.py --seconds 60 --rate 100` before and after.
2. The integrated app run (as in checkpoint 006) before and after.
3. `tools/esp32_csi_visualize.py` on the recorded session, to see the
   subcarrier spectrum and the statistics side by side.
4. Ten minutes of continuous streaming with the supervisor enabled, checking
   the heartbeat count, the missed-heartbeat count, the malformed count and
   the heap trend.
5. `tools/esp32_csi_poll_sweep.py --seconds 180 --intervals 0,0.005,0.02,0.05`
   — the hostile-host sweep. Today the 50 ms arm loses 52 % of the packets
   and eventually wedges the device; after the change every arm must show
   0 malformed lines, a live device, and a `csi_dropped` counter that
   accounts for the id gaps.
6. `tools/esp32_usb_health.py --seconds 1200 --poll-interval 0.0` — a
   20-minute continuous soak. Must end with 0 gaps, 0 missing, 0 malformed.

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
