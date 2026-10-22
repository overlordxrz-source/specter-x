# Checkpoint 015 — phone-as-station CSI validation

**Date:** 2026-10-22
**Branch:** `feature/alpha002-esp32-supervisor`
**Verdict:** **LINK VALIDATED. SCORED PREFLIGHT FAILED, for three reasons that are
not a firmware failure.** A real station associated, was identified, produced
CSI for the whole capture with zero malformed lines, zero sequence gaps and
zero queue drops. The failures are one stimulus property of the phone and one
over-strict check in the harness.

Evidence: `runs/alpha002_hw_validation_20261022/` (gitignored).

| File | SHA-256 (first 16) |
|---|---|
| `phone-station.raw` (150 s, 320 115 B) | `f2c208488d60f975` |
| `phone-station-timeline.log` | `fe7813ce08d47e7f` |
| `preflight-phone-station.json` (60 s scored) | `e727c62b51df2f29` |
| `capture_phone.py` | `f0a4f2af7f1d6a53` |

---

## 0. Correction, later the same day

Two things in this record were wrong or incomplete and are corrected in
checkpoint 016:

- **The subcarrier check was defective**, not the link. Scoring v2 replaces the
  exact-set test with a structural null check plus aggregate coverage. The v1
  score below is preserved unchanged and is **not comparable** to a v2 score.
- **The cause of the packet cadence is a hypothesis, not a finding.** This
  checkpoint originally called it "textbook power-save (DTIM)". No 802.11
  frame capture was taken and the phone's power-save state was never observed.
  The cadence itself is measured; the mechanism is not.

## 1. Conditions

A phone joined `SPECTER-LAB` as the station. The Mac stayed on Kent State
Wireless the whole time; the board was monitored only over USB/UART. No flash,
no reset, no change to host networking, no campus gateway involvement. The
scored test reads both USB paths, so it needs exclusive use of the console
port; the background capture was stopped for it.

## 2. Station state, measured

| Check | Measured |
|---|---|
| Association | `peer=16:01:cc:d5:06:18`, locally-administered (private) MAC |
| Peer identification | set on `AP_STACONNECTED`, stable across every status line |
| CSI callback growth | `csi_cb` 661 → 1545 over the capture, monotonic |
| Accepted / printed | `printed` 610 → 1447; `csi_cb − printed` ≈ 98 rejected ambient frames |
| Channel | `ch=6` on all 676 records, no roam |
| RSSI | −29 … −47 dBm |
| IQ length | 128 B = 64 complex samples on **every** record |
| `first_word_invalid` | 0 on every record |
| Queue | `drop_old=0`, `drop_new=0`, `q=0`, `q_high=13` |
| Sequence | 3 single-record gaps in 664, with drop counters at zero → capture-path, not firmware |

Null-slot structure is exact: slots `{0} ∪ {27..37}` are zero in **672/672**
records.

## 3. The 60 s scored test

```
csi callback activity        5.0/s           >= 5/s        FAIL
csi callback fires at all    yes             > 0           PASS
packet continuity            5.0/s           no rate given UNKNOWN
longest inter-packet gap     1.222s          <= 1.0s       FAIL
malformed lines              0               <= 0          PASS
sequence gaps                0               0             PASS
rssi                         -41 dBm         -85..-15      PASS
noise floor                  -95 dBm         <= -80        PASS
channel                      6               one value     PASS
subcarrier map               79.7% of 52     >= 99%        FAIL
phy rate                     dominant 9 (71%) recorded     PASS
device queue drops           0               <= 0          PASS
usb vs console byte drift    0.05%           <= 0.5%       PASS
supervisor telemetry         not in build    deferred      DEFERRED

PREFLIGHT: FAIL
```

297 callbacks and 295 printed records in 60 s. Status `csi_cb` 2366 → 2663,
`printed` 2151 → 2446.

## 4. Why each failure happened

### 4.1 Inter-packet gaps — measured cadence, unexplained mechanism

Inter-packet intervals over 123 s: median **0.011 s**, p95 0.956 s, and 63 gaps
> 0.5 s, recurring roughly every 2 s, the longest 1.96 s. The mean rate is
5.5/s only because frames arrive in bursts separated by silences.

That is the observation. The **explanation is unverified**. Power save with a
DTIM-driven wake schedule would produce this shape, but so would several other
mechanisms, and none was tested: no 802.11 frame capture, no read of the
phone's power-save state, no control condition with power save known to be
off. Treat "power save" as the leading hypothesis, not the cause.

Consequence, independent of cause: ~5 packets/s with holes of a second or more
is **not** a usable sampling rate, and the 35 FPS HUD cannot be fed from it.

### 4.2 Callback activity 4.95/s vs a 5/s threshold

The same cause, measured against a threshold that was chosen for a saturated
link. The link was up; the stimulus was sparse. Borderline, and honest to
report as a FAIL rather than round up.

### 4.3 Subcarrier map — the check is wrong, not the data

The check requires the non-zero slot set to equal exactly the 52 used
subcarriers. Measured over 672 records: 627 (93.3%) match exactly; 45 have
1–3 **extra** zero slots, scattered (slot 55 ten times, slot 39 six, most
once). Those are subcarriers whose int8 I and Q both truncated to zero at low
amplitude. The null slots are never non-zero, which is the property the check
was meant to protect.

In the 60 s window the same effect scored 79.7%. That is a quantisation
artefact reported as a format regression. A correct assertion is:

* every null slot is zero (holds in 672/672), and
* aggregated over the capture, all 52 used slots carry energy at least once
  (also holds).

This was a defect in `tools/esp32_lab_preflight.py`, not in the firmware, and
it is fixed in checkpoint 016 under scoring v2.

## 5. What was not proven

- Dense, gap-free acquisition. The phone is a poor sampler.
- Packet continuity against a known offered rate — no controlled generator
  existed, so the check is UNKNOWN.
- Anything about the campus link, which was never used.

## 6. Follow-ups carried forward

1. WPA2 on the SoftAP (currently `WIFI_AUTH_OPEN`).
2. Flash-size declaration in the app image header (runtime falls back to 2 MB).
3. Subcarrier-map assertion in the preflight tool.
4. A station that does not power-save — second ESP32, or a host with PS
   disabled — before any timing-sensitive measurement.
