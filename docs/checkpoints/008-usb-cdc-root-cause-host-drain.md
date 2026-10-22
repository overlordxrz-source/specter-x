# SPECTER-X checkpoint 008 — the USB CDC link has *two* separate faults

**Date:** 2026-10-21
**Branch:** `feature/alpha002-esp32-supervisor`
**Status:** the stall investigated in checkpoint 007 splits into **two
independent faults**, and the split is the useful result:

| | Fault A — packet loss | Fault B — the device pauses |
|---|---|---|
| **Cause** | **host-side**: the host does not drain the CDC endpoint fast enough | **device-side**: nothing the host does |
| **Symptom** | packets lost (id gaps), lines truncated (malformed), eventually a permanent wedge | the whole CDC path goes silent for ~5.5 minutes, then resumes by itself |
| **Preventable from the host?** | **yes** — drain continuously | **no** |
| **Recovery** | a device reset, once it has wedged | **it comes back on its own** |

Checkpoint 007's "device-side" conclusion was right about **Fault B** and
wrong about **Fault A**. This checkpoint replaces the single-cause account
with the two-fault one, and gives the host-side rule that prevents Fault A.

**No firmware was flashed, no bootloader was entered, and the 16 MB backup
was not touched.** Every experiment is read-only apart from the deliberate
manual hard-resets used to recover the instrument between experiments.

---

## 1. Fault A — packet loss is caused by the host's read cadence

### The control that was missing

The application and the baseline tool read the CDC endpoint in a tight loop
and always reported a clean link. The health monitor read the same port
with a 50 ms sleep between reads — and it was the tool that produced every
"device-side" observation. So the experiment is: same device, same tool,
same duration, reset beforehand; **the only variable is the host's read
cadence**.

| Arm | Host poll | Packets received | Of the device's ids | Gaps | Missing | Malformed |
|---|---|---|---|---|---|---|
| **A** | 50 ms | 6 880 (38/s) | **47.8 %** | **777** | **7 516** | **481** |
| **B** | continuous | 12 930 (72/s) | **100.0 %** | **0** | **0** | **0** |

(Arm A and arm B are `runs/soak/expA_slow_poll.json` and
`runs/soak/expB_continuous.json`, both 180 s, both preceded by a reset.)

Under a slow poll the device's sequence ids skip — whole CSI packets were
*not* delivered — and 481 lines arrived truncated, i.e. the bytes arrived
but a line was cut. The bytes that do arrive are complete (~433 B/packet):
the loss is the device not sending, or sending into a full TX FIFO.

### The onset is progressive, not instantaneous

Arm A's counters, sampled every 30 s:

| t | packets | gaps | missing | malformed |
|---|---|---|---|---|
| 0–60 s | 0 → 3 649 | **0** | **0** | **0** |
| 90 s | 3 649 | 16 | 178 | 8 |
| 120 s | 4 742 | 270 | 2 545 | 150 |
| 150 s | 5 831 | 523 | 5 017 | 303 |

The link is *clean for the first minute* and then degrades at an
accelerating rate. **This is why 60-second baselines never saw it**, and why
the six-run campaign of checkpoint 007 was clean.

### The wedge is reproducible on demand

Driving the port with the 50 ms poll until it went silent:

```
slow-poll phase : 39 027 packets over 335 s, then silent
continuous drain for 60 s after the wedge : 0 packets
reopen the port, continuous drain 30 s     : 0 packets
```

**The wedge is the terminal state of the same overload.** A device reset is
the only thing that recovers it.

### The safe operating envelope

A sweep of the host's poll interval, 180 s per arm, each preceded by a
reset (`tools/esp32_csi_poll_sweep.py`, `runs/soak/poll_sweep_180s.json`):

| Host poll | Packets/s | KB/s | Arrived | Gaps | Missing | Malformed |
|---|---|---|---|---|---|---|
| continuous | 169 | 76.3 | 100.0 % | 0 | 0 | 0 |
| 5 ms | 180 | 77.1 | 100.0 % | 0 | 0 | 0 |
| 20 ms | 170 | 74.3 | 100.0 % | 0 | 0 | 0 |
| 50 ms | 182 | 78.3 | 100.0 % | 0 | 0 | 0 |

**Honest reading of this table:** 50 ms is *not reliably* bad — in these
arms it was clean, while in arm A the same 50 ms poll lost 52 % of the
packets. The 50 ms poll sits near the edge: sometimes the device's print
path keeps up, sometimes it does not, and the onset is slow (60–90 s) and
stochastic. The 60 s arms show the same thing from the other side — at
50 ms the device *throttled itself* to 110 packets/s (45.7 KB/s) instead of
the usual ~180/s (77 KB/s) while still reporting 100 % arrival: the device
absorbs the overload by slowing down, until it cannot.

