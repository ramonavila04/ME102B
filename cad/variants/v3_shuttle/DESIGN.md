# V3: reciprocating shuttle (scotch-yoke slide)

**Result: does not pass.** The final revision (r4) jams at the throat edges in roughly half of
all trials. It also misses often, because the pocket fails to fill within six strokes. The
200-trial table is in "Final campaign" below.

The cause is geometric, explained in "Why a rigid-edge shuttle cannot reach zero here":
- These domed tablets can stand on edge in any seat or tube with FDM clearance.
- A pill standing or tilted half out of the pocket is held face-to-face between the moving pocket
  wall and the fixed stripping edge. No rigid edge profile tried here lifts it out.

CAD: `build.py` (CadQuery, parametric per pill). Sim spec: `sim/variants/v3_shuttle.py`.

## Mechanism (r4, final)

Frame: the slide top is at z = 0. The underside of the hopper's cover plate is at z = +0.4, the
running gap. The pocket floor (the fixed floor plate) is at z = −D. The slide is drawn at
mid-stroke, and its x = R·sin θ. Fill is at θ = −90° (x = −R); drop is at θ = +90° (x = +R).

- **Hopper:**
  - Rectangular funnel. The ±x walls are 60° from horizontal and the ±y walls 70°, so the corner
    valleys are about 56°.
  - A 20 mm vertical extension sits on top.
  - Printed in one piece with the cover plate, which closes the slide channel over the whole stroke.
- **Throat:**
  - The opening in the cover plate at x = −R. It exposes only the pocket's seat: 0.8 mm beyond its
    trailing edge and 3 mm beyond its leading edge.
  - Its edges are the bottom of the 60° funnel faces. The cover plate's underside meets each face
    in a 60° knife edge, 0.4 mm above the slide. Above that edge the face rises away from the slide
    (relief): there is no converging chamfer.
- **Pocket** (through the slide, closed underneath by the floor plate):
  - A seat one pill wide: the pill outline plus 0.4 mm per side, with a vertical leading (+x) wall.
  - Its trailing half is squared off. From there a 20° ramp rises from the floor to the slide top.
    The ramp and a vertical pill face meet at 70°, more than the 62° wedge that self-locks at
    μ = 0.6, so a pill squeezed between them is pushed up.
  - Depth D = the largest pill's thickness + 0.35 mm. For the caplet it is the caplet's width
    + 0.35 mm, so a caplet on its side also sits below the slide top.
  - A second pill can't ride along: 2·t_min is greater than D + 0.4 for every pill.
- **Fill:** on the return stroke, the pills on the slide top are dragged against the entry wall. The
  seat arrives under that pile at the end of the stroke, the crank slows near θ = −90°, and the
  pocket dwells there.
- **Drop:** the floor hole at x = +R is the seat outline grown by 1.5 mm. The chute bore is the hole
  grown by a further 1 mm, so there is no ledge to catch a pill. The crank also dwells at θ = +90°.
- **Stroke spacing:** R is sized per pill so the pocket mouth (seat + ramp) is covered by the cover
  plate at least 3 mm before the seat reaches the drop hole. The pocket is never open to throat and
  chute at once.
- **Guide:** the slide runs in a channel with 0.4 mm clearance at the top (cover plate), bottom
  (floor) and sides (rails).
- **Drive:**
  - Pololu 1000:1 micro metal gearmotor (3 mm D-shaft), shaft vertical, under the base at x_crank.
  - It turns a crank disc with a Ø5 mm pin at radius R, running in a yoke slot across the slide
    (0.35 mm clearance per side).
  - Sim drive: `index_deg` 360 (one stroke out and back), 30 rpm, `start_deg` −90, `max_steps` 6
    (the firmware indexes again if the chute beam saw nothing).

### Parameters per pill (mm; generated, see each `<pill>/manifest.json`)

