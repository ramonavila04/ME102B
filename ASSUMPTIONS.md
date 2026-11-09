# Assumptions and gaps

Each item says what is missing, what was assumed instead, and how to close it.
Items marked **MEASURE** need a team member with calipers or a bench supply.

## Evidence

| # | Gap | Assumption | How to close |
| --- | --- | --- | --- |
| A1 | No jam videos or photos. The Drive videos (IMG_4151–4153, IMG_4298/4299, MOTOR_VIDEO and the sensor tests) could not be downloaded here: Drive downloads are blocked by the network proxy, and the files are 9–264 MB. The team also said it has no jam clips. P4 describes clips 1 and 2 as moving "smoothly by hand". | The sim check (PLAN 4.3) is checked against the team's verbal description ("jams in several places, not consistent") and the P3 note that the plate-to-canister gap lets pills wedge. Neither is a measured jam location. | Record 10 cycles per pill on the current prototype and note each jam's location (canister rim, pocket, brush, drop hole or chute). Compare against the V0 jam-site table in `results/`. |
| A2 | Real pill dimensions are not recorded anywhere. | `iron` (Nature Made Iron 65 mg): Ø 9.5 × 5.0 mm, 0.40 g, round biconvex. This is an estimate for a small coated mineral tablet, not a measurement. "Nature Valley" in chat is taken to mean Nature Made. | **MEASURE** 10 tablets (diameter, thickness, mass); put the mean ± 3σ in `sim/pills.py`, then rerun `make cad sim`. |
| A3 | Other pills in the envelope. | `small` Ø 6.0 × 2.8, `caplet` 19.0 × 8.5 × 6.5, `cap0` size-0 capsule 21.7 × Ø 7.65. These are typical published values for the class, not specific products. | Replace them with the team's actual products if they are known. |
| A4 | Which Onshape tab is current. | The synced assembly `Pill_Dispenser_Clip_On_Canister` (2026-11-09) is the prototype that jams. Parts named `REFERENCE_ONLY_Flexible_Bristles` are modelled as a real compliant brush. | Confirm that the printed prototype matches this tab and has a physical brush. |
| A5 | Scope. | One canister and one pill type per module, dispensing one pill per command. A six-pill system is six modules (or one motor per module, as in the research doc). | The team confirms the scope. |

## Motor and drive

| # | Gap | Assumption | How to close |
| --- | --- | --- | --- |
| M1 | The Pololu #5229 spec page is blocked from this machine. | 12 V no-load speed 35 rpm (BOM note). The sim limits torque to 1.0 N·m, Pololu's recommended maximum for micro-metal gearboxes (10 kg·cm), not the higher stall torque. Gear ratio 1000.0:1 exactly as computed in the firmware (≈ 986.4:1), 12 CPR, so 11 836.9 counts per output turn. | **MEASURE** no-load rpm at 12 V with the encoder test (`pio run -e motor-tb6612`). |
| M2 | Motor driver. | TB6612FNG (BOM and P4). The DRV8833 in the old source program is not used. | — |
| M3 | Board. | Original Adafruit HUZZAH32 (product 3591), per the BOM and repo. P4 lists a "Feather ESP32 V2"; if that is the board, pin numbers change (see `docs/hardware.md`). | Check the silkscreen on the board. |

## Simulation

| # | Gap | Assumption |
| --- | --- | --- |
| S1 | Friction of PLA against coated tablets. | μ drawn uniformly from 0.20–0.60 per trial, separately for pill–part and pill–pill contacts. Static and kinetic are equal, which MuJoCo requires. |
| S2 | Pill stiffness and crushing. | Pills are rigid; MuJoCo's soft contact gives about 0.05 mm of effective compliance. A real pill can chip instead of stalling, so the sim's jam count is a lower bound on damage events. |
| S3 | Brush bristles. | Modelled as 12 hinged flaps with torsional springs, tuned so the tip deflects 3 mm under 0.05 N. The real stiffness is unknown. |
| S4 | Jam definition. | Rotor speed below 10 % of command for more than 0.3 s, or the cycle not finishing within 3× nominal time. Any stall is a jam, even if a reverse-and-retry would clear it. |
| S5 | Printed clearance. | A clearance in the CAD is the as-modelled gap. The sim uses the as-modelled gap. A real print can be 0.1–0.2 mm tighter on each side. |

## Electronics

| # | Gap | Assumption |
| --- | --- | --- |
| E1 | Pin conflicts. | `potentiometer_code_to_screen.ino` (Drive, 2026-11-08) uses GPIO32 for the potentiometer and GPIO13 for TFT D/C. `include/pins.h` uses GPIO32 for motor enable and GPIO13 for the LED. The integrated pin map reassigns pins; see `docs/wiring.md`. |
| E2 | Wokwi. | `wokwi.com` is blocked from this machine, so firmware logic is verified with PlatformIO native unit tests instead of a Wokwi run. |
| E3 | RTC. | Adafruit #3013, a DS3231 on I²C, with a CR1220 cell as listed on BOM Sheet3. |
| E4 | Display. | Adafruit #1770, a 2.8" ILI9341 TFT on SPI, as in the team sketch. The 3" IPS from the P3 slides is not used. |
