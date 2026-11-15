# Standalone hardware test procedures

These are manual bench tests. Do them in the order given in
[wiring.md](wiring.md#e-build-and-bring-up-order). Host-side logic tests
are separate: `pio test -e native` (see README). No hardware test has been performed by the coding
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

## UI panel (`ui-panel`, 115200 baud)

Covers the TFT, pot, Select and Back buttons, DS3231 RTC, home switch,
buzzer and status LED on the system pin map ([wiring.md](wiring.md)). The
test holds the motor driver in standby (STBY on GPIO26 LOW). Add one part at
a time. Set the RTC from the serial monitor with `T YYYY-MM-DD HH:MM:SS`.
Pass:
- The pot bar and number follow the knob over the full 0 to 4095 range,
  without jumping more than a few counts at rest.
- SEL, BACK and HOME show 1 only while that switch is pressed.
- Select gives a short beep.
- The status LED blinks at 1 Hz.
- The RTC seconds tick, and the time survives a reset. With the CR1220
  fitted, it also survives a full power cycle.
- `RTC not found` means there is an I2C wiring fault (SDA 23, SCL 22).

## Motor (`motor-drv8833` OR `motor-tb6612`, 9600 baud)

First confirm the actual carrier and wiring in hardware.md. Secure/unload the
mechanism and use a suitable current-limited motor supply. At boot the motor must
remain OFF, including if switch contacts start closed. The source assumes a
**latching** switch: each settled open/closed transition toggles the motor.
A momentary button toggles on both press and release. With the system's
momentary Back button on GPIO19, the motor therefore runs only while the
button is held, which is an acceptable dead-man behaviour for this test.
Rewire STBY/nSLEEP to GPIO26 and (TB6612) PWMA to GPIO21 first; see
[hardware.md](hardware.md).

Pass: first physical latch push starts motion, next stops; encoder counts change
and RPM is plausible; stopped motor stays still. Send `x` while running: motor
stops and requires a new settled switch transition before restarting. Check reset
leaves it stopped. Invalid-transition counts help diagnose noise; there is no
closed-loop speed controller, jam stop or dispensing logic in this test.

| Date/tester | Commit/board/driver/supply | Test | Observations/result |
| --- | --- | --- | --- |
| Pending | Pending | Beam, load cell, UI panel, motor | Not yet hardware-tested |
| Pending | Pending | Integrated `dispenser` (wiring.md step 8) | Not yet hardware-tested |
