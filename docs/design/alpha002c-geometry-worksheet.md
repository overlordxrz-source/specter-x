# Alpha 002-C — geometry worksheet (corrected, Amendment 1)

**This is not a geometry record.** The record is `<session>.geometry.json`,
written only from measured values after this procedure. No value is copied
from an earlier session or estimated.

## Definitions (Amendment 1)

* **Axis** — the straight line from the **phone antenna** (phone body centre)
  to the **ESP32 antenna** (PCB-antenna end, away from the USB connector).
* **M** — the midpoint of the axis.
* **Longitudinal offset** — displacement along the axis from M, positive
  toward the phone.
* **Lateral offset** — displacement perpendicular to the axis, at the
  midpoint. This is what "off-axis" means; it is **not** a radial distance.
* **S** — the standing spot: **longitudinal 0.00 m** (tolerance ±0.05) and
  **lateral 0.30 m** (tolerance 0.25–0.35).

Superseded: the earlier text said "0.5 m from the midpoint, 0.3 m off the
axis", which mixed a radial distance with a lateral one. The earlier
worksheet construction (0.30 m half-separation with 0.50 m radii) also gave
0.40 m, not 0.50 m. Both are corrected here.

## The one layout to use

With `L = 1.50 m` (accepted range 1.45–1.55):

1. **Clear the path.** Chair, monitor arms and cables out of the line at
   both heights. The chair must not be at S.
2. **Fix the endpoints.** Phone screen facing the board. Neither moves after
   this step.
3. **Measure L** from antenna to antenna. → 1.45–1.55 m.
4. **Mark M** at L/2 on the floor (plumb down).
5. **Mark A and B on the axis**, 0.30 m either side of M (0.60 m apart).
6. **Find S:** from A measure **0.425 m** to the floor; from B measure
   **0.425 m**; where the two marks meet is S.
   *Why 0.425:* √(0.30² + 0.30²) = 0.4243. This puts S exactly 0.30 m
   perpendicular from M.
7. **Verify:**
   * `|S−A| = |S−B| = 0.425 m ± 0.01`;
   * `|S−phone| = |S−ESP32| ≈ 0.81 m ± 0.02`
     (exactly √(0.75² + 0.30²) = 0.808 m at L = 1.50);
   * the torso is off the axis; extend the sweeping arm — the hand crosses
     the line near M, the torso does not.
8. **Mark the feet** shoulder-width apart, facing the midpoint.
9. **Measure antenna heights:** phone body centre, ESP32 antenna end →
   both **0.75–0.85 m**.
10. **Sight the path:** from the phone, nothing stands in the line.

If the torso still touches the line with the feet on the marks, widen the
lateral offset to **0.35 m** (still inside tolerance) and re-mark; record the
actual value.

## Record these measured values

| field | required | measured |
|---|---|---|
| `distance_m` (L) | 1.45–1.55 | |
| `phone_height_m` | 0.75–0.85 | |
| `esp32_height_m` | 0.75–0.85 | |
| `spot_longitudinal_m` | −0.05…+0.05 | |
| `spot_lateral_m` | 0.25–0.35 | |
| `s_phone_m` | ≈ 0.81 (computed) | |
| `s_esp32_m` | ≈ 0.81 (computed) | |
| `phone_orientation` | screen facing board | |
| `recorded_utc` | UTC timestamp | |
| `confirmed_by` | who measured | |

The analysis recomputes `s_phone_m` and `s_esp32_m` from `L`, the
longitudinal and the lateral offsets, and rejects the session (INVALID) if
the measured distances disagree by more than 0.03 m, if the radial offset is
outside 0.25–0.36 m, or if S is closer than 0.70 m to either antenna.

## Decision rule

* All values inside tolerance and the sweep clears the torso → **the
  protocol stands**; write the record and run the 10 s pre-check.
* Any value outside tolerance, or no clear floor at S → **stop**. A
  documented amendment is proposed and reviewed before data; the hypothesis,
  features, test, direction, thresholds and exclusions never change.
