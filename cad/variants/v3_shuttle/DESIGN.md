# V3: reciprocating shuttle (scotch-yoke slide)

**Status: blocked by a simulator issue in the slide/crank drive model (see "Simulator issue").**
The CAD passes `cad/check_printability.py` for all four pills. The sim cannot judge the
mechanism yet: with the engine as it is, an empty machine (no pills) fails its first stroke.
No 200-trial campaign was run, because its results would mean nothing.

## Mechanism

- **Hopper**: rectangular funnel. Its ±x walls are 60° from horizontal and its ±y walls 70°,
  so the corner valleys are about 56°, steep enough for pills to slide at μ = 0.6. A 20 mm
  vertical extension sits on top. The hopper is one print with the **cover plate**, whose
  underside runs 0.4 mm above the slide top over the whole stroke.
- **Throat**: a rectangular opening in the cover plate at x = −R (the fill position). It is
  exactly where the funnel walls meet the cover underside, so each throat edge is a 60°
  knife edge whose face rises away from the slide. A pill that sticks out of the pocket
  meets a surface facing up and toward the hopper, which pushes it back up into the hopper.
  It never meets a converging wedge.
- **Slide**: one pocket through the slide, closed underneath by the floor plate.
  - The pocket is the pill's maximum size plus 0.4 mm per side.
  - Its depth D puts the largest pill 0.35 mm below the slide top; for caplets, a caplet
    lying on its side also fits.
  - A second pill can't ride along: 2·t_min is greater than D + 0.4 for every pill.
  - The trailing (−x) half of the pocket rim has a 45° chamfer, deeper than any second pill
    can dip into the pocket. The chamfer and the 60° throat face form a 75° V that opens
    upward. That is more than 2·atan(0.6) = 62°, so a pill squeezed between them is pushed
    up and out instead of wedging.
- **Floor plate / guide base**: the floor and two side rails. The slide runs with 0.4 mm
  clearance at the top, bottom and sides. The drop hole at x = +R is the pocket outline
  grown 1.5 mm all round, and the chute bore is grown a further 1.0 mm, so there is no
  ledge for a pill to catch on.
- **Stroke spacing**: the pocket can never be open to the throat and the drop hole at the
  same time. The margin is at least 3 mm for every pill.
- **Drive**:
  - A Pololu 1000:1 micro metal gearmotor with its shaft vertical, under the base at
    x = −52 mm.
  - It drives a crank disc with a Ø5 mm pin at R = 14 mm. The pin runs in a yoke slot
    across the slide, with 0.35 mm clearance per side.
  - x = R·sin θ, so one revolution from θ = −90° is fill, then drop (θ = +90°), then back
    to fill.
  - Sim drive: `index_deg` 360, 30 rpm, `start_deg` −90, `max_steps` 3.

## Parameters per pill (mm)

| pill | pocket (x × y) | depth D | slide t | trailing chamfer | throat x-range | throat y | drop hole | slide mass |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| iron | Ø10.45 | 5.50 | 5.10 | 1.25 | −21.28 … −7.98 | 16.45 | Ø13.45 | 25.0 g |
| small | Ø6.90 | 3.25 | 2.85 | 1.20 | −19.45 … −9.75 | 12.90 | Ø9.90 | 14.1 g |
| caplet | 9.50 × 20.0 slot | 9.05 | 8.65 | 3.35 | −22.90 … −8.45 | 22.0 | 12.5 × 23.0 | 41.3 g |
| cap0 | 8.53 × 22.8 slot | 8.08 | 7.68 | 2.50 | −21.57 … −8.94 | 24.8 | 11.53 × 25.8 | 36.7 g |

Every pill uses R = 14 mm, a 0.4 mm running gap, a 44 mm wide slide, a 3 mm floor, a 3 mm
cover and 2 mm hopper walls.

## Printability (`python cad/check_printability.py cad/variants/v3_shuttle/*/manifest.json`)

PASS for all four pills:
- 1st-percentile wall thickness is at least 1.78 mm on every part. The hopper's 60° throat
  knife edges show up only in the minimum single-ray reading.
- Overhang is no more than 2.2 mm² on any part.
- Every part is watertight.
- Clearances: slide–base 0.40, slide–hopper 0.40, pin–yoke 0.35, crank–base 0.60,
  crank–mount 1.50 mm.