| pill | seat (x × y) | depth D | ramp length | slide t | crank R | throat x-range | throat y | slide width | slide mass |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| iron | Ø10.45 | 5.50 | 15.11 | 5.10 | 22 | −28.03 … −13.77 | 16.45 | 59.7 | 28.5 g |
| small | Ø6.90 | 3.25 | 8.93 | 2.85 | 16 | −20.25 … −9.55 | 12.90 | 47.7 | 10.4 g |
| caplet | 9.50 × 20.0 slot | 9.05 | 24.86 | 8.65 | 26 | −31.55 … −18.25 | 22.0 | 67.7 | 57.4 g |
| cap0 | 8.53 × 22.8 slot | 8.08 | 22.20 | 7.68 | 24 | −29.07 … −16.73 | 24.8 | 63.7 | 44.6 g |

## Printability (`python cad/check_printability.py cad/variants/v3_shuttle/*/manifest.json`)

PASS for all four pills:
- Every part is watertight.
- 1st-percentile wall thickness is at least 1.30 mm (the cap0 slide is the thinnest, at its
  feathered ramp tip); all other parts are at least 1.78 mm.
- Overhang is no more than 2.2 mm² on any part.
- Clearances: slide–base 0.40, slide–hopper 0.40, pin–yoke 0.35, crank–base 0.60,
  crank–mount 1.50, crank–clamp 5.0 mm.

| part | print orientation | notes |
| --- | --- | --- |
| slide | flat, underside on the bed | the ramp ends in a feathered edge at the slide top; 0.12 mm layers there help |
| guide_base | floor underside on the bed | rails print as walls |
| hopper | cover-plate underside on the bed | the funnel walls lean 30° (x) and 20° (y) from vertical, so no support is needed |
| chute | flange on the bed (rotated 180° about x) | |
| crank | disc on the bed, pin and hub up | D bore Ø3.1 with a flat at 2.55 mm; check the press fit on the shaft |
| motor_mount | back wall (the −y face) on the bed (rotated 90° about x) | horizontal holes are 55° teardrops |
| motor_clamp | flat | |

PLA, 0.2 mm layers, 3 perimeters, 30 % infill.

## Fasteners and assembly

1. Press the crank onto the gearmotor D-shaft. The shaft tip should end 0.3 mm below the top of
   the hub.
2. Slide the gearbox (12 × 10 mm) into the motor mount's U slot from +y. Close it with the motor
   clamp and **2× M2 × 8** screws, which self-tap into the 1.7 mm pilots.
3. Screw the motor mount to the underside of the base rails with 2× M3 × 10 (self-tap into the
   2.5 mm pilots).
4. Screw the chute under the drop hole with 2× M3 × 8.
5. Drop the slide into the channel. The crank pin must enter the yoke slot.
6. Fit the hopper / cover plate on the rails with 6× M3 × 10.
7. The gearbox length (15 mm) and shaft length (10 mm) are assumed. **MEASURE** them before
   printing the mount; `SHAFT_LEN` and `GEARBOX_*` are in `build.py`.

## Revision history (dev runs: 10 trials per pill, seeds 1000–1009, 1 worker)

