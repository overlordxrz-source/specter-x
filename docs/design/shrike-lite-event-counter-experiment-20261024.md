# Shrike Lite event-counter experiment — prepared, not authorized

**Status: PREPARED / NOT AUTHORIZED / NOT PROGRAMMED.**
24 October 2026. This document assesses the existing event-counter design and
defines the next physical gate. No event-counter bitstream was generated,
loaded or flashed. No external signal, jumper, probe, firmware change, OTP or
factory-file edit was made. Work is isolated on
`research/specter-sync-event-counter`, based on the successful F16 heartbeat
commit `e8b4bd0`.

## Artifacts reviewed

| File | SHA-256 |
|---|---|
| `firmware/shrike_lite/fpga/event_counter/main.v` | `698945d34c856897ecca8047f59db529dcb3981dcc77775b61a12688eacab8aa` |
| `firmware/shrike_lite/fpga/event_counter/tb_event_counter.v` | `b62f329caa2c4d5a70ee6be5a0c6e281d39e795cbb143653967b5c1a9493d31f` |
| `firmware/shrike_lite/fpga/event_counter/tb_event_counter_hazards.v` | `5a17a96dd3ffbe8b3838c4c8d90effb1fe02f6a771e16cd340e01faa860bb2d2` |
| `firmware/shrike_lite/rp2040/event_counter_readout_bounded.py` | `4c1d8c557d4f48551aab5c8cb9ab03cf217d2c6a12f2f7f9eeb110bd0a427a68` |

The existing `event_counter_readout.py` is retained unchanged as the earlier
unbounded prototype.

## Design assessment

### Pin ownership and physical nets

Published v1_r0.4/v1_r0.5 PCB sources agree on these nets:

| Signal | FPGA | Board path | RP2040 |
|---|---|---|---|
| Event input | F1 (U5 pad 14) | J2 pin 17; **no bias resistor** | — |
| Read clock | F18 (U5 pad 9) | R7 → J2 pin 15 | GPIO14 (U4 pad 17) |
| Read data | F17 (U5 pad 8) | R8 → J2 pin 14 | GPIO15 (U4 pad 18) |

- F1 is **floating** unless externally biased. The FPGA input has no local
  pull resistor in the reviewed sources. No count claim is valid while F1 is
  floating.
- F17/F18 are the internal MCU–FPGA link. Never attach external wires to J2
  pins 11, 12, 14 or 15.
- The factory `main.py` configures RP2040 GPIO14 and GPIO15 as **outputs** and
  toggles them. Loading an event-counter bitstream while those directions
  remain outputs would contend with FPGA F17 (read data). The factory loop must
  be interrupted through the normal REPL and GPIO15 must be set to input
  **before** the event bitstream is loaded. GPIO14 may be set output-low as the
  read clock.

### CDC and snapshot coherence

- `event_in` and `rd_clk` each pass through a 3-stage synchronizer sampled by
  the 50 MHz internal clock. Event detection requires a pulse high/low width
  above the synchronizer sampling interval; the Phase 0 protocol recommends
  ≥1 µs for the first source.
- `event_count` and `last_timestamp` update on the same 50 MHz edge. The
  snapshot load `{event_count,last_timestamp}` is therefore coherent.
- An event arriving during an active 64-bit read is excluded from that
  snapshot and appears in the next idle reload. The hazard simulation confirms
  this.
- `IDLE_CYCLES=50000` is 1 ms at nominal 50 MHz. The host waits 3 ms before a
  read and shifts 64 bits at ~4 µs/bit (~256 µs total).
- **Mid-read reload hazard:** if the host pauses longer than the idle reload
  interval between rising edges, `shift_reg` reloads and the host assembles a
  mixed old/new word. The hazard test reproduces this. The bounded readout
  aborts on any edge gap above **250 µs**; no automatic retry is allowed.
- The 32-bit timestamp wraps every ~85.9 s at nominal 50 MHz. The physical
  trial must stay below 60 s and flag any wrap/discontinuity.

### Offline verification

Nominal simulation:

```text
PASS: event counter snapshot, count and timestamp checks
```

Adversarial simulation:

```text
PASS: event during read left the active snapshot coherent
PASS: mid-read pause reproduces a non-coherent mixed snapshot
PASS: event-counter CDC/idle hazard controls
```

Bundled Yosys 0.59 synthesis (no PNR, no bitstream, no timing claim):

```text
596 cells; 0 problems; 6 ports
127 DFFE, 38 DFF, 64 MUX, ...
```