| part | print orientation | notes |
| --- | --- | --- |
| slide | flat, underside on the bed | 0.2 mm layers; the top face must be flat (ironing helps) |
| guide_base | floor underside on the bed | rails print as walls |
| hopper | cover-plate underside on the bed | the funnel walls lean 30° from vertical, so no support is needed |
| chute | flange on the bed (rotated 180° about x) | |
| crank | disc on the bed | D bore 3.1 mm with a 2.55 mm flat; check the press fit |
| motor_mount | back wall (the −y face) on the bed (rotated 90° about x) | horizontal holes are teardrops |
| motor_clamp | flat | |

PLA, 0.2 mm layers, 3 perimeters, 30 % infill.

## Fasteners and assembly

1. Press the crank onto the gearmotor D-shaft. The shaft tip should end 0.3 mm below the
   top of the hub.
2. Slide the gearbox into the motor mount's U slot from +y. Clamp it with the motor clamp
   and 2× M2 × 8 screws, which self-tap into the 1.7 mm pilots.
3. Screw the motor mount to the underside of the base rails with 2× M3 × 10 (holes at
   x = −76 and −28, y = ±25.9).
4. Screw the chute under the drop hole with 2× M3 × 8.
5. Drop the slide into the channel. The crank pin must enter the yoke slot.
6. Fit the hopper / cover plate on the rails with 6× M3 × 10 screws into the rails' 2.5 mm
   pilots.
7. The gearmotor's gearbox length and shaft length are assumed (15 mm and 10 mm).
   **MEASURE** them before printing the mount.

## Revision history

| rev | change | sim result |
| --- | --- | --- |
| r0 | First full geometry, as above | Not evaluable. With no pills, one empty stroke overshoots to +25…+34 mm (R = 14). The engine's jam rules fire at θ ≈ +90° on every stroke (see below). The first two iron trials jammed. |

## Simulator issue (not fixed: the engine was not edited)

The engine models the slide (scotch yoke) through the controller only (`Drive.crank_state` and
`Drive.control`). The yoke constraint x = R·sin θ, |x| ≤ R, is not enforced anywhere:

1. `crank_state` clips q/R to [−1, 1] and estimates θ from asin, choosing the branch nearest
   the reference. Past either dead centre (|q| > R) the measured angle sticks at ±90°, so the
   position loop cannot see the error.
2. At the dead centres `control` applies force = τ / (max(|cos θ|, 0.05)·R) · sign(cos θ). The
   sign comes from cos(±90°) ≈ ±6e−17, and the force reaches 1 N·m / (0.05·14 mm) ≈ 1430 N.
   So when the reference passes +90°, the controller keeps pushing the slide +x past +R
   instead of reversing it. A real crank pin reverses it geometrically.
3. Holding at the fill dead centre with a start angle after the ±2° jitter:

   | start angle | behaviour with no pills |
   | --- | --- |
   | below −90° | the slide creeps past −R (−14.58 mm after 1 s at −92°; trial iron/1 sat at −17.2 mm) with the torque saturated 100 % of the time |
   | −89° or −91° | the force chatters at about ±1100 N |
   | exactly −90° | holds still |

To reproduce with no pills (only the engine and this spec are used):
`python /tmp/claude-0/-home-user-me102b/b0848cd0-22fc-5180-a96c-adf726b7b474/scratchpad/stroke.py`

| start angle | hold | stroke travel | max lag | jam fires at |
| --- | --- | --- | --- | --- |
| −92° | −14.58 mm, saturated 100 % | −14.62 … +34.03 mm | 178° | 0.14 s (lag), 0.29 s (saturation) |
| −90° | −14.00 mm, 0 % saturated | −14.00 … +32.97 mm | 180° | 1.13 s (lag) |
| −88° | −15.43 mm, saturated 100 % | −15.46 … +24.79 mm | 180° | 0.12 s (lag) |

**Suggested fix (for the sim owner):** model the yoke kinematically instead of through the
controller:
- a crank body on a hinge (driven by the existing hinge PD and motor line);
- a yoke block on a y-slide inside the x-slide body;
- an `<equality connect>` between the crank pin site and the block.

The encoder then reads θ directly, and the pin carries the constraint force at the dead
centres.
