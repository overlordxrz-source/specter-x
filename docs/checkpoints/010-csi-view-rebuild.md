# SPECTER-X checkpoint 010 — the CSI view, rebuilt

**Date:** 2026-10-21
**Branch:** `feature/alpha002-esp32-supervisor`
**Status:** the CSI mode has been rebuilt around a **scrolling subcarrier
waterfall**, a **baseline-relative signal-change trace** and **compact
packet/USB health counters**, on a new deep-burgundy/charcoal theme. The raw
spectrum is kept as a secondary diagnostic. A **guided motion experiment** is
now part of the application, and the live view states plainly that a signal
change is **not** a human detection.

**No firmware was flashed. `main` was not touched.**

---

## 1. The packet structure, verified on the wire

Taken from the board itself, not from the documentation:

```
CSI_DATA,2091,40:f4:ec:7e:37:22,-70,9,0,0,0,0,0,0,0,0,0,-96,0,1,0,17684550,0,109,0,128,0,"[0,0,-14,-15,...]"
```

| # | field | example | note |
|---|---|---|---|
| 0 | type | `CSI_DATA` | |
| 1 | id | `2091` | the sequence counter the host uses to detect loss |
| 2 | mac | `40:f4:ec:7e:37:22` | **the transmitter of the frame the board heard** |
| 3 | rssi | `-70` | dBm |
| 4 | rate | `9` | |
| 14 | noise_floor | `-96` | dBm |
| 16 | channel | `1` | **the channel of that frame** |
| 18 | local_timestamp | `17684550` | µs since the board's boot |
| 20 | sig_len | `109` | |
| 22 | len | `128` | **the number of I/Q samples that follow** |
| 23 | first_word | `0` | |
| tail | data | `"[0,0,-14,-15,…]"` | **128 interleaved I/Q samples = 64 complex subcarriers** |

The amplitudes are therefore `hypot(I[n], Q[n])` over 64 complex
subcarriers, and the **complex samples are available** - the new view uses
them rather than a pre-reduced magnitude.

### The unused subcarriers, measured

Across every packet captured, the null set is **exactly**:

```
subcarrier 0            (DC)
subcarriers 27 .. 37    (the guard band)
```

**52 of the 64 carriers are in use.** The view detects this from the data
(a carrier that reads exactly zero for five consecutive packets) rather than
assuming it, paints the band out, labels it, and **excludes it from every
statistic** - including it would dilute every measure with twelve carriers
that are supposed to be silent.

### The Wi-Fi source - and a correction to checkpoint 007

The board's own log says:

```
I (3108) wifi:connected with Kent State Guest, aid = 1, channel 11, BW20, bssid = b8:62:1f:e5:ac:62
I (4111) esp_netif_handlers: example_netif_sta ip: 10.7.82.237, mask: 255.255.240.0, gw: 10.7.95.254
```

**Checkpoint 007 stated that the `mac` field of every CSI packet matches the
BSSID in the log. That is not always true.** A packet captured before the
most recent reset carried `mac = 40:f4:ec:7e:37:22` on `channel = 1` - a
*different* access point on the same guest network. The board roams between
the guest APs, and the `mac`/`channel` fields of a CSI packet describe the
**transmitter of the frame that produced it**, which is not necessarily the
AP the board is currently associated with.

The consequence is practical, not academic: a motion experiment's trials can
silently straddle an AP change, and a CSI record's channel can change under
the experiment's feet. The view therefore **records the source and its
history** and shows it - the HUD's header names the current source, and the
health card carries a `CSI SOURCE HISTORY` line. Nothing is smoothed over.

No network was scanned, and no device other than the one the board was
already associated with was identified or contacted.

---

## 2. The new CSI view

```
+------------------------------------------------------------------------+
| CSI  ● CONNECTED   SOURCE b8:62:1f:e5:ac:62  CH 11  RSSI -61 NOISE -96 |
+------------------------------------------------------------------------+
| SUBCARRIER WATERFALL            64 carriers -> time   189 pkt/s  22s    |
|  (scrolling; the unused band is painted out and labelled)     [S] SPECTRUM|
+------------------------------------------------------------------------+
| SIGNAL CHANGE FROM BASELINE    mean |delta| of the normalised profile   |
|  (rolling; RF PATH CHANGE, NOT A HUMAN DETECTION)                     |
+------------------------------------------------------------------------+
| LINK              SEQUENCE          TRANSPORT        RADIO            |
|  state              id first          malformed        rssi             |
|  packets/s          id last           dropped          noise floor      |
|  packets            gaps              bytes            carriers used    |
|  uptime             missing           silence          baseline         |
+------------------------------------------------------------------------+
```

**The waterfall** replaces the old static bar chart. Rows are subcarriers,
columns are time, newest at the right. Packets are bucketed into columns
(6 packets, ~34 ms) so the picture scrolls at about 30 columns a second -
**about 22 seconds of history** - instead of past in under two. The colour
scale is stretched across the *used* carriers' own 2nd..98th percentile, so
the structure in the troughs is visible instead of being crushed into the
bottom of the ramp.

**The change trace** is the mean absolute deviation of the **normalised**
spectrum from a 12-second moving baseline. Normalising by each packet's own
total is what makes it honest: the total amplitude of a CSI packet is nearly
proportional to the received power, so the raw amplitude mostly measures the
radio (checkpoint 009 measured a within-trial amplitude~RSSI correlation of
0.62-0.93). The panel is labelled **"RF PATH CHANGE, NOT A HUMAN DETECTION"**
in amber, permanently.

**The health counters** are compact and grouped - link, sequence, transport,
radio - and a non-zero counter is drawn in the fault colour. The supervisor
row still says **"telemetry not available"**, because the firmware does not
emit it. The health semantics were not touched: the tests that assert a
floating DAQ channel is badged as noise now reference the theme's semantic
colours instead of literal RGB triples, so the palette can move without
weakening the assertion.

