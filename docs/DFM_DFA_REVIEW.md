# DFM / DFA review: V7 dispenser with six V2 modules, chute and pill cup

Scope: everything needed to build the V7 dispenser with the V2 disc modules, as it stands on
branch `feature/v7-canister`.

| Area | What was reviewed |
| --- | --- |
| Module CAD | `cad/variants/v2_v7_module/build.py`, the V2 parts it reuses (`cad/variants/v2_inclined_disc/build.py`) and `assemble.py` |
| Chute CAD | `cad/variants/v2_v7_module/chute.py`: chute, pill cup and brackets |
| V7 enclosure | The V7 enclosure from the team's STEP (`cad/onshape/V7_Pill_Dispenser_Heat_Inserts.step`) |
| Firmware | `firmware/dispenser/main.cpp`, `include/pins.h`, `include/mechanism.h` and `platformio.ini` |
| Docs | The module README and the build steps |

DFM here means 3D printing (PLA, 0.4 mm nozzle, no supports) plus bought parts.

Every finding below was checked against the geometry or the code, not by eye.

## Summary

| # | Finding | Severity | Status |
| --- | --- | --- | --- |
| 1 | The hopper's M3 × 6 heat-set inserts went into a 3 mm back plate: half of each insert stuck out | DFM, high | **Fixed**: 3.5 mm bosses behind the plate |
| 2 | Each motor-post insert hole was exactly as deep as its insert, so the M3 × 10 screw bottomed out | DFM, high | **Fixed**: hole 9 mm deep |
| 3 | The motor posts left only 1.5 mm of plastic round each insert | DFM, medium | **Fixed**: post R 3.5 → 4.0 (2 mm wall; 1 mm to the gear tips) |
| 4 | The side chute joints needed 10.4 mm of screw through the wall and rib, so an M3 × 12 countersunk reached only 1.3 mm into the insert | DFA, high | **Fixed in the buy list**: M3 × 16 countersunk on the sides, M3 × 12 at the front |
| 5 | The chute cannot be lowered straight into the enclosure: its lip is under the window's top edge and its sides are under ribs | DFA, high | **Path found and checked**: lower it 40 mm behind its final place, then slide it forward 40 mm (`sim/v7_chute_install.py`) |
| 6 | The pill cup cannot be lifted straight out: the chute lip sits inside it | DFA, medium | **Path found and checked**: forward 6 mm, then up and forward (`sim/v7_cup_removal.py`) |
| 7 | README said "swap the motor leads" for the reversing gear pair; that trips the ENCODER DIRECTION fault, because the encoder is on the motor | Firmware / DFA, high | **Fixed**: `pio run -e dispenser-v7` inverts motor and encoder together |
| 8 | The iron and small back plates and hoppers look alike | DFA (mistake-proofing) | **Fixed**: kit name debossed on both |
| 9 | Four M3 socket-screw lengths per module (10 and 12) | DFA | **Fixed**: all M3 socket screws are M3 × 12 (lengths checked) |
| 10 | Fits (bearing press, inserts, bores) are nominal and printer-dependent | DFM | **Added**: `fit_test/fit_coupon.stl`, print before the six sets |
| 11 | Electronics serve one module: every header GPIO is used | System / DFA, blocker | **Open**: team decision (options below) |
| 12 | No home sensor or mount on the V7 module; the firmware needs one | DFA, high | **Open** |
| 13 | Modules screw on from under the deck, so replacing one means lifting the deck with all six | DFA (service) | **Open**, recommendation |
| 14 | Glued joints: cheeks into base, cover onto hopper | DFA (service) | **Open**, recommendation |
| 15 | The shaft is cut and filed by hand (6 times) | DFA | **Open**, recommendation |
| 16 | The V7 enclosure's lower body is 226 × 277 mm and its deck Ø226 mm | DFM (printer) | **Open**: check the team's printer bed |

## Fixed in this pass

### 1–3. Heat-set inserts

- **Problem.**
  - The V2 back plate is 3 mm thick, and the hopper bolts into four M3 × 6 inserts pressed in from the back.
  - Pressed flush at the back, each insert stood 3 mm proud of the front face, under the hopper flange.
  - Pressed flush at the front, it stood 3 mm proud at the back. Either way only 3 mm of it was held.
- **Fix for the hopper inserts.**
  - Each hole now has a Ø7.5 × 3.5 mm boss behind the plate, so the 6 mm insert sits fully in 6.5 mm of plastic, flush with the boss end.
  - R4 would have touched the plate's R40 edge and broke the mesh, so the boss is R3.75.
  - The bosses stop 0.5 mm short of the cheeks.
