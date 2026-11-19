# V2 module for the V7 enclosure

The V2 inclined pocket disc, repackaged so six of them bolt onto the V7 pill dispenser
(`cad/onshape/V7_Pill_Dispenser_Heat_Inserts.step`) in place of its six vertical canister
modules. Each module drops its pills into the V7's central opening, so the V7 funnel and
weighing station are used unchanged.

![Six modules on the V7 enclosure](../../../docs/v7_module_assembly.png)

## What is kept from V2, and what is new

| | Status |
| --- | --- |
| Disc, pockets, hopper bore, cover, 50° tilt, 25 rpm indexing | Unchanged V2 parts. The iron and small-tablet kits passed 200/200 trials as a stand-alone V2. |
| Exit duct | New: 38 mm long (V2: 96 mm). The exit-relief section continues only 12 mm into it, then the duct narrows to the plain exit-hole section so the six ducts fit where they converge. |
| Drive | New, more compact: two R4-ZZ bearings 18 mm apart, a 1:1 pair of printed spur gears (module 1.5, 14 teeth), and the gearmotor on its own mount behind the gears, below the shaft. |
| Hopper flange and back plate | Trimmed to the module's 60° slice of the deck (1.7 mm³ of the iron hopper is removed; nothing pills touch). |
| Stand | New: a base plate that bolts to the V7 deck exactly where a V7 module does, and two cheeks. |

Because the duct changed, the pill path was re-tested in simulation as variant
`v2_v7_module` (`python -m sim.campaign v2_v7_module --pills iron small --trials 200`):

| Kit | Trials passed | Dispenses | Failures |
| --- | --- | --- | --- |
| iron | 200 / 200 | 600 ok | none |
| small | 200 / 200 | 600 ok | none (after rev 41, below) |

The first small-tablet run had 1 double in 600 dispenses: a tablet wedged tilted in its pocket
at the exit and fell late. The disc's closed-pocket undercut went from 12° to 20° (V2 rev 41,
shared with the stand-alone V2), and both the stand-alone V2 and this module were rerun at
200/200. Results are in `results/v2_v7_module/`; the superseded run is in `results/old_rev40/`.

## How it mounts on the V7

- **Position**: module centres on a 72 mm radius at 30°, 90°, 150°, 210°, 270°, 330°,
  same as the V7 modules. The hopper leans outward; the drive and exit duct point down
  and inward.
- **Fastening**: two M3 × 6 heat-set inserts (OD 5 mm) in the base plate, at
  (−24, 0) and (+22, 0) mm in the module frame (+y radially outward). These are the V7
  module positions; the V7 deck holes and its M3 × 12 screws from below are reused.
- **Wires**: the slot in the base plate sits over the deck's motor opening; route the
  motor and beam-break cables through it.
- **Pill drop**: the duct ends 27 mm from the enclosure axis (iron) and 54 mm above the
  deck; pills fall clear of every module's drive into the V7 funnel (checked with a
  pill-sized column from the duct end down to the funnel top).

## Checks run

| Check | Result |
| --- | --- |
| `cad/check_printability.py` on every part | Pass: walls ≥ 1.2 mm, no supports. The shaft gear is allowed 12 mm² of overhang for the 0.4 mm ring where its hub meets the tooth roots |
| Overlaps inside one module (`assemble.py --check`) | Only the expected fits: shaft in the disc bore, motor shaft in the motor gear |
| Overlaps with modules 2 and 6 | None |
| Overlaps with the V7 enclosure, funnel, mounts, weighing station, front panel | Only the base plate's two heat-set inserts (expected: they melt into the plastic) |
| Pill path from duct end to funnel | Clear for iron and small tablets |

## Size

Each module stays inside its 72 mm-wide slice at the deck. The hoppers lean outward, so
the top of each overhangs the enclosure edge: the furthest point is 148 mm from the
enclosure axis (the enclosure radius is 113 mm). Tallest point 140 mm above the deck
(V7 modules: 147.5 mm).

## Print