| rev | change | driven by | sim result |
| --- | --- | --- | --- |
| r0 | First geometry. One pill-sized pocket with a 45° trailing chamfer. Throat at the funnel knife edges. R = 14. | — | Not evaluable at first: the engine's old slide drive let the slide run past the dead centres. Reported, and fixed in the engine as a kinematic yoke. Rerun with 3 iron seeds: misses, a jam at the exit edge, and a drive overload. |
| r1 | 20° trailing ramp from the floor to the slide top, replacing the 45° chamfer. Throat exposes seat + ramp. R sized per pill. | A tablet standing on edge in the pocket was held between the knife edge (on its flat face, horizontal normal) and the 45° chamfer: a 45° wedge, under the 62° lock limit. | Iron dev run: 19 misses, 5 exit-edge jams. **Invalid:** the convex decomposition had closed the drop hole (see "Simulator issues"). |
| (fix) | Spec: collision crops tiled at 6 mm. | Rays cast against the convex pieces showed a single hull filling the floor's drop hole. | Holes verified open. |
| r2 | Throat exposes only the seat; at fill the ramp lies under the entry-side cover. | Pills parked on the 20° ramp (they don't slide on it at μ = 0.2–0.6) and never reached the seat. | Pockets now fill: iron 1000 gave ok, ok. Seed 1001 jammed, with a tablet lying flat on the lower ramp: it slipped under the knife edge and was squeezed between the rising ramp and the cover. |
| r3 | Ramp starts on a vertical step at z = 0.4 − t_min/2 + 0.3, so a pill lying on the ramp meets the knife edge below its mid-height. | r2 seed 1001. | Worse. Jam trials: iron 9/10, small 5/10, caplet 7/10, cap0 6/10. A standing tablet is held face-to-face between the knife edge and the step corner, with both normals on one line (zero torque). Seated tablets that rock about 12° touch the knife edge and stall against the floor. |
| r4 | Back to the r2 geometry, with `max_steps` raised from 3 to 6. | r3 was worse than r2. In r2 most failures were misses. | Iron: 1/10 passed (9 ok, 7 miss, 5 jam). Cap0 on r4: 0/10 passed (2 ok, 12 miss, 6 jam). Small and caplet were run only on r2 (identical geometry, 3 strokes): small 2/10 passed (10 ok, 7 miss, 5 jam); caplet 0/10 (4 ok, 10 miss, 6 jam: 3 exit edge, 3 entry edge). |

## Final campaign (r4, 200 trials × 4 pills, `--workers 3` under the campaign lock)

See `results/v3_shuttle/*.json`. The summary is added below once the campaign has finished.

FINAL_TABLE_PLACEHOLDER

## Why a rigid-edge shuttle cannot reach zero here

1. **Tablets stand on edge.**
   - With FDM clearance (0.3–0.4 mm per side), a domed tablet can turn freely from flat to
     standing in the seat. Rotated about a horizontal axis, its plan outline never exceeds 10.01 mm
     (iron) or 6.32 mm (small). Preventing the turn would need a seat or tube within 0.17 mm
     (iron) or 0.11 mm (small) per side.
   - A standing iron tablet is 9.65 mm tall. Two stacked iron tablets are 9.7–10.3 mm, so the
     depth cannot hold a standing tablet below the slide while still rejecting a stacked pair.
     Caplets and capsules on end are worse.
2. **The edge meets a flat face.** A standing or tilted pill half out of the pocket reaches the
   stripping edge with its flat face toward it. The edge pushes along the face normal, horizontal
   or downward. The only escape is to slide up between the two faces, which friction forbids when
   the faces are held from opposite sides.
3. **Every trailing-wall profile still pinches something:**
   - vertical wall or 45° chamfer: wedge below 62° (r0);
   - shallow ramp from the floor: lifts a standing tablet but gives a flat-on-ramp vise (r2/r4);
   - step + ramp: face-to-face vise across a standing tablet (r3).

   A compliant stripper (brush) or gravity stripping on a tilted pocket would avoid this, but both
   lie outside this variant's brief.

## Simulator issues found (reported; the engine was not edited)

1. **Slide drive (fixed upstream in "Model the scotch-yoke drive kinematically").** The old drive
   clamped q/R to ±1 and took the crank angle by asin. At the dead centres it pushed with up to
   about 1430 N with a sign from cos(±90°). An empty machine overran to +25…+34 mm with R = 14 and
   tripped the jam rules on every stroke.
2. **Convex decomposition can close holes** (`sim/convexify.py`). A piece is accepted when
   (hull volume − volume) / hull area < tol. For a large thin plate with one hole that ratio is
   small, so one hull covers the hole. The cropped 75 × 72 × 3 mm floor with a Ø13.45 mm drop
   hole became one piece. After tiling at 12 mm the hull still bulged several mm into the hole's
   round edge.
   - Workaround here: 6 mm crop tiles, checked by casting vertical rays against the pieces and the
     CAD.
   - Other variants with holes in large plates may be affected. A per-piece maximum-deviation test,
     for example hull vertices against the solid's surface distance, would be safer than the area
     mean.
