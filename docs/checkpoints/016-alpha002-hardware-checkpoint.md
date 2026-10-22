# Checkpoint 016 — Alpha 002 hardware checkpoint

**Date:** 2026-10-22
**Branch:** `feature/alpha002-esp32-supervisor`
**Verdict:** **The firmware is verified on hardware for everything it claims to
do at this stage, and dense acquisition is demonstrated for 60 s with a
station that was kept talking.** Unattended operation is not demonstrated: the
station goes quiet when it chooses to, and the two phone trials were
confounded by using different traffic apps (checkpoint 017). No flash, no reset, no merge, no change to host networking in this
checkpoint.

Supersedes the subcarrier verdict in checkpoint 015. The v1 score there is
preserved unchanged and is **not comparable** to a v2 score.

---

## 1. The subcarrier defect, and the fix

The v1 check required the set of non-zero subcarrier slots to equal exactly the
52 used slots of a 20 MHz LLTF. I/Q are **int8**: a faint active subcarrier
truncates to exactly `(0, 0)`. One truncation anywhere in a frame failed the
frame, so a healthy link scored 79.7%.

Measured on the preserved capture (672 records):

| Observation | Count |
|---|---|
| Required nulls `{0} ∪ {27..37}` zero | **672 / 672** |
| Exact 52-slot set | 627 / 672 (93.3%) |
| 1–3 extra zero slots in active positions | 45 / 672 |

The 45 exceptions are scattered (slot 55 ten times, slot 39 six, most once),
which is the signature of quantisation, not of a structural change.

**v2 scoring** asserts the property that actually matters:

1. **`subcarrier nulls`** — every required null is zero, in every frame.
   Criterion 100%; a null carrying energy is a real failure.
2. **`active subcarrier coverage`** — all 52 active slots carry energy at least
   once **across the capture**, criterion ≥ 99%. Judged in aggregate so an
   individual truncated slot is not a failure.
3. Fewer than 20 frames to judge → `UNKNOWN`, not a pass.
4. A v1 observation replays as `UNKNOWN` for both lines. The tool refuses to
   infer the v2 answer from a v1 counter.

No other threshold moved: activity 5/s, gap 1.0 s, malformed 0, continuity 95%,
drops 0, drift 0.5%, RSSI −85…−15, noise floor ≤ −80.

## 2. Two further harness defects, found by re-running

1. **A parse error killed the CSI reader.** A spliced line on the native USB
   path (`CSI_DATA,…,csSPECTER_STAT,…`) raised out of `CsiParser.feed`, the
   thread died, and the run reported 0 packets. Preserved as
   `preflight-phone-station-v2-attempt1-crashed.*` — the console path had
   captured 102 KB while the CSI thread was already dead, which is exactly the
   failure mode. `feed` is now wrapped; a bad line counts as malformed and the
   capture continues.
2. **Bytes that arrived before the window were counted as data.** Opening a
   live stream starts mid-record; the backlog is also where splices live. Both
   ports now drain for 0.25 s before the measurement window begins.

## 3. Scores, separately versioned

| | v1 (preserved) | v2 (corrected) |
|---|---|---|
| `scoring_version` | absent | **2** |
| window | 60 s | 60 s |
| CSI packets | 300 | 74 |
| subcarrier nulls | exact-set 79.7% → FAIL | **74/74 clean → PASS** |
| active coverage | — (not measured separately) | **52/52 slots → PASS** |
| malformed / seq gaps / drops | 0 / 0 / 0 | 0 / 0 / 0 |
| USB↔console drift | 0.05% | 0.17% |
| activity | 5.0/s → FAIL | 1.3/s → FAIL |
| longest gap | 1.222 s → FAIL | 16.443 s → FAIL |

The two runs are **not** comparable on rate: v1 was captured while traffic was
being generated, v2 after it stopped. They are comparable on structure, and
there the corrected scoring agrees with the hardware: the IQ map is intact.

v2 is a fresh capture. The v1 run's raw bytes were never saved, so a corrected
score *of that run* cannot be derived; that gap is why `--raw-out` now exists.

## 3a. Addendum — the same link, 60 s, fully passing

Every earlier run failed on the same thing: the station slept. With the phone
kept talking (the later traffic app, in the foreground), the same 10 Hz ping
to `192.168.4.1`, on the same link, produced:

