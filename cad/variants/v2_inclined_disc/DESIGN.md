# V2: inclined pocket disc

`build.py` regenerates every part from `sim/pills.py`:

    python cad/variants/v2_inclined_disc/build.py            # all four pill kits + common parts
    python cad/check_printability.py cad/variants/v2_inclined_disc/*/manifest.json
    python -m sim.campaign v2_inclined_disc --trials 200 --resume

## Mechanism

A disc tilted 50° from horizontal turns over a fixed back plate, inside a fixed hopper
bore. Pockets in the disc rim hold exactly one pill; the hopper wall closes each
pocket's outer side and the back plate is its floor. Pills pool at the low side of the
hopper, drop into a pocket as it passes, ride up, and fall through a hole in the back
plate at the top (12 o'clock) while the disc is stopped. A 50 mm duct behind the plate
carries the pill past the motor to the cup; the beam-break sits 8 mm into the duct.

Why it resists the original design's failures:

- The only fixed surface a pocket ever passes is the concentric hopper wall, which
  never crosses the pocket. There is no stripping edge to shear a half-seated pill.
- Unseated pills slide back to the pool by gravity: tan 50° = 1.19, twice the worst
  friction coefficient tested (0.6).
- The exit is at the top, 180° from the pool, so the pile can't reach it.
- The firmware indexes one pocket pitch at a time and stops at the first pill the
  beam-break sees, so an empty pocket costs time, not a miss.

## Pocket per pill (from `pocket_params`)

| Pill | Pocket | Size (mm) | Depth | Pockets | Index |
| --- | --- | --- | --- | --- | --- |
| iron Ø9.5 × 5.0 | standing slot, open to the wall, inner wall chamfered 2.7 | 7.45 radial × 11.64 along the rim | 4.55 | 8 | 45° |
| small Ø6.0 × 2.8 | flat notch, open to the wall | Ø6.8 | 2.4 | 8 | 45° |
| caplet 19 × 8.5 × 6.5 | flat notch, 2.1 lead-in chamfer | 21.0 × 11.7 | 6.0 | 4 | 90° |
| size-0 capsule 21.7 × Ø7.65 | flat notch, 2.5 lead-in chamfer | 22.7 × 8.4 | 7.27 | 4 | 90° |

Thick tablets (thickness ≥ half the diameter, i.e. iron) settle standing on edge against
the hopper wall, so their pocket is built for that pose: one standing tablet fits
radially (two would need 9.7 mm), and the slot is longer than the tablet's tilted
diagonal so it cannot wedge between the slot's end walls.

## Hopper

- 74 mm tall bore, Ø60.8 at the disc. Upper half closed by the cover; the lower half
  is the pour opening.
- Exit relief: a 4 mm deep groove over the exit, full height, with 20° ramps. A pill
  at the exit has no wall to lean on.
- Pool side (lower half), fading smoothly to nothing at the sides:
  - 0–8 mm above the disc: wall leans outward 10°;
  - 12–45 mm: whole shell leans inward 15°, so the bore only widens toward the pool;
  - top 4 mm: lip leaning inward 40° (near vertical once the assembly is tilted).

## Parts and print orientation

All parts print without supports (`check_printability.py`: walls ≥ 1.2 mm, sliding
clearances 0.4 mm, unsupported overhang ≤ 4 mm²). Settings are in `BUILD.md`.

| Part | Per pill | On the bed |
| --- | --- | --- |
| `disc` | yes | back face down |
| `backplate` (with duct, motor socket, stand tabs) | yes | front face down |
| `hopper` | yes | flange down |
| `cover`, `clamp`, `side_left`, `side_right`, `base`, `cup` | no (`common/`) | flat |

## Revision history

Every change answers a failure seen in the simulator. Counts are dispense cycles.

| Rev | Change | Result that drove the next change |
| --- | --- | --- |
| 1 | Exit at 3 o'clock, round/oblong notches at pill size + 0.35 mm | Small tablets: pile reached the exit, 2 doubles in 3 cycles |
| 2 | Exit moved to 12 o'clock with a 50 mm duct; notches widened to the tilted pill diagonal | Iron: tablet hung on edge between notch end and wall at the exit (jam at 103°) |
| 3 | Hopper bore relieved over the exit | Capsules shoved along the wall instead of seating (3 jams in 3 trials) |
| 4 | 45° lead-in chamfers on long-pill notches | First 25 campaign trials, iron: 8 doubles (two tablets standing side by side in the widened notch) |
| 5 | Round notches back to Ø + 0.7 mm | 25 iron trials: 1 jam (tilted tablet wedged in the notch at the exit), 1 miss |
| 6 | Iron in an edge slot (5.85 mm wide); relief made full height, 4 mm deep | 34 misses in 75 cycles: the tablet self-locks in the narrow slot and never drops |
| 7 | Closed round pockets 1.2 mm inside the rim | 75 misses in 75: tablets stand against the wall and the pocket passes under them |
| 8 | Standing slot open to the wall (7.45 × 11.64 mm); flat notch again for thin tablets | 100 iron trials: 0 jams, 0 doubles, 2 misses (tablets arched 19 mm above the disc), 2 tablets spilled over the low front lip |
| 9 | Hopper 70 mm; inner lining leaning 15° over the pool | Lining left a shelf at the rim; a tablet slid off it |
| 10 | Lining flared back to the bore; rim chamfer | The flare made a waist: all 20 tablets arched above it |
| 11 | Whole pool-side shell leans 15° (no lining, no waist) | Lone flat tablet held up by wall friction (1 miss in 4 problem seeds) |
| 12 | Bottom 8 mm of the pool-side wall flared outward 10° | 125 iron trials: 0 jams, 0 doubles, 4 misses (flat tablet bridging the slot), 4 tablets lost when poured onto the rim |
| 13 | Slot inner wall chamfered 2.7 mm; 4 mm inward lip at the top of the pool side; rim chamfer removed | See `results/COMPARISON.md` |

## Known limits

- Pill-specific: each pill needs its own disc, back plate and hopper (the three are a
  matched set because the back plate position depends on disc thickness).
- The iron dimensions are an estimate (ASSUMPTIONS A2). The standing-slot rule keys on
  thickness ÷ diameter ≥ 0.5; iron is 0.53, so a measured tablet under 0.5 would switch
  to a flat notch. Re-run the campaign after measuring.
- The pour opening is the lower half of a Ø60 bore with a lip: pour slowly or use a
  paper funnel.