| Part | File | Qty per module | On the bed |
| --- | --- | --- | --- |
| Disc | `<kit>/disc.stl` | 1 | back face down (as saved) |
| Back plate (duct, bearing tube, motor posts, stand tabs) | `<kit>/backplate.stl` | 1 | front face down (as saved) |
| Hopper | `<kit>/hopper.stl` | 1 | flange down (as saved) |
| Cover | `common/cover.stl` | 1 | outer face down |
| Base plate | `common/base.stl` | 1 | flat |
| Cheek, right and left | `common/cheek_right.stl`, `common/cheek_left.stl` | 1 each | flat |
| Shaft gear | `common/shaft_gear.stl` | 1 | gear face down, hub up |
| Motor gear | `common/motor_gear.stl` | 1 | flat |
| Motor mount | `common/motor_mount.stl` | 1 | front wall down |
| Strap | `common/strap.stl` | 1 | flat |
| Front spacer, rear spacer | `common/spacer.stl`, `common/rear_spacer.stl` | 1 each | flat |

Print the back plate in an opaque colour (the beam-break looks through the duct). Other
settings as in `BUILD.md`. `<kit>/module_assembly.step` shows one module put together;
`python cad/variants/v2_v7_module/assemble.py iron` also writes `iron/v7_assembly.step`,
the whole V7 with six modules (50 MB, not committed).

## Buy, per module

| Item | Qty |
| --- | --- |
| 1/4" steel shaft, cut to 40 mm; file a flat 0.6 mm deep on each end | 1 |
| R4-ZZ ball bearing, 1/4" × 5/8" × 0.196" | 2 |
| Pololu micro metal gearmotor with encoder (as in the BOM) | 1 |
| M3 × 6 heat-set inserts, OD 5 mm | 8 (2 base, 4 hopper, 2 motor posts) |
| M3 × 12 socket screws from under the deck | 2 (the V7 ones) |
| M3 × 10 screws, hopper to back plate | 4 |
| M3 × 10 screws, motor mount to posts | 2 |
| M3 × 12 screws and nuts, cheeks to back-plate tabs | 4 |
| M3 × 6 set screw and M3 nut, shaft gear | 1 each |
| M2 × 8 self-tapping screws, strap | 2 |
| IR break-beam pair, 3 mm | 1 |

## Assembly

1. Press the heat-set inserts: two into the base plate from underneath, four into the
   back of the back plate (hopper holes), one into the end of each motor post.
2. Press one bearing into the pocket in the front of the back plate, the other into the
   rear end of the bearing tube.
3. Press the disc onto one flatted end of the shaft, shaft end flush with the top of the
   disc's boss. Slide the front spacer on behind the disc and pass the shaft through both
   bearings from the front.
4. Slide the rear spacer onto the shaft behind the rear bearing, then the shaft gear (gear
   face toward the bearing). Hold the disc down, push the gear up to the spacer, and
   tighten its set screw on the shaft's rear flat. The disc must turn freely with no end
   play you can feel.
5. Bolt the hopper to the front of the back plate (4 × M3 × 10, groove over the exit hole);
   glue the cover into the hopper mouth on the high side.
6. Push the motor gear onto the gearmotor shaft (one drop of CA on the flat). Lay the motor
   in the motor mount, gearbox face against the front wall, fit the strap with 2 × M2 × 8,
   and screw the mount to the posts with 2 × M3 × 10. The two gears must mesh across their
   full width; turn the disc by hand to check.
7. Bolt the cheeks to the back-plate tabs (4 × M3 × 12 and nuts) and glue them into the
   base-plate slots, square to the base.
8. Fit the beam-break LEDs into the two holes across the duct, 8 mm behind the plate.
9. Set the module on the deck, wires through the slot, and screw it down from below with
   the V7's 2 × M3 × 12.

## Firmware

The gears are 1:1, so encoder counts per disc turn, the 45° index, 25 rpm and timings in
`include/mechanism.h` are unchanged. A spur pair reverses the direction: the disc turns
the opposite way to the motor. Swap the two motor leads (or invert the motor direction in
firmware) so the disc turns the same way as in the simulation.

## Not yet proven

- Spur gears printed in PLA at module 1.5: the backlash allowance (0.1 mm per gear) and
  the 21.15 mm centre distance are nominal; check the mesh by hand before powering.
- The motor is held in its mount by the strap only; there is no hard stop on the gear
  side. Check it does not creep along the mount.
- The hoppers overhang the enclosure by 35 mm each; check the dispenser does not tip
  when a hopper is filled.
- Shaft, bearing and gearmotor sizes are nominal; measure them as in `BUILD.md` section 2.
