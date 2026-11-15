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

| Pill | Pocket | Size at the face (mm) | Depth | Pockets | Index |
| --- | --- | --- | --- | --- | --- |
| iron Ø9.5 × 5.0 | flat round notch, open to the wall | Ø10.35 | 4.55 | 8 | 45° |
| small Ø6.0 × 2.8 | flat round pocket, closed, 1.2 mm inside the rim; rib liner on the hopper wall | Ø6.8 | 2.4 | 8 | 45° |
| caplet 19 × 8.5 × 6.5 (**experimental**) | rim-wise notch, half-depth; hub 1 mm inboard | 19.9 × 11.7 | 3.47 | 4 | 90° at 5 rpm |
| size-0 capsule 21.7 × Ø7.65 (**experimental**) | rim-wise notch, half-depth; hub 1 mm inboard | 22.7 × 8.4 | 4.16 | 4 | 90° at 5 rpm |

**Status.** The iron and small-tablet kits passed the full campaign (200 of 200 trials
each) and are the ones to build. The caplet and capsule kits have not passed it; their
row above is the latest revision under test.

Every tablet pocket holds its pill lying flat, with 0.35 mm clearance per side, and is
slightly shallower than the pill is thick, so a second pill cannot nest on top. Every pocket wall
is undercut 12° below a 1.2 mm straight land (pocket wider at the back plate than at the
face): at the exit the pill is pressed against the pocket's inner wall harder than it is
pulled out of the back, and the undercut lets it slide out. Tablet discs index at 25 rpm.