**The rule that follows: drain the endpoint continuously.** Not "poll
slowly but often enough" — every measurement that lost packets used a sleep
in the read loop, and every measurement that was clean drained without one.

### What does *not* cause a wedge

Five candidate triggers were tested and eliminated:

| Hypothesis | Test | Result |
|---|---|---|
| A gap in reading wedges the link | pause reading for 5 s, then 15 s | **resumes cleanly both times** (4 799 and 6 112 packets after the pause) |
| Closing the port with a backlog wedges it | drain 8 s, close with the device's FIFO still full, reopen | **recovers** (731 packets) |
| Leaving the port closed wedges it | close the port for 5 s, 30 s, 90 s, 240 s, then reopen | **recovers every time** (664, 1 673, 1 650, 985 packets) |
| The host's USB stack is broken | the board's other USB path (CH343) during every stall | **always works** |
| A hard reset is the only way out | continuous drain, then reopen, after a wedge | **neither works**; the reset is |

So the wedge is **not** caused by a pause, a close, a reopen, or a host USB
fault. It is the *accumulated overload* of the device's TX path, and the
one thing that always ends it is a device reset.

### The application's reader already complies

`specter/sensors/esp32/reader.py` reads everything available and only
sleeps (5 ms) when the port is *empty*:

```python
waiting = ser.in_waiting
if waiting:
    data = ser.read(waiting)      # read everything, immediately
    ...
else:
    ...
    time.sleep(0.005)              # only when there is nothing to read
```

That is the shape the sweep says is safe, and it is consistent with the
application never having reported a gap.

---

## 2. Fault B — the device pauses itself, even under perfect draining

This is the fault checkpoint 007 saw, and it survives every control.

### The 20-minute soak, draining continuously

`tools/esp32_usb_health.py --seconds 1200 --poll-interval 0.0`:

```
received 94 413 packets   (100.0 % of the device's ids)
gaps 0   missing 0   malformed 0
33.7 KB/s average
2 stalls, at t = 323 s and t = 653 s
```

**The integrity was perfect across the whole 20 minutes.** But the link
went silent twice.

### The control: no reopen at all

`tools/esp32_csi_baseline.py --seconds 1200` opens the port once and never
touches it again — no reopen, no reset, nothing:

```
received 115 139 packets   (100.0 % of the device's ids)
gaps 0   missing 0   malformed 0
40.6 KB/s average
arrival interval: median 6.06 ms, p95 9.12 ms, MAX 331 035 ms
```

**The 331-second maximum arrival interval is the fault, in one number.**
The link went silent for 5.5 minutes — and it came back **by itself**,
because the run continued to 1 200 s with a perfect sequence.

### The 320-second signature

Across three independent stalls in two runs, the silence is the same length:

| Run | Stall at | Silence | Resumed at | Length |
|---|---|---|---|---|
| continuous soak, with reopen | 323 s | device silent | 643 s | **320 s** |
| continuous soak, with reopen | 653 s | device silent | 972 s | **319 s** |
| baseline, no reopen | — | device silent | — | **331 s** |

The reopen happened at the *start* of each silence, so "reopen fixed it" and
"it recovered by itself" are not distinguishable in that run. The baseline
run settles it: **there was no reopen there, and it still recovered.**

The id sequence was *consecutive across the silence* (`first_id 114 809`,
`last_id 229 947`, span == packets received, 0 missing). So during the
5.5 minutes the device produced **nothing at all** — no packets, no ids —
and then carried on from exactly where it had stopped. It is a *pause*, not
a drop and not a corruption.

### What the pause is not

* **Not a host USB fault** — the board's other USB path (the CH343 UART0
  bridge) works throughout, and macOS logs no USB error.
* **Not a host drain problem** — the host was draining continuously, at
  100 % arrival, with zero gaps before and after the silence.
* **Not a Wi-Fi association loss** — the device kept reporting the same AP
  (`b8:62:1f:e5:ac:62`), the same channel (11) and a plausible RSSI
  (−89…−57 dBm) before and after.
* **Not something the host can clear** — a reopen does not shorten it, and
  in the deliberate wedge experiment neither a reopen nor continuous
  draining revived the device at all.

**It is a device-side pause of the whole output path, of about 5.5 minutes,
that resolves itself.** Diagnosing it further needs to happen on the
device — the CDC path is silent, so the device's own log is silent with it.
That is precisely what the supervisor telemetry (Alpha 002-C) would buy:
a heartbeat and a health record from the device, so a host-visible pause
becomes a *device-reported* pause.

---

## 3. What this changes