| | |
|---|---|
| CSI frames | **2364** (39.0/s) |
| data frames, 122 B | **600** → 10.07/s, i.e. the offered rate |
| null-data frames, 28 B | 1757 (the station's association-keeping traffic) |
| longest gap | **0.224 s** host-side, 79 ms device-side |
| gaps > 0.5 s | **0** |
| subcarrier nulls | 2364 / 2364 |
| active coverage | 52 / 52 |
| malformed / seq gaps / queue drops | 0 / 0 / 0 |
| USB↔console drift | 0.25% |
| **verdict** | **PASS** |

Cadence is bimodal, not uniform: median 26.9 ms, p95 61.8 ms, and only 50.3% of
intervals are under 28.6 ms. So the stream is gap-free but **not** a steady
35 Hz feed; a 35 FPS HUD cannot be assumed from this.

What this changes: dense acquisition is demonstrated, not merely possible.
What it does not change: the earlier failures were the station going quiet,
which is a property of the phone and its traffic app, not of the firmware.
Which of the candidate mechanisms was responsible was never separated
(checkpoint 017).

**Caveat on the continuity metric.** It compares *all* callbacks to the offered
rate, so null-data frames inflate it (394% here). It passes, but it is not a
loss measurement. The honest loss figure comes from the data frames alone:
600 received against 596 expected at 10 Hz for 59.6 s, i.e. ≤ 0.7%.
Splitting the metric by frame length is a follow-up.

## 4. Packet cadence: measured versus hypothesised

**Measured, same link, same 10 Hz offered load, two trials of the phone:**

| trial | frames | data frames (122 B) | null-data (28 B) | longest gap |
|---|---|---|---|---|
| earlier trial, earlier traffic app | 17 per 60 s | **1** | 16 | 35.1 s |
| later trial, different traffic app | 2364 per 60 s | 600 | 1757 | 0.079 s |

**Correction (checkpoint 017).** The two trials used **different traffic
apps**, so they are confounded. The difference cannot be attributed to the
phone's power saving alone: whether the app sends, at what rate, and whether
the operating system suspends it all changed at the same time. The labels
above therefore name the *trial*, not a measured phone state — "idle" was
never measured, it was inferred.

**What is established regardless of the confound:** the station put **one**
payload frame on the link in 60 seconds in the failing trial and **600** in
the succeeding one. The silence is **phone-side, not firmware-side**: the
same association, the same AP, the same firmware and the same offered load
yield either 39 frames/s or 0.3 frames/s, and the board's own counters never
show loss (`drop_old=0`, `drop_new=0`, `q=0`) in any run.

**Not measured:** which mechanism was responsible. At least three candidates
were never separated: 802.11 power save with a DTIM wake schedule, the
operating system suspending the traffic app, and the app simply not sending.
No 802.11 frame capture was taken, the phone's power-save state was never
read, and there was no control with power save known to be off. The 28-byte
null-data frames are consistent with a station holding association in power
save, but they are also present in the succeeding trial, so they do not
identify the mechanism by themselves.

The consequence that survives every explanation: an unattended iOS station
cannot be relied on for a continuous feed, so unattended operation needs a
station whose behaviour we control.

## 5. Verified on hardware

| Claim | Evidence |
|---|---|
| App-only write at `0x10000` is safe and sufficient | write + independent read-back verify; bootloader and partition table byte-identical before and after |
| Firmware boots and runs on this board | boot log from `0x10000`, no abort/watchdog |
| SoftAP + own DHCP come up | `SPECTER-LAB` ch 6, `192.168.4.1` |
| **CSI callback fires in SoftAP mode** | `csi_cb` rises with no station at all, and with a station attached |
| Station association and peer identification work | peer MAC stable across the whole capture |
| Channel metadata correct | `ch=6` on all 676 records, no roam |
| IQ structure intact | 128 B / 64 slots on every record; nulls zero 672/672; `first_word_invalid=0` |
| No firmware-side loss | `drop_old=0`, `drop_new=0`, `q=0` throughout |
| Both USB paths carry the same stream | drift 0.05% (v1), 0.17% (v2), 0.25% (dense run) |
| Dense, gap-free acquisition is achievable | 2364 frames in 60 s, 39.0/s, longest gap 79 ms, zero gaps > 0.5 s |
| Offered load is received without loss | 600 ping frames against 596 expected, ≤ 0.7% |
| Rollback was unnecessary but real | verified before the write; never exercised |

## 6. Still unproven

| Question | Status |
|---|---|
| Dense, gap-free acquisition | **demonstrated** for 60 s: 39/s, max gap 79 ms, zero gaps > 0.5 s |
| Continuity against a known offered rate | **demonstrated**: 600 ping frames vs 596 expected, ≤ 0.7% loss |
| Dense acquisition unattended | **no** — the station goes quiet when it chooses to; the cause was never separated |
| Uniform 35 Hz cadence | **no** — median 26.9 ms, p95 61.8 ms, bimodal |
| Motion or vital-sign detection | **nothing measured**; no human-subject run |
| SoftAP under WPA2 | **no** — the AP is currently open |
| Correct flash-size declaration | **no** — runtime falls back to 2 MB and warns |
| Cause of the cadence | **hypothesis only** — phone-side either way, mechanism not separated |
| Multi-station behaviour, long soak | **no** |
| Behaviour on the campus network | deliberately not tested |

## 7. Follow-ups

1. WPA2 on the SoftAP (`CONFIG_SPECTER_LAB_PASSWORD` is empty).
2. Declare 16 MB properly in the app image header.
3. A station whose sleep behaviour we control — second ESP32, or a host with
   power save known to be off. This is the control condition the cadence
   hypothesis still lacks, and it is also what unattended operation needs.
4. Split the continuity metric by frame length. It currently counts null-data
   frames toward the offered rate and so reports 394% where the data-frame
   loss is ≤ 0.7%.
5. Only then: motion, and only against the null distribution.

## 8. Evidence

`runs/alpha002_hw_validation_20261022/` (gitignored):

| File | SHA-256 (first 16) |
|---|---|
| `preflight-phone-station.json` (v1, untouched) | `e727c62b51df2f29` |
| `preflight-phone-station-v2.json` | `fbfac8ee218b6596` |
| `preflight-phone-station-v2.raw` | `ead83703030f8149` |
| `phone-station.raw` (672 records) | `f2c208488d60f975` |
| `preflight-phone-station-v2-ping10hz-run4.json` (PASS) | `c3382bc7d0c9b694` |
| `preflight-phone-station-v2-ping10hz-run4.raw` | `35da65ce03ccc354` |

Regression fixtures committed: `tests/fixtures/esp32_csi/phone_station_lltf.jsonl`
— one exact record and two real truncation cases from the capture.

Tests: **287 passed, 1 skipped.**