- **Fix for the motor posts.**
  - The insert hole is now 9 mm deep. The 6 mm insert sits flush at the end, and the M3 screw ends 6 mm in, 3 mm short of the hole bottom.
  - The posts are R4 (2 mm of wall). The motor gear tips still clear them by 1.0 mm.
- **Checks.** Printability passes for both kits and the common parts. `assemble.py --check`
  finds no new overlaps: inside the module, with neighbouring modules and with the V7 parts.
- **Pill path.**
  - The pill-path simulation still holds. The bosses are on the plate's rear face at radius 36 mm, outside the duct.
  - A pill only reaches the back of the plate inside the duct.

### 4. Chute joint screws

The chute is screwed to each bracket from inside the trough. On the side brackets the screw passes:

- the 2.4 mm wall;
- the 8 mm rib;

then enters the bracket's insert.

- An M3 × 12 countersunk, whose stated length includes the head, sits 0.3 mm below the surface and reaches only 1.3 mm into that insert.
- An M3 × 16 reaches 5.3 mm, inside the 6.5 mm insert hole.
- The front rib is 3.6 mm, so the front joint stays M3 × 12 (5.7 mm in).

### 5. Chute install path (new check)

- **What was checked.** A clearance check at 0.25 mm margin, against:
  - the enclosure (deck off);
  - the front panel;
  - the weighing station;
  - the three brackets already fitted.
- **Result.**
  - Lowered straight down, the chute hits after 2 mm. Its lip is under the window's top edge (y −120..−107, z ≈ −100).
  - Lowered 40 mm further back, it clears at every height, and then slides forward 40 mm into place.
  - At 30 mm back it hits ribs under the deck front; at 50 mm it hits the enclosure low down.
- **Rerun.** `python sim/v7_chute_install.py` checks the whole path and exits non-zero if any step is blocked.

### 6. Pill cup removal (new check)

- **Why.** A straight lift hits the chute lip, and a straight forward pull hits the tray's front ramp.
- **Path.** Forward 6 mm, then up and forward to about 16 mm up, then out of the window.
- **Result.** The path keeps 1 mm clear of everything (`python sim/v7_cup_removal.py`).
- **Load.** The cup is about 7 g of PLA. With 4 iron pills, the 100 g load cell carries under 10 g.

### 7. Motor direction on the geared module

- **Cause.** The disc turns opposite to the motor, and the encoder measures the motor.
  - Swapping the motor leads reverses the motor but not the encoder, so the firmware stops with ENCODER DIRECTION.
  - Leaving it alone runs the disc backwards with no fault.
- **Fix.** A new build flag, `MECH_DRIVE_REVERSED` (env `dispenser-v7`), flips both signs. The original wiring-polarity switches are kept separately.
- **Tests.** The polarity logic was compiled with the host compiler both ways, and the native test suite passes.
- **Not built.** The ESP32 build could not be compiled here: its library download is blocked by the network.

### 8–10. Mistake-proofing, fastener count, fit coupon

- **Kit labels.** IRON or SMALL is debossed 0.6 mm:
  - in the back plate's rear face (top when printing, below the gears);
  - in the hopper flange top.

  The discs already differ visibly by pocket size.
- **Screws.**
  - M3 socket screws per module are now one length, M3 × 12 (12 per module).
  - Fastener types per module drop from 6 to 5: M3 × 12, M3 set screw, M3 nut, M2 × 8 self-tapper, M3 insert.
  - Lengths checked:

    | Joint | Stack | Where an M3 × 12 ends |
    | --- | --- | --- |
    | Hopper | 3 mm flange + 6.5 mm insert stack | 2.5 mm past the boss, in open air |
    | Motor mount | 4 mm ear + 9 mm hole | 8 mm in |
    | Cheeks | 5 mm tab + 4 mm cheek + 2.4 mm nut | 0.6 mm past the nut |
    | Deck | 5 mm deck + through-insert | — |

- **Fit coupon.** `cad/variants/v2_v7_module/fit_test.py` writes `fit_test/fit_coupon.stl` (29 cm³, flat, no supports). It has:
  - 4 bearing pockets at +0.0 to +0.3 mm;
  - 4 insert holes, Ø3.9–4.2;
  - 3 shaft bores at +0.1 to +0.3 mm;
  - 3 motor D-bores at +0 to +0.1 mm.

  Print it once per printer, then set `BRG_FIT` and the bores before printing 6 module sets.

## Open items for the team

### 11. Electronics for six modules (blocker)

`include/pins.h` assigns all 21 header GPIOs of the HUZZAH32 to one module:
- motor driver: 4 pins;
- encoder: 2;
- beam-break: 1;
- home switch: 1;
- plus the TFT, buttons, pot, load cell, RTC, buzzer and LED.

Six modules need about 5 more signals each:
- a motor channel;
- a quadrature encoder, at about 5 kHz at 25 rpm;
- a beam-break.

