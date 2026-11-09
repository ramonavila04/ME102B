# Pill dispenser redesign plan

Goal: a single-canister dispenser that releases **exactly one pill per cycle with
zero jams**, proven in a physics simulation and buildable from FDM prints this
weekend. One canister holds one pill type. The six-canister product is six copies
of the winning module, so the module is designed to be duplicated.

Gaps and guesses are recorded in [ASSUMPTIONS.md](ASSUMPTIONS.md). Nothing here
depends on the jam videos: none were available (see ASSUMPTIONS A1).

## 1. Pill set

The team tests with Nature Made iron tablets. Three representative pills cover the
rest of the provisional envelope (27 × 12 × 12 mm max, from the research doc).
Dimensions are nominal; each trial draws every dimension uniformly from the
tolerance band.

| ID | Pill | Shape | Nominal size (mm) | Tolerance | Mass |
| --- | --- | --- | --- | --- | --- |
| `iron` | Nature Made Iron 65 mg (team test pill) | round biconvex tablet | Ø 9.5, 5.0 thick | ±0.15 | 0.40 g |
| `small` | small round tablet (81 mg aspirin class) | round biconvex tablet | Ø 6.0, 2.8 thick | ±0.10 | 0.10 g |
| `caplet` | large oblong caplet (multivitamin class) | capsule-ended oblong | 19.0 × 8.5 × 6.5 | ±0.20 | 1.20 g |
| `cap0` | size-0 hard capsule | cylinder, hemispherical ends | 21.7 long, Ø 7.65 | ±0.30 L, ±0.08 Ø | 0.50 g |

The `iron` dimensions are an estimate and must be measured with calipers before
printing (ASSUMPTIONS A2). Every variant reads pill sizes from one file
(`sim/pills.py`), so a measured value regenerates the CAD and reruns the sim.

## 2. Failure modes found in the current design

Source: `cad/onshape/Pill_Dispenser_Clip_On_Canister_67p5mm.step` (synced from
Onshape on 2026-11-09). Measured from the STEP geometry:

| # | Location | Geometry | Expected failure |
| --- | --- | --- | --- |
| F1 | Canister bottom rim ↔ rotor top | 2.9 mm vertical gap, square edge | Thin tablets or tablet edges enter the gap and are pinched as the rotor turns (shear jam). The team flagged this in the P3 shop questions ("plate-to-canister gap must stay small so pills don't wedge"). |
| F2 | Rotor pockets | 3 slots, 11.5 × 26.6 mm, 6.0 mm deep, all pill types | One slot holds 2–6 small or iron tablets (doubles). Caplets and capsules can sit diagonally or half in. |
| F3 | Pocket depth vs pill height | 6 mm deep, pills up to 7.7 mm tall | Pills taller than the pocket stand proud; the brush or canister rim catches them (jam), or they are dragged to the drop hole on top of another pill (double). |
| F4 | Brush | 50 mm row of bristles hanging to 0.08 mm above the rotor | Bristles push pills sideways into the F1 gap; flexible bristles let a second pill ride through. |
| F5 | Rotor ↔ stationary floor | 0.35 mm gap | Below FDM tolerance (≈0.3 mm per mating surface); the printed rotor drags or binds, so the jam is in the drive, not the pill path. |
| F6 | Floor hole ↔ chute | 11.5 × 27 mm slot over a 14 × 29 mm chute | Long pills falling end-first can bridge or tumble at the slot edge. |

The team describes the jams as "in several places, not consistent". With F1–F4
the jam location should depend on the random pile, which matches that description.

## 3. Candidate mechanisms

All variants share the pill set, motor (Pololu #5229, 1000:1 HPCB 12 V, ~35 rpm
unloaded), FDM rules (walls ≥ 1.2 mm, ≥ 0.3 mm clearance per sliding pair,
support-free orientation) and sensing (IR beam-break in the chute, load cell
under the cup).

| ID | Mechanism | What changes from the current design |
| --- | --- | --- |
| **V0** | Current team CAD, unchanged | Baseline for the sim check (section 5). |
| **V1** | Minimal fix of the current design | Keep the vertical-axis rotor and canister. One pocket per pill type, sized for exactly one pill (depth ≈ pill thickness, length < 2 pill widths). Canister rim lowered to 0.5 mm above the rotor with a 45° lead-in. A rigid stripper blade replaces the brush. Running clearances raised to FDM values. |
| **V2** | Horizontal-axis pocket drum | A drum turning on a horizontal shaft under a 50° funnel hopper. One pill-sized pocket on the drum rim fills at the top, and a stripper lip wipes extras back into the hopper. The pocket turns pill-down and drops it into the chute. Gravity only ever pulls pills out of the pinch zone. |
| **V3** | Reciprocating shuttle (scotch-yoke slide) | The motor drives a pin in a slotted slide. The slide carries one pill-sized hole from under the hopper (fill) to over the chute (drop). The hopper wall acts as the stripper. Pills are sheared only along a straight, chamfered edge. |
| **V4** | Inclined rotating disc (seed-singulator style), if time allows | A disc tilted 45° with rim pockets lifts one pill per pocket out of a pool and drops it through a hole at the top. |