**The raw spectrum** is one keypress away (`S`) and is labelled
`RAW SPECTRUM - DIAGNOSTIC`. It is the right thing to look at when the
waterfall looks wrong, and the wrong thing to look at all the time.

### The theme

`specter/hud/theme.py` is the single source of truth: a deep burgundy and
charcoal ground, muted crimson and rose accents, and a four-step type scale
(`T_MICRO`, `T_SMALL`, `T_LABEL`, `T_VALUE`, plus two display sizes). The
health colours (sage / amber / crimson) are deliberately **not** the accent
colours, so a state can never be mistaken for decoration. Every mode -
OPTICAL, NIGHT-GREEN, POD, ANALOG, CSI - is restyled and preserved.

---

## 3. The guided experiment

`specter/sensors/esp32/experiment.py` is now the **only** judge of a
recording. The CLI tool and the HUD use the same code, so they cannot
disagree.

* `--announce` speaks each phase (macOS `say`) with a lead-in, so a subject
  follows the run by ear.
* `--repeats` and `--shuffle` randomise the order within each repetition,
  because the session drifts and a fixed order makes the drift
  indistinguishable from the condition.
* The app runs it inline: `python -m specter.app --csi esp32 --mode CSI
  --guided --guided-repeats 3 --guided-consent "..."`. The right-hand panel
  shows the phase, the countdown and the trial number; the metrics are
  exported to JSON with a compressed `.npz` sidecar for the packets and a
  CSV for the spreadsheet.
* The export can be analysed **offline** from the JSON with
  `analyse_offline()`.

### Signal change is not human detection

This distinction is now structural, not a caveat in a comment. The live view
says *signal change*. The experiment's verdict is one of:

| situation | the claim |
|---|---|
| the conditions do not separate | `SIGNAL CHANGE ONLY - NO VERIFIED HUMAN DETECTION` |
| they separate, but there is no stationary control | `CONDITIONS SEPARATE, BUT NO STATIONARY CONTROL` |
| they separate, with a labelled stationary control | `VERIFIED HUMAN DETECTION (labelled trial, conditions separate)` |

A **verified** detection needs *both* a labelled trial with a consenting
subject *and* statistics that separate the conditions. Neither alone is
enough, and the module never upgrades one into the other.

---

## 4. Performance

Measured on this machine, `tools/hud_shots.py --bench`:

| | before | now |
|---|---|---|
| HUD render, CSI mode | 41.8 FPS (documented, whole app) | **12.1 ms/frame, 82 FPS** for the renderer alone (6.1 ms / 163 FPS on an idle machine - see the note) |
| CSI state update | - | **31 µs per packet** (0.55 % of one core at 178 packets/s) |
| the two rolling buffers | - | 0.01 ms per snapshot |
| live app, real board | - | **35.7 FPS** end to end, camera included |

**The benchmark machine was busy.** An unrelated training job was running
during these measurements and stole the cores; the render figure was
6.1 ms (163 FPS) when the machine was idle and 12.1 ms (82 FPS) under load.
The conservative number is the one quoted. The live 35.7 FPS figure is from
the real end-to-end run and is the number that matters.

Two optimisations mattered and one was a trap:

* Resizing a **three-channel** image and colour-mapping afterwards is
  **4× faster** than colour-mapping first and resizing the colour image
  (0.36 ms vs 1.5 ms) - the opposite of what I assumed.
* The trace polyline is vectorised, and the canvas is allocated with one
  `np.full` instead of `np.zeros` plus an assignment.

**The single-reader architecture is preserved.** The reader still owns the
USB port; the rolling state is folded from the drained records in the frame
loop; the HUD is a pure drawing surface and never touches the port. The
rolling buffers are fixed size, so the memory is bounded no matter what the
frame loop does.

---

## 5. What is *not* claimed

1. **The motion experiment still has no verified detection.** Checkpoint
   009's result stands: the conditions do not separate, and the apparent
   amplitude difference is confounded with RSSI. The redesign does not
   change that - it makes the *live* view honest about the difference
   between a signal change and a detection.
2. **The metric was chosen after seeing the first run's data**, so the next
   run must fix the metric in advance. The gain-free features are now
   computed and exported, so a held-out run is possible.
3. **The board wedged again** during this work, exactly as checkpoint 008
   describes: it needs a device reset after a period of not being read. The
   live screenshots in `docs/alpha002/` were taken from a freshly reset
   board.
4. **The subject's position during the first experiment is unrecorded**, so
   the most likely cause of the null result cannot be checked from the data.
5. **The supervisor telemetry is still unavailable** - no firmware was
   flashed, and the HUD says so.

---

## 6. Artefacts

| Path | What |
|---|---|
| `specter/hud/theme.py` | the palette, the type scale, the colour ramps |
| `specter/hud/csi_views.py` | the waterfall, the change trace, the health card |
| `specter/sensors/esp32/csi_analysis.py` | the rolling state: waterfall, baseline, change metric |
| `specter/sensors/esp32/experiment.py` | the trial machine, the statistics, the verdict |
| `tools/hud_shots.py` | the screenshots and the benchmark |
| `tests/test_hud_csi_view.py` | 24 tests over the new code |
| `docs/alpha002/hud_csi_live.png` | the live HUD, real board |
| `docs/alpha002/hud_csi_waterfall.png` | the CSI mode, synthetic stream |
| `docs/alpha002/hud_csi_spectrum.png` | the raw spectrum, the secondary view |
| `docs/alpha002/hud_optical.png` | the optical mode, restyled |
| `docs/alpha002/hud_night_green.png` | the night mode, restyled |