**Thin tablets (small).** A tablet thinner than half the notch width can stand on edge
beside a second one in an open notch, and both are carried (`pair_prone` in `build.py`
decides this from the pill's dimensions; iron is thick enough that a pair does not fit).
For those pills the pocket is a closed circle, and the hopper wall carries a rib liner:
its 50° underside starts 0.3 mm above the disc at the wall, and it then runs parallel to
the wall, 2.3 mm inside it, to the top. A tablet lying flat on the disc is stopped by the
rib exactly over the pocket and drops in; nothing can stand against the wall; in a closed
circle a second standing tablet has no room.

## Hopper

- 74 mm tall bore, Ø60.8 at the disc. The cover closes the part above local y = +12;
  the rest is the pour opening (about 31 mm deep).
- Exit relief: a 4 mm deep groove over the exit, full height, with 20° ramps. A pill
  at the exit has no wall to lean on.
- Pool side (lower half), fading smoothly to nothing at the sides:
  - 12–45 mm above the disc: whole shell leans inward 15°, so the bore only widens toward
    the pool;
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
| 13 | Slot inner wall chamfered 2.7 mm; inward lip at the top of the pool side; rim chamfer removed | 10 iron trials: 2 jams, 2 misses (a second tablet sat half-in on the chamfer and was pinched). Lip kept (4 mm), chamfer reverted |
| 14 | Chamfer and base flare removed; cover edge moved to y = +12 (wider pour opening) | Last-tablet test (3 loaded): 7 of 16 trials missed, a lone tablet lies flat and bridges the slot |
| 15 | Iron in a flat round notch | 13 of 16 last-tablet trials failed: tilted tablets wedge across the notch and ride past the exit |
| 16 | Standing slot again; disc rises as a 60° cone inboard of the slots; iron at 10 rpm | Last-tablet 16/16 clean, but 1 double in 10 random trials (second tablet cradled in the V above a seated one) |
| 17 | Cone on a 12 mm straight hub | Doubles in 10 of 16 trials at 14 tablets (the channel conveyed stacked tablets) |
| 18 | 60° ramp ring only 3 mm high, flat face above | 14 loaded: 16/16 clean. 3 loaded: 13/16 (last tablet seated at the exit but not dropping) |
| 19 | Every pocket wall undercut 12° below a 1.2 mm land; exit hole enlarged to match | 3 loaded: 15/16 (standing tablet carried past the slot at 10 rpm) |
| 20 | Iron at 6 rpm; ramp ring 4.5 mm | 3 loaded: 24/24; 14 loaded: 16/16; but 1 jam in 40 campaign trials: a tablet parked half-way into the exit hole |
| — | **Simulator fix.** That tablet was held by a collision piece protruding 1.45 mm into the pocket. `sim/convexify.py` bounded only the average overshoot of each convex piece; it now bounds the maximum (≤ 0.15 mm near pills). All earlier campaign results, for every variant, were discarded. Rows 5–20 above were measured on the old collision shapes | Rev 20 re-tested: a lone flat tablet bridged from the ramp ring to the wall (1 miss in 10 trials) |
| 21 | Flat round notch for every tablet; standing slot, ramp ring and slow speed retired | **Iron: 200/200 trials pass (600 dispenses).** Small: 1 double in 10 trials (two tablets standing side by side in one notch) |
| 22 | Rib ring above the disc for thin tablets | 19 loaded: 16/16. 3 loaded: 2/24 (the rib stopped lone tablets short of the open notch) |
| 23 | Closed circular pocket for thin tablets, no rib | Mostly misses: tablets rest against the wall, beyond the pocket |
| 24 | Closed pocket placed where a rib ring stops a flat tablet | Pills sat on the rib's short top face; with a long taper instead, a tablet stuck to it (7/8) |
| 25 | Rib as a straight liner parallel to the wall | Small: 3 loaded 24/24, 19 loaded 16/16. Full campaign: see `results/COMPARISON.md` |

### Long pills (revisions 26–40, not yet passing)

Caplets and capsules fail in ways tablets do not. What was tried, on the corrected
simulator, with small targeted tests (24 trials at 4 loaded and at 10 loaded):

| Rev | Change | Result |
| --- | --- | --- |
| 25/29 | Full-depth notch sized to the tilted pill, lead-in chamfer all round | Caplets: 1 slow pickup in 90 campaign trials; with 16 steps allowed, 1 double in 100 (a second caplet's tail sat in the chamfered front of the pocket) |
| 26–28 | 60° cone inboard of the notches to turn pills along the rim | Doubles (second pill cradled in the V beside a seated one) and exit jams; 21/24 at best |
| 30 | No lead-in chamfer | 1 double and 1 jam in 20 trials |
| 31–32 | Snug notch (pill + 0.35 mm per side) | No doubles, but a caplet standing on end locked diagonally in the 9.4 mm width (jams in 4–7 of 24) |
| 33 | Snug length, width clear of the section diagonal | No jams; 2 doubles in 24 (two caplets end-down in one pocket) |
| 34 | Half-depth pockets (0.55 × thickness) | No doubles or jams; 2 low-fill misses in 24 |
| 35 | Hub sized from the pill's length | A caplet wedged as a strut between hub and wall |
| 36 | Radial pockets | 7 of 24 low-fill trials clean |
| 37–38 | No trailing chamfer; 5 rpm (a caplet lying ready on the track was over a passing pocket for only ~0.013 s at 25 rpm) | Caplets: 24/24 at 4 loaded, 23/24 at 10 loaded (the one failure was a test-setup error, since fixed). Capsules: 23/24 at 4 loaded (two capsules locking each other on the open face) |
| 39 | Speed-bump ribs on the face | Capsule lock unchanged |
| 40 | Straight hub 1 mm inboard of the pockets, 6 mm tall: the pool is a channel ~1 mm wider than the pocket | Capsules 24/24 at 4 loaded. Remaining targeted tests and the 200-trial campaign not run |

## Known limits

- Pill-specific: each pill needs its own disc, back plate and hopper (the three are a
  matched set because the back plate position depends on disc thickness).
- The iron dimensions are an estimate (ASSUMPTIONS A2). Whether a tablet gets the open
  notch or the closed pocket with rib depends on its thickness-to-diameter ratio; re-run
  `build.py` and the campaign after measuring.
- The hopper's lowest wall line is a 40° slope in the assembled position (the disc is at
  50°). That is 9° steeper than the worst friction tested; a stickier tablet would hang
  on the wall.
- The pour opening is the lower half of a Ø60 bore with a lip: pour slowly or use a
  paper funnel.