Pockets are pill-specific. Each variant gets an interchangeable insert (V1, V3)
or drum (V2), generated from the pill dimensions. This mirrors the LiviPod
approach the team noted in its research. No single fixed pocket can meter a 6 mm
tablet and a 21.7 mm capsule one at a time.

## 4. Verification

### 4.1 CAD (success condition 1)
- Every variant is a CadQuery script parameterised by pill and clearance, and
  exports STEP and STL per part.
- An automated check (`cad/check_printability.py`) reports minimum wall thickness
  (ray-cast), clearances between mating parts, and overhangs greater than 45°
  without support in the print orientation. A build fails when any rule fails.

### 4.2 Physics simulation (success condition 2)
- **Engine:** MuJoCo 3. PyBullet has no Python 3.13 wheel on this machine.
- **Geometry:** each part's exported STL goes through an exact convex
  decomposition (`sim/convexify.py`). It slices the mesh into cells with an
  adaptive octree and convex-hulls each piece. Cells split until the hull adds
  less than 0.05 mm of material, so modelled gaps match the CAD to about 0.05 mm.
  The original team STEP goes through the same path.
- **Pills:** convex meshes (biconvex tablet, rounded caplet, capsule) with mass
  and inertia from the dimensions.
- **Drive:** the motor is modelled with its speed–torque line (stall torque, no-load
  speed) at 12 V. The sim spins it exactly as the firmware will (same cycle angle,
  speed and dwell), using constants shared with the firmware.
- **Trial:** randomise pill dimensions within tolerance, friction (μ 0.2–0.6 for
  pill–PLA and pill–pill), restitution, fill count (3–25 pills) and start poses
  (dropped in at random). Then run **3 consecutive dispense cycles**.
- **Per-cycle outcome:** `ok` (exactly one pill crosses the chute sensor plane),
  `double` (2 or more), `miss` (0 with pills still in the hopper), or `jam` (the
  rotor stalls for more than 0.3 s, or a pill is held between moving and fixed
  parts with contact force over the threshold). The jam site is recorded as the
  pair of geoms in contact at the stall plus the pill position.
- **Scale:** at least 200 trials per pill type per variant. A variant passes only
  with 0 jams, 0 doubles and 0 misses in every cycle. When a variant fails, the
  geometry changes and every trial reruns. The test is never loosened.

### 4.3 Sim credibility check (success condition 4)
- Run V0 (team STEP) in the same harness and the same trials.
- The expected match to reality: V0 jams, at more than one site, at varying
  locations from trial to trial. The sites should be F1/F3/F4 for tablets and F2
  doubles for small pills.
- Without videos, the evidence is the team's own description and the P3 note
  about the plate gap. If V0 ran clean, the sim would be suspect and I would fix
  it before trusting any other result.

### 4.4 Proof you can see (success condition 3)
- A recorder logs every body pose from real trials of the best variant to JSON.
- A three.js viewer replays those logs with the variant's real STL meshes.
  Selectable trials include an original-design jam for comparison.
- A comparison table of jam, double and miss rates for each variant and pill,
  with jam-site counts.

### 4.5 Electronics (success condition 5)
- Wiring diagram (SVG) and pin map, resolving the GPIO13 and GPIO32 conflicts
  between `include/pins.h` and the TFT sketch.
- Power budget per rail (12 V motor, 5 V, 3.3 V) and a build order.
- Integrated PlatformIO firmware: a state machine with scheduling (RTC), menu
  (potentiometer, button, TFT), encoder-closed-loop indexing, beam-break and
  load-cell confirmation, and jam detection with a reverse-and-retry cycle.
  Cycle timing comes from the same mechanism constants the sim uses.
- Builds pass in CI. Logic is verified with host-side native tests. Wokwi is not
  reachable from this machine; see ASSUMPTIONS.

### 4.6 BUILD.md (success condition 6)
- Parts list with sources, print settings, fastener-level assembly, and a
  physical test procedure mirroring the sim: N cycles per pill, counted outcomes,
  and a pass threshold.

## 5. Work split

| Stream | Owner | Depends on |
| --- | --- | --- |
| Sim harness, convexifier, pill models, V0 import | lead | — |
| V1, V2, V3 (V4) CAD + sim iteration | one sub-agent each | harness |
| Electronics: wiring, firmware, native tests | sub-agent | mechanism timing constants (shared header) |
| Viewer, comparison table, BUILD.md, final report | lead | results |
