# V1: minimal fix of the team's indexed rotor

`build.py` regenerates every part from `sim/pills.py`:

    python cad/variants/v1_fixed_rotor/build.py            # all four pill kits
    python cad/check_printability.py cad/variants/v1_fixed_rotor/*/manifest.json
    python -m sim.campaign v1_fixed_rotor --trials 200

The architecture is the team's: a vertical-axis rotor under a Ø67.5 mm canister,
a fixed deck with a fill opening, a drop hole over a chute, and the Pololu 1000:1
micro gearmotor underneath. Rotor top is z = 0; the drop hole is on +x; the rotor
indexes counter-clockwise by one pocket pitch per step (firmware: up to N steps
per dispense, stop when the chute beam breaks).

## What changed vs V0, and why

| V0 (team CAD) | V1 | Failure it removes |
| --- | --- | --- |
| 3 generic 12 × 27 mm slots with 8.8 × 23.8 liners | One pill-specific rotor per pill type: N pockets (iron 6, small 8, caplet 3, cap0 3) sized pill + tolerance + 0.9 mm per side, too small for two pills side by side | Iron misses (didn't fit the liner); 2–8 small tablets per slot (doubles) |
| Pocket depth 6 mm for every pill | Shallow pocket: floor-to-rotor-top ≈ 0.6 × pill thickness (min rotor 1.6 mm) | A pill that is half in a deep pocket is gripped and sheared; a shallow pocket lets it tip out |
| Rotor wall 2.35 mm above a fixed floor liner | Rotor slides on the floor with 0.4 mm clearance; rim in a spacer ring with 0.4 mm | Small tablets entering the under-rotor gap |
| Deck 0.35 mm above the rotor, 45° underside chamfer at the stripping edge (wedge 1.65 → 0.35 mm) | Deck 0.4 mm above the rotor in the fill sector. Over the covered sector the deck is relieved to a height midway between a seated pill and a pill lying on the rotor top (below a capsule's axis). The stripping edge is a vertical face, oblique to the pocket motion (20–35°, outer end upstream) | Converging wedge at the stripping edge; extra pills riding through |
| Fill opening reaches r = 30.8 over a Ø52 rotor | Fill opening is an annular slot exactly over the pocket track, inside the rotor; a hub cone and an outer cone (50°) shed pills into it, a ridge baffle (50°) roofs the covered sector | Pills lost past the rotor rim; pills riding the rotor off the track and never lining up with a pocket |
| Nylon brush | Removed | Brush pushed pills into the gaps; flexible bristles let a second pill ride through |
| Single printed housing | Floor part with spacer ring and collar (locates deck and canister, anti-rotation rib), deck insert, canister, lower enclosure with chute and motor post | Printable without supports; pill kit = rotor + floor + deck |

## Parts, print orientation and settings

PLA, 0.4 mm nozzle, 0.2 mm layers, 3 perimeters, 20 % gyroid infill unless noted.
No supports on any part (`check_printability.py` passes: walls ≥ 1.2 mm, every
downward face steeper than 45°, sliding clearances 0.4 mm).

| Part | Per pill? | Print orientation | Notes |
| --- | --- | --- | --- |
| `rotor` | yes | upside down (top face on the bed) | 100 % infill for the hub boss (4 perimeters is enough). D-bore 3.05 mm with flat at 1.05 mm: press onto the 3 mm D shaft; ream if tight |
| `floor` | yes | as assembled (underside on the bed) | top face is the rotor running surface: print it with ironing if available |
| `deck` | yes | upside down (cone tops on the bed) | every funnel face is 50° so it prints without support upside down; the relieved underside then faces up |
| `lower_enclosure` | common | as assembled | chute is sized for the largest kit (cap0); motor post takes a Pololu #989 bracket |
| `canister` | common geometry | upside down | spigot drops into the floor-part collar and clamps the deck |

## Fasteners and assembly

1. Motor: Pololu 1000:1 HPCB 12 V micro gearmotor in a Pololu #989 bracket,
   2 × M2 × 6 screws into the motor post (teardrop pilot holes at 18 mm spacing;
   check the bracket's hole spacing before printing). Gearbox face 1.5 mm below
   the floor part.
2. Floor part onto the lower enclosure: 3 × M2 × 12 pan-head self-tapping
   screws at r = 30 mm (counterbored in the spacer ring, pilot holes in the
   enclosure bosses).
3. Rotor pressed onto the D shaft through the floor's hub hole (0.4 mm radial
   clearance); check it turns freely with 0.4 mm under it (feeler gauge).
4. Deck insert into the collar, notch over the anti-rotation rib. It sits on the
   spacer ring, which sets the 0.4 mm rotor-to-deck gap.
5. Canister spigot into the collar; it clamps the deck. Secure with tape or the
   team's snap clips.

Changing pill type = swap rotor + floor + deck (three prints).

## Revision history (sim results)

RESULTS_PLACEHOLDER
