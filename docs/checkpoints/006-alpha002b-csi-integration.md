# SPECTER-X checkpoint 006 — Alpha 002-B, real CSI host integration

**Date:** 2026-10-21
**Branch:** `feature/alpha002-esp32-supervisor` (pushed; **not** merged)
**Status:** the DI-188 work aside, the ESP32-S3's Wi-Fi CSI stream is now a
first-class SPECTER-X sensor — instrument → `Measurement` → HUD → JSONL — with
**exactly one reader** owning the USB port. Measured live on the hardware.
**No firmware was built or flashed.**

---

## 1. The architecture: one reader, many consumers

```
 /dev/cu.usbmodem1101  (Espressif 0x303A:0x1001)
        │
        │  ONE reader
        ▼
 Esp32SerialReader ──> SerialDispatcher ──┬──> CsiParser ──> bounded queue ──┐
        │                                  └──> supervisor parser ─> queue ─┤
        │                                                                     │
        │  health: CONNECTED / CONNECTING / STALLED / DISCONNECTED / ABSENT /  │
        │           ERROR, packets, gaps, missing, malformed, dropped, silence  │
        ▼                                                                     ▼
 csi_summary Measurement                                   HUD "CSI" mode + JSONL
 (sensor="wifi_csi", kind="csi_summary")
```

`specter/sensors/esp32/reader.py` is the only thing that opens the port. It
feeds the shared :class:`SerialDispatcher`, and it *feeds* the supervisor's
state machine rather than opening a second port — so the supervisor and the
CSI stream share one reader and one set of bytes.

### What the supervisor does when the firmware does not emit it

The board's current firmware emits **no** supervisor packets. The reader
therefore reports the supervisor as:

```
available: False   state: "UNAVAILABLE"
detail:    "instrument does not emit supervisor packets"
```

and the HUD shows **"telemetry not available"** in amber plus a
`SUPERVISOR ESP32  N/A  telemetry not available` health row. **No simulated
heartbeat is ever substituted in a real-hardware session** — the simulator
exists only in the unit tests, and it is not reachable from the app.

---

## 2. The measurement

One `csi_summary` Measurement per second, because the board produces ~178
packets/s and logging each one would bury the event log. The summary
**accounts for every packet** — the count, the id range, the gaps and the
drops are all in the payload.