That is about 30 more signals. The firmware also drives one motor.

Options, roughly cheapest first:
1. **One module moves at a time.** Share the encoder and beam lines through an analog
   multiplexer (one select bus). Drive the six motor channels from three TB6612 boards through an I²C PWM/GPIO expander.
   The ESP32 pulse counter keeps the encoder counting.
2. **A second microcontroller** (or one per pair of modules) on I²C or UART, running the
   existing per-module motion code; the HUZZAH32 keeps the UI, scale and schedule.
3. A board with more GPIO in place of the HUZZAH32.

This decides the wiring harness and where the boards sit inside the enclosure (now mostly
filled by the chute), so it should be settled before the enclosure is printed.

### 12. Home sensing

- **Gap.** The firmware homes on a switch (`HOME_SWITCH`, GPIO39). The V7 module has no switch, no flag and no mount for one. The stand-alone V2 also had none: BUILD.md says to tape it on.
- **Backlash.** With the encoder on the motor and 3° of gear backlash, homing should sense the disc side.
- **Suggestion.** A flag on the shaft-gear hub and a slotted optical switch on the motor mount. Both are behind the plate, away from pills.
- **To decide first.** The sensor part and its dimensions are not in the BOM. This needs choosing before a mount is drawn.

### 13. Servicing one module

- **Problem.** Each module is held by two M3 screws from under the deck, and the deck carries all six modules. So replacing one module means lifting the deck and the other five.
- **Options.**
  - Inserts in the deck and screws from above, through the base plate. The screw heads sit under the leaning hopper and drive, so this needs a long hex driver or a rework of the base.
  - Keep the current design and accept the deck lift.
- **Also unknown.** The STEP does not show how the deck is held to the enclosure.

### 14. Glued joints

The cheeks are glued into the base-plate slots and the cover is glued onto the hopper.

- **Problem.** Neither can be taken apart. The cheeks' squareness depends only on the slot.
- **Suggestions.**
  - Screw each cheek to the base with one M3 and an insert, or print the base and cheeks as one part (3 parts become 1).
  - Snap or screw the cover on.

### 15. Shaft machining

- **Today.** Each module's 1/4" shaft is cut to 40 mm and has two 0.6 mm flats filed by hand.
- **Suggestion.** Buying 1/4" D-profile shaft (one continuous flat) removes the filing. The flat suits both the disc and the gear set screw. Bearings on a D-shaft are common in hobby drives.
- **To check.** The disc bore and the bearing seats for a D-shaft against the part actually bought.

### 16. Enclosure printing

- **Sizes.** The V7 enclosure is three printed parts:

  | Part | Size | Plastic |
  | --- | --- | --- |
  | Deck | Ø226 × 5 mm | 130 cm³ |
  | Inner shell | Ø226 × 149 mm | 221 cm³ |
  | Lower body with front bay | 226 × 277 × 101 mm | 208 cm³ |

- **Printer.** The lower body needs a bed of about 280 mm, or a split. The deck and shell need at least 230 mm. Check the team's printer before committing.

## Part count and material

| Per module | Count |
| --- | --- |
| Printed parts | 13 (disc, back plate, hopper, cover, base, 2 cheeks, 2 gears, motor mount, strap, 2 spacers) |
| Bought parts | 34 (shaft, 2 bearings, gearmotor, 8 inserts, 12 M3 × 12, 5 M3 nuts, set screw, 2 M2 × 8, IR pair) |
| Fastener types | 5 |
| Plastic | 109 cm³ iron kit, 119 cm³ small kit |

Six modules: 78 printed and 204 bought parts, about 0.7 L of plastic.

| Chute set (once) | Count |
| --- | --- |
| Printed | 5 parts (chute, pill cup, 3 brackets), 82 cm³ |
| Hardware | 9 (3 inserts, 3 M3 × 16, 2 M3 × 16 countersunk, 1 M3 × 12 countersunk) |

The chute is the largest new print: 93 × 190 × 71 mm on its floor, which fits a 220 mm bed.

## Checks run in this pass

| Check | Result |
| --- | --- |
| `check_printability.py` on every module, chute and coupon part (wall ≥ 1.2 mm, no supports, watertight) | Pass |
| `assemble.py iron --check`, `assemble.py small --check` | Only the expected fits (shaft in disc, motor gear on shaft, strap clamp, base inserts) |
| Moving-part clearances in one module | Disc 0.38–0.40 mm, gears to plate/mount 1.0–2.2 mm, gear mesh 0.15 mm |
| `sim/v7_chute_install.py` | Pass (40 mm offset path) |
| `sim/v7_cup_removal.py` | Pass, 1 mm margin |
| `pio test -e native` | Pass |
| `pio run -e dispenser-v7` | Not run: library download blocked here |