* **Two independent faults, two different owners.** Fault A is the host's
  to prevent (drain continuously — the app already does). Fault B is the
  device's to diagnose and fix (firmware).
* **Checkpoint 007's "device-side" verdict was right about Fault B and
  wrong about Fault A.** Its evidence was accurate; the inference from it
  was single-cause when the situation was two-cause.
* **Checkpoint 007's observation — "every wedge happened after the host
  released the port" — is explained.** Releasing the port, or polling
  slowly, means not draining; that is Fault A; that is what wedges the
  device. The release is the trigger, but the overload is the cause.
* **The host must not treat "the port opened" as "the device is talking"**,
  and it must not treat a stall as fatal: a 5.5-minute pause that resolves
  itself must be *reported* (it is an acquisition interruption, and it
  breaks the "no outages" criterion), not papered over.
* **The firmware needs to survive a slow host** — it must drop and count
  rather than corrupt, and it must report its own drops so a host-side gap
  and a device-side drop are distinguishable. See the updated
  [`docs/design/esp32-firmware-integration.md`](../design/esp32-firmware-integration.md).

---

## 4. The baselines still stand, with one refinement

The six 60-second baselines (checkpoint 007 §2) were taken with a
continuously-draining tool, so they are valid: 137.4–155.7 packets/s, mean
146.0, stdev 7.1, **0 gaps, 0 missing, 0 dropped, 1 malformed, 0 outages**,
channel 11 throughout, RSSI −86…−56 dBm.

The refinement is about the *rate*. Across every clean run in this
checkpoint the device's produced rate ranged from **72 to 190 packets/s**,
and the sweep's 60 s arm at 50 ms shows 110/s — a device absorbing an
overload by slowing down. The observed rate is therefore a property of the
*link's* health, not only of the Wi-Fi environment, and a rate below
~120 packets/s is a symptom worth alerting on, not just a number.

---

## 5. Limitations — stated plainly

1. **The device's internal mechanism is still not known**, for either
   fault. We have shown *when* the device drops and *when* it pauses, and
   that the host's read cadence is the trigger for the first; we have not
   shown which part of the ROM's USB-serial path overflows, or what makes
   the device pause for 5.5 minutes.
2. **The 50 ms behaviour is intermittent**, so "continuous draining" is
   justified by the consistent absence of loss in every clean run and the
   consistent presence of it in every lossy run — not by a clean threshold.
   The threshold is between 5 ms (always clean) and 50 ms (sometimes clean).
   A finer sweep (10, 25, 35, 45 ms) would locate it.
3. **The wedge was reproduced once, deliberately** (335 s under a 50 ms
   poll) and seen once incidentally (377 s). Two samples.
4. **The pause is characterised by its length, not its cause.** 320–331 s
   across three instances is a strong signature, but three samples.
5. **The 20-minute runs are one each.** A longer unattended soak (hours)
   is the obvious next measurement for the pause's rate of occurrence.
6. **Only the id counter proves loss.** The device's `id` is per printed
   packet, so a callback the device never printed is invisible. What we
   measure is "of the ids the device printed, how many reached the host".
7. **The motion experiment still has only its null control.** The positive
   control needs a consenting subject.
8. **The DI-188 is still disconnected**, so its acceptance test skips.

---

## 6. Artefacts

| Path | What |
|---|---|
| `tools/esp32_csi_poll_sweep.py` | the poll-interval sweep (new) |
| `tools/esp32_usb_health.py` | the soak monitor; fixed the unconditional 50 ms sleep, added `--poll-interval` and a reopen probe |
| `runs/soak/expA_slow_poll.json` | arm A — 50 ms poll, 180 s, 47.8 % arrived |
| `runs/soak/expB_continuous.json` | arm B — continuous poll, 180 s, 100 % arrived |
| `runs/soak/poll_sweep.json` | 60 s arms |
| `runs/soak/poll_sweep_180s.json` | 180 s arms |
| `runs/soak/soak_continuous_20min.json` | 20-minute continuous soak, with reopen |
| `runs/soak/baseline_20min_noreopen.json` | 20-minute single-open run, no reopen — the 331 s pause |
| `docs/alpha002/csi_reference_stationary.png` | the stationary reference profile |

`runs/` is git-ignored, so the JSON evidence is copied to
`docs/checkpoints/evidence/` (the one exception, the 11.6 MB null-control
recording, is referenced by checksum instead).

**The firmware backup is untouched** —
`~/Downloads/esp32s3-csi-flash-backup-20261021-full.bin`, 16 777 216 B,
SHA-256 `51ae09689e19217aa52ff7d136313d2354345f9faf42ec50ee75324e602458f0`.