| Preserved | How |
|---|---|
| **packet counters** | `id` (the upstream `id`), `first_id`..`last_id`, and `packets` since the last log |
| **device timestamps** | `local_timestamp` (the device's own µs clock) in the value, and `t_sensor` = that clock in seconds |
| **provenance** | `sensor_id` = the board MAC (`14:C1:9F:26:52:EC`), `source` = `wifi_csi`, `algorithm` = `csi_recv_router`, `frame_index` = the packet id |
| **acquisition health** | `link_state`, `link_detail`, `packets_per_s`, `gaps`, `missing_packets`, `malformed`, `dropped`, `unknown_lines`, `silence_s`, `reconnects`, `uptime_s` |
| **the signal itself** | `amplitudes` — 64 per-subcarrier magnitudes, `subcarriers`, `iq_samples`, plus `ap_mac`, `rssi`, `rate`, `channel`, `noise_floor`, `sig_len` |

`confidence` is `None`: a CSI packet is an observation, not a calibrated
measurement.

---

## 3. Measured results on the hardware

### The 60-second integrated run (the app, `--csi esp32 --mode CSI`)

| | |
|---|---|
| Duration | 70 s (3 460 HUD frames) |
| **Rate** | **176.37 packets/s** |
| **vs the 178.15 packets/s baseline** | **99.0 %** |
| Sequence gaps | **0** |
| Missing packets | **0** |
| Malformed records | **0** |
| Dropped queue entries | **0** |
| Unknown lines | 0 |
| Link state | `CONNECTED` throughout, 0 reconnects |
| `csi_summary` records | 65 (0.93 Hz) |
| Packets accounted for | 12 250 |
| id range | 36 678 → 48 927 |
| Subcarriers | 64 |
| AP | `b8:62:1f:e5:ac:62`, channel 11, −65 dBm |

### The reader on its own (no app, 60 s)

| | |
|---|---|
| Rate | **185.94 packets/s** |
| Gaps / missing / malformed / unknown | 0 / 0 / 0 / 0 |
| Dropped | 9 254 — the bounded queue (2 048) overflowing because nothing drained it, which is the queue doing its job |
| id range | 22 427 → 33 728 (consecutive) |
| Shutdown | port released, thread joined, clean exit |

**Reading of the numbers.** The reader alone is *above* the earlier baseline
(185.94 vs 178.15) — the baseline tool drained and parsed more per packet.
The integrated app costs about 5 % of the rate (176.37), which is the HUD
loop, the JSONL write and the Measurement construction. Nothing is lost: zero
gaps, zero missing, zero malformed, zero dropped, in both runs.

### Shutdown behaviour

`stop()` escalates in three steps — ask the thread to stop, wait, then take the
serial port away so a blocked read fails and the thread unwinds. The port is
**always** released; the thread is always joined.

---

## 4. The HUD

`--mode CSI` shows the link and the signal:

* the subcarrier amplitude spectrum of the latest packet (64 bars, real
  structure, with the DC/guard band visible as a notch);
* the packet statistics: packets, packets/s, id range, sequence gaps, missing,
  malformed, dropped, unknown lines, silence, reconnects, uptime, bytes;
* the device's own timestamp and the board MAC.

`docs/alpha002/alpha002_csi_hud.png` is that view from the live run.

## 5. Offline visualisation

`tools/esp32_csi_visualize.py` reads a recorded session log and renders the
same two panels offline — a subcarrier-amplitude heatmap over time and the
packet statistics — so a run can be reviewed after the hardware is gone.
It uses **OpenCV and numpy only**; no new dependency was added.

```
python3 tools/esp32_csi_visualize.py runs/session.jsonl -o runs/csi.png
```

`docs/alpha002/alpha002_csi_offline.png` is the output for the integrated run.

---

## 6. Tests

`tests/test_esp32_integration.py` — **14 tests**, no hardware:

| Covered | |
|---|---|
| **USB disconnect** | the device vanishing is reported as `DISCONNECTED`, not hidden |
| **Reconnect** | a new port is opened and the reconnect is counted |
| **Stalled stream** | silence past the timeout becomes `STALLED` |
| **Startup silence** | silence during the grace window is `CONNECTING`, not a stall |
| **Malformed data** | bad records are counted; the good ones still arrive |
| **Truncated / split records** | a record split across reads is reassembled; a short one is counted malformed |
| **Multiple record types** | CSI, HELLO, STAT and HB interleaved on one link, each to its own consumer |
| **Bounded queue** | a slow consumer cannot grow the queue or block the reader |
| **Shutdown** | the port is released; stopping is safe when the device is already gone |
| **Supervisor unavailability** | a real link with no supervisor packets reports `UNAVAILABLE`, never a fake heartbeat |

Full suite: **207 passed, 1 skipped** (the real-device DI-188 acceptance test —
that instrument is disconnected).

Two real bugs were caught by these tests during development: the reader was
feeding *parsed* packets to the supervisor's *line* API, and the packet-delta
counter in the app was advanced before it was read (so every logged
`packets` was 0).

---

## 7. A hardware problem this work exposed

The board's **native USB CDC path wedges** — it has now happened three times
(today, and twice before). The symptom is always the same: the device still
enumerates with the right VID/PID and serial, but the CDC data path returns
nothing in either direction, so no command and no packet gets through. It
affected the DI-188 too, in the same way (checkpoint 003).

**Recovery**: a hard reset over the UART bridge
(`esptool --port /dev/cu.usbmodem5B901602281 --baud 115200 --after hard-reset chip-id`)
brings it straight back, and the CSI stream resumes **after ~10 s**, because the
application has to bring up Wi-Fi first.

**The reader now handles this**: it distinguishes *warming up* (silence inside
the 20 s startup grace → `CONNECTING`) from *stalled* (silence after that),
reports the outage, and reconnects on its own if the device disappears.

Two things the reader does **not** do, deliberately: it never resets the
device, and it never opens the bootloader. Recovery stays a deliberate,
human action.

---

## 8. Remaining limitations

1. **The wedge is not fixed, only detected.** The reader reports it and
   survives it, but the instrument still needs a manual reset to recover.
2. **The supervisor is unavailable** until firmware emits it (Alpha 002-C).
3. **One summary per second** — the individual packet ids between summaries
   are accounted for in aggregate, not logged individually. Logging every
   packet would produce ~178 records/s.
4. **The queue can drop records** if a consumer falls behind; the drop count
   is reported, and nothing is silently lost.
5. **The DI-188 is still disconnected**, so its acceptance test skips.
6. **The app still has two USB paths** — the DI-188 reader and the ESP32
   reader — but they are different devices, so only one reader per node, which
   is the constraint that matters.

---

## 9. Branches

```
main                                b5e1875   untouched
 └─ fix/di188-acquisition-shutdown  25b2948
     └─ feature/alpha002-esp32-supervisor          Alpha 002-A + B + this work
```

**Not merged into main.**