Logs: `runs/shrike_lite_event_counter_20261024/` (`hazard_sim.log`,
`synthesis.log`, nominal simulation log). Full Go Configure place-and-route,
I/O-planner bitstream generation and timing analysis are **not** run yet; they
require a later authorized build. The static pin mapping above still requires
verification in the installed I/O Planner before any build.

## Required separate authorizations

The following are **not** covered by this preparation:

1. An event-counter bitstream build and its exact hash.
2. Any physical load of that bitstream.
3. Any F1 bias/jumper or external pulse source.
4. Any external probe or measurement.

The successful F16 heartbeat authorization did not authorize this experiment.

## Bounded physical protocol — after separate authorization

### Preconditions

- Owner authorization names the exact staged event-counter bitstream SHA-256,
  one load, exact port/device and the F1 source/bias decision.
- USB-C power only; no 5V header; no external 5V; all signals 3.3 V CMOS.
- Factory `main.py` and `blink_all.bin` backups verified; no factory file edit.
- One device owner; deconflict the port and stop other readers. The
  noncooperating-reader limitation is unchanged and must be handled by operator
  evidence.
- F1 is either left physically unconnected **and excluded from count claims**,
  or biased/pulsed under a separate electrical authorization. Do not leave a
  claim-bearing F1 floating.

### Pin-ownership and load sequence

Use the normal REPL path, then `mpremote resume` for subsequent operations so a
normal soft reset cannot rerun the factory loop between steps:

1. Interrupt the factory loop via the REPL. Do not edit `main.py`.
2. Read back and hash the factory files.
3. Configure RP2040 GPIO15 as **input** and GPIO14 as **output, low** before
   loading the event bitstream. Configure any future GPIO6 pulse source as
   **input/low** until its separate authorization.
4. Stage the event-counter image as a new temporary file; read it back and
   verify exact size/hash.
5. Load exactly once with `shrike.flash('<event-image>', 46408)`. No OTP, no
   repeat, no normal soft reset during the test.
6. Read snapshots only through the bounded readout; never drive GPIO15 after
   the bitstream is active.

### Phase A — readout framing only (F1 not biased)

If a separately authorized bitstream is loaded with F1 left unconnected, only
the following may be assessed:

- 64-bit frames decode without readout timeout;
- no rising-edge interval exceeds 250 µs;
- repeated reads complete without host error.

Do **not** accept event counts, zero-count claims or timestamp behavior in this
phase: F1 is floating. If count is unstable, stop; do not reinterpret noise as
an event.

### Phase B — biased no-event baseline (separate F1 authorization)

After a separate authorization to hold F1 at a defined 3.3 V CMOS level:

- Hold F1 low.
- Read at least 10 consecutive snapshots with bounded gaps.
- Require a stable `event_count` (expected 0 in a clean start), no skipped
  reads, and a monotonic timestamp modulo 2^32.
- If the count changes with no source, stop; do not continue to Phase C.

### Phase C — bounded pulse capture (separate pulse authorization)

Only after separate authorization for the exact source/jumper:

- Known 3.3 V CMOS source at F1; common ground; ≥1 µs high/low; first planned
  source 1 Hz / 10 ms high via RP2040 GPIO6 loopback or a reviewed external
  generator.
- Capture <60 s to stay well inside the 32-bit timestamp wrap.
- Every snapshot read uses the bounded readout; any 250 µs gap aborts the
  frame.
- Require count increments exactly once per observed pulse, no missing or
  duplicate increments, monotonic timestamps for increasing counts, and an
  explicit record of any wrap/discontinuity.
- Preserve raw CSV, host time, source settings, supply, temperature and the
  exact bitstream/firmware hashes.

### Stop conditions

Stop immediately—do not automatically repeat, retry programming or reconnect—
on any of:

- an unexpected reset/banner, port error or device disappearance;
- any readout edge gap above 250 µs or a malformed 64-bit frame;
- event count change without a known pulse, missing/duplicate events, or
  backwards counter;
- F17/F18 contention suspicion or unexpected board behavior;
- any external source exceeding 3.3 V, uncertain ground, or unexpected current.

### Rollback

1. Remove the staged event-counter image.
2. Soft-reset to run the factory `main.py`; this reloads factory
   `blink_all.bin`.
3. Read back and hash `main.py` and `blink_all.bin`; confirm no extra files.
4. Preserve the raw capture/logs and failures. No automatic re-run.

## Acceptance and non-claims

A successful Phase C means only that this bounded source/readout produced
consistent counts and timestamps for this run. It does **not** establish
oscillator accuracy, absolute time synchronization, sustained USB reliability,
event-detection accuracy, human sensing or any motion/spatial claim.

No event-counter bitstream has been generated, staged or programmed by this
preparation.
