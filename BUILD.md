# Build guide: V2 inclined pocket disc

This builds one dispenser module for one pill type. Two kits are proven in simulation
and ready to print:

| Kit | Folder | Simulated result |
| --- | --- | --- |
| **Iron tablet** (Ø9.5 × 5.0 mm, the team's test pill) | `cad/variants/v2_inclined_disc/iron/` | 200 of 200 trials, 600 dispenses, exactly one tablet each |
| **Small tablet** (Ø6.0 × 2.8 mm) | `cad/variants/v2_inclined_disc/small/` | 200 of 200 trials, 600 dispenses, exactly one tablet each |

The caplet and size-0 capsule kits in the same folder are **experimental: do not build
them yet** (see [Status of the long-pill kits](#status-of-the-long-pill-kits)).

How it works: a disc tilted 50° turns over a fixed back plate, inside the hopper.
Pockets near its rim each hold one tablet lying flat. Tablets pool at the low side of
the hopper, one drops into each pocket as it passes, rides up, and falls through a hole in
the back plate at the top while the disc is stopped. A 96 mm duct carries it past the
drive into the cup.

The drive is a transmission in its own right: the disc sits on a 1/4" shaft carried by two
ball bearings in a tube behind the back plate, and a flexible coupler joins the shaft to
the gearmotor. The firmware turns the disc one pocket (45°) at a time and stops as
soon as the beam-break in the duct sees a tablet.

## 1. Parts list

### Printed parts

Files are in `cad/variants/v2_inclined_disc/`. The disc, back plate and hopper are a
matched set per pill: print all three from the same kit folder.

| Part | File | Qty | Side on the bed | Approx. plastic |
| --- | --- | --- | --- | --- |
| Disc | `<kit>/disc.stl` | 1 | flat back face (boss up) | 10 cm³ |
| Back plate with duct, bearing tube, motor saddle and stand tabs | `<kit>/backplate.stl` | 1 | flat front face (duct up); 99 mm tall | 45 cm³ |
| Hopper | `<kit>/hopper.stl` | 1 | flange | 41–54 cm³ |
| Cover | `common/cover.stl` | 1 | flat outer face | 3 cm³ |
| Motor clamp strap | `common/clamp.stl` | 1 | flat | 1 cm³ |
| Thrust spacer (sets the disc gap) | `common/spacer.stl` | 1 | flat | < 1 cm³ |
| Shaft collar | `common/collar.stl` | 1 | flat end down, boss up | 2 cm³ |
| Side plate, right and left | `common/side_right.stl`, `common/side_left.stl` | 1 each | flat | 14 cm³ each |
| Base, 116 × 195 mm | `common/base.stl` | 1 | flat (slots up) | 135 cm³ |
| Pill cup | `common/cup.stl` | 1 | upright | 6 cm³ |

The STL files are saved in their assembled, tilted position. In the slicer, use "lay on
face" on the side named above. Matching STEP files sit next to each STL.
`<kit>/assembly.step` shows every part in place, with the shaft, bearings, coupler and
motor as reference solids (regenerate with `python cad/variants/v2_inclined_disc/assemble.py`).

### Print settings

| Setting | Value | Why |
| --- | --- | --- |
| Material | PLA. **Print the back plate in black or another opaque colour** | Light PLA lets infrared through the duct walls and the beam-break misses the pill (BOM Sheet 3 note) |
| Nozzle and layer height | 0.4 mm nozzle, 0.16 mm layers | Pocket walls are undercut 12° and the small-tablet disc has 1.2 mm webs |
| Walls | 4 perimeters | Covers the thinnest designed wall (1.2 mm) |
| Infill | 25 % gyroid; 40 % for the disc and back plate | |
| Supports | **None** | `cad/check_printability.py` passes every part: walls ≥ 1.2 mm, sliding gaps 0.4 mm, no overhang beyond 45° |
| Elephant-foot compensation | 0.15 mm | The disc's back face runs 0.4 mm above the back plate |
| Brim | 5 mm on the hopper and side plates | Tall parts on a small footprint |

Do not scale parts in the slicer; the running clearances are modelled in the CAD.

### Bought parts (sources from the team's `BOM 102B` sheet)

| Item | Qty | Source | Used for |
| --- | --- | --- | --- |
| 1000:1 micro metal gearmotor HPCB 12 V with encoder | 1 | Pololu #5229 | Turns the disc |
| Encoder cable, 6-pin JST SH, 30 cm | 1 | Pololu #4763 | |
| 1/4" steel shaft, 2-1/4" (57 mm) long, D-profile or round rod with a filed flat | 1 | ServoCity D-shaft, or cut from 1/4" rod | Carries the disc |
| Ball bearing R4-ZZ, 1/4" × 5/8" × 0.196" | 2 | Any bearing supplier | Shaft bearings |
| Flexible coupler, 3 mm to 6.35 mm, Ø19 × 25 mm | 1 | Amazon, uxcell B09138PC6R | Shaft to motor |
| M3 × 6 screw and M3 nut | 1 each | McMaster (BOM) | Collar set screw |
| ESP32 Feather (HUZZAH32) | 1 | Adafruit #3591 | Controller |
| TB6612FNG motor driver | 1 | Adafruit | Motor driver |
| IR break-beam pair, 3 mm LEDs | 1 | Adafruit #2167 | Confirms each dispense, in the duct |
| Load cell 100 g (TAL221) and HX711 amplifier | 1 each | SparkFun, #13230 | Second confirmation under the cup (mount not designed yet) |
| DS3231 real-time clock and CR1220 cell | 1 | Adafruit #3013 | Schedules |
| 2.8" TFT (ILI9341) | 1 | Adafruit #1770 | Display |
| 10 kΩ panel potentiometer, 2 push-buttons | 1 + 2 | Adafruit, Digi-Key GPTS203211B | Menu |
| Roller-lever microswitch | 1 | BOM Sheet 3 | Home position |
| 12 V supply (Mean Well GST90A12), IEC cord, barrel-to-terminal adapter | 1 | Digi-Key, Adafruit #368 | Power |
| 5 V regulator | 1 | Pololu #4085 | 5 V rail |
| 100 µF and 0.1 µF capacitors, 10 kΩ resistors, 2 A slow-blow fuse | — | Lab stock | See `docs/wiring.md` |
| M3 × 16 screw, M3 nut, M3 washer | 8 screws, 8 nuts, 4 washers | McMaster (BOM) | 4 for hopper to back plate, 4 for back plate to side plates |
| M2 × 8 screw | 2 | McMaster (BOM) | Motor clamp strap |
| CA glue | — | Lab stock | Side plates into the base; cover onto the hopper |

## 2. Measure before you print

1. **Measure 10 tablets** with calipers: diameter, thickness, mass. The iron size in
   `sim/pills.py` (Ø9.5 × 5.0 mm, 0.40 g) is an estimate, not a measurement
   (ASSUMPTIONS A2). If yours differ by more than 0.15 mm, put the measured values in
   `sim/pills.py`, then rebuild and re-test:

   ```bash
   python cad/variants/v2_inclined_disc/build.py iron
   ```

   ```bash
   python cad/check_printability.py cad/variants/v2_inclined_disc/iron/manifest.json
   ```

   ```bash
   python -m sim.campaign v2_inclined_disc --pills iron --trials 200 --workers 4
   ```

2. **Measure the drive parts.** `build.py` assumes: gearmotor body 12 × 10 mm with a 9 mm
   shaft (`GEARBOX`, `MOTOR_SHAFT`); bearings 15.875 mm outside diameter and 4.98 mm wide
   (`BRG_OD`, `BRG_W`); coupler Ø19 × 25 mm (`COUPLER`); shaft 57.15 mm long
   (`DRIVE_LEN`). If a part differs, change the constant and rebuild.
3. **Shaft flat.** The disc bore is a D: 6.35 mm round, 5.75 mm across the flat. File a
   flat 0.6 mm deep on the front 10 mm of the shaft until it measures 5.75 mm, or, for a
   bought D-shaft, measure across its flat and set `DRIVE_FLAT`. File a second flat near
   the rear end for the coupler's set screw.

## 3. Assembly

1. **Disc.** Deburr the pocket edges with a blade. The back face must be flat: if the
   disc rocks on a table, sand it on 400-grit paper on glass.
2. **Test-fit the disc on the 1/4" shaft.** The D-bore is a light press fit on the filed
   flat. If it is loose, add one drop of CA on the flat at step 5.
3. **Bearings.** Press one bearing into the pocket in the front of the back plate until it
   seats (it ends 1.6 mm below the plate face). Press the other into the rear end of the
   bearing tube until it seats on its step.
4. **Hopper.** Seat the hopper flange on the front of the back plate with the wide groove
   in its bore over the exit hole, and bolt it with 4 × M3 × 16, washer and nut.
5. **Shaft and disc.** Press the disc onto the flatted end of the shaft, shaft end flush
   with the top of the disc's centre boss. Slide the thrust spacer onto the shaft behind
   the disc, then pass the shaft through both bearings from the front. The spacer rests on
   the front bearing's inner ring and holds the disc 0.4 mm off the plate.
6. **Collar.** Drop the M3 nut into the collar's slot and start the M3 × 6 screw. Slide
   the collar onto the shaft behind the rear bearing, small boss toward the bearing. Push
   it up to the bearing while holding the disc down, back it off a paper's thickness, and
   tighten the screw. The disc must spin freely with no end play you can feel.
7. **Coupler and motor.** Clamp the coupler's 6.35 mm end on the shaft's rear flat, 1.5 mm
   behind the collar. Lay the gearmotor in the saddle from the open side, shaft into the
   coupler's 3 mm end, and tighten that set screw on the D-flat. Fix the clamp strap across
   the motor with 2 × M2 × 8 into the rails (they cut their own thread; stop when snug).
   Turn the disc by hand: the motor end should not wobble.
8. **Cover.** Press the cover's lip into the hopper mouth over the exit side (the high
   side once assembled) and fix it with two drops of CA.
9. **Stand.** Glue the two side plates into the base slots, square to the base. Bolt the
   back-plate tabs to the side plates with 4 × M3 × 16 and nuts. The disc now sits at 50°
   with the hopper leaning over the long end of the base and the duct pointing down and
   back.
10. **Cup.** Stand it on the base under the end of the duct, behind the motor.
11. **Beam-break.** Push the IR emitter and receiver into the two holes across the duct,
   8 mm behind the plate, facing each other.
12. **Home switch.** Mount the roller-lever switch on a side plate so the disc's boss or a
    pocket edge trips it once per revolution. No mount is printed for it yet; use
    double-sided tape for the first build.
13. **Electronics.** Wire as in `docs/wiring.md` (diagram `docs/wiring.svg`), following
    its bring-up order: power with no loads first, then each 3.3 V part with its component
    test, motor last.

## 4. Firmware

```bash
pip install -r requirements-dev.txt
```

```bash
pio run -e dispenser -t upload --upload-port YOUR_PORT
```

The default build is for the iron kit. For the small-tablet kit, add
`build_flags = -DMECH_PILL_SMALL` under `[env:dispenser]` in `platformio.ini`.

`include/mechanism.h` is generated from the simulated design by
`python sim/export_firmware_constants.py`, so the motor moves exactly as it did in the
simulation: 45° per step at 25 rpm with 120 ms ramps, a 600 ms pause, and up to 16
steps before it reports the canister empty.

**Home offset, once per build.** After homing, jog the disc until a pocket is centred
over the exit hole, read the angle on the serial monitor, and put it in
`MECH_HOME_OFFSET_DEG` in `sim/export_firmware_constants.py`. Regenerate the header and
rebuild.

## 5. Test on the real build

The simulation's claim is zero jams, zero doubles and zero misses over 200 randomised
trials of three dispenses each. Check it on hardware with the same protocol:

1. **Dry run.** With the hopper empty, send 10 dispense commands. Each should end in
   "Canister empty" after 16 steps with no stall. A stall here means a rubbing part, not a
   pill problem: fix it before going on.
2. **Loaded rounds.** Do 10 rounds. In each, pour in a different number of tablets
   between 3 and 20 (3 and 30 for small tablets), send 3 dispense commands, and after
   each one count what is in the cup and empty it.
3. **Include the last-tablet case.** At least 3 of the 10 rounds should start with
   exactly 3 tablets, so the third dispense is the last tablet in the hopper.
4. **Record every dispense** in the table: one tablet, two or more, none, or a stall. For
   a failure, note where the tablet was (pool, pocket on the way up, exit, duct) and take
   a photo.
5. **Pass:** 30 dispenses in a row with exactly one tablet each. One jam or one double
   fails the test.
6. **Compare the original prototype.** Run the same 10 rounds on the current prototype
   with iron tablets and note where it jams, then compare with the original design's row
   and jam sites in `results/COMPARISON.md`. This is the check the simulation could not
   get from video (ASSUMPTIONS A1).

| Date, tester | Kit | Round | Tablets loaded | Dispense 1 | Dispense 2 | Dispense 3 | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| | | | | | | | |

## Not yet proven on hardware

- **Friction and dust.** The simulation uses rigid pills with friction from 0.2 to 0.6.
  Coatings, static and tablet dust are not modelled.
- **The low wall of the hopper is a 40° slope** once assembled. That is 9° steeper than
  the worst friction tested, so a stickier tablet could hang there.
- **Print accuracy.** The simulation uses the designed 0.4 mm gaps. A print can be
  0.1–0.2 mm tighter per side, and a warped disc will rub.
- **Tablet size.** The iron dimensions are an estimate until section 2 is done.
- **Drive line fits.** The bearing pockets, coupler length and motor saddle are sized from
  nominal dimensions, not measured parts. Expect to adjust `BRG_FIT` after the first print.
  The flexible coupler adds a little twist between the encoder and the disc.
- **Load cell and home switch** have no printed mounts yet. The firmware treats the load
  cell as a second check; the beam-break alone decides the result.
- **Firmware on hardware.** It compiles and passes 28 host tests per kit, but has not run
  on the board. The Wokwi simulation could not be run from the build machine.

## Status of the long-pill kits

The caplet (19 × 8.5 × 6.5 mm) and size-0 capsule kits are in the repository but have
**not** passed the 200-trial test and are not cleared to build. Their latest revision
(half-depth pockets, 5 rpm, a hub that keeps pills lying along the rim) showed no jams or
doubles in small targeted tests, but its full campaign has not been run. Long pills fail
in ways tablets do not: they stand on end, pair up in one pocket, and lock each other
when only a few are left. See `cad/variants/v2_inclined_disc/DESIGN.md`.
