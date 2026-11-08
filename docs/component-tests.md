# Standalone hardware test procedures

These are manual bench tests. No hardware test has been performed by the coding
agent. Record date, tester, board, driver, supply, commit and actual observations
in the table below. Upload only one environment at a time; see README commands.

## Beam break (`beam-break`, 115200 baud)

Wire per hardware.md. Align lenses, then block/unblock by hand repeatedly.
Pass: serial output changes between BEAM CLEAR and BEAM BLOCKED and repeats status
every second. An unplugged signal may read CLEAR: check both physical states.
This polling test does not establish reliable fast falling-pill counting.

## Load cell (`load-cell`, 115200 baud)

Set `KNOWN_MASS_G` in the test to match a measured reference mass (default 10g).
Install empty cup, send `t`, place reference mass, wait for settling, send `c`.
Remove the reference mass. Pass: empty cup returns near zero, reference mass reads
near its known value, and readings over 2g say Full (exactly 2g is Not full).
Agree on acceptable measurement tolerance before recording a pass. Repeat tare
and calibration after reset. Verify missing/disconnected sensor reports an error,
not a weight. Averaging is blocking and intended for this standalone test only.

## Motor (`motor-drv8833` OR `motor-tb6612`, 9600 baud)

First confirm the actual carrier and wiring in hardware.md. Secure/unload the
mechanism and use a suitable current-limited motor supply. At boot the motor must
remain OFF, including if switch contacts start closed. The source assumes a
**latching** switch: each settled open/closed transition toggles the motor.
A momentary button would toggle on both press and release and needs a code change.

Pass: first physical latch push starts motion, next stops; encoder counts change
and RPM is plausible; stopped motor stays still. Send `x` while running: motor
stops and requires a new settled switch transition before restarting. Check reset
leaves it stopped. Invalid-transition counts help diagnose noise; there is no
closed-loop speed controller, jam stop or dispensing logic in this test.

| Date/tester | Commit/board/driver/supply | Test | Observations/result |
| --- | --- | --- | --- |
| Pending | Pending | Beam, load cell, motor | Not yet hardware-tested |
