# Hardware baseline and shared pin map

> **Full system wiring, pin table, power budget, bring-up order and safety
> notes: [wiring.md](wiring.md)** (diagram: [wiring.svg](wiring.svg)). The
> table below lists only the pins the standalone component tests use. Both
> follow [`include/pins.h`](../include/pins.h).

Target: original Adafruit HUZZAH32, product 3591, PlatformIO `featheresp32`.
The original beam-break document targets the Feather V2, where RX is GPIO7.
Do not use that mapping on the original ESP32: GPIO7 is connected to flash.
This project uses the original HUZZAH32's RX, GPIO16. Confirm which board you
have before wiring.

| Signal | GPIO | Notes |
| --- | --- | --- |
| Beam receiver | 16 | RX on the original board. External 10k pull-up to 3.3V. |
| HX711 DAT | 36 | Input only. External 10k pull-up to 3.3V. |
| HX711 SCK | 4 | Clock |
| Motor-test button (= system Back) | 19 | Switch to ground, internal pull-up. MISO is unused by the TFT. |
| Status LED | 12 | CHANGED from the on-board LED on 13, because 13 is now TFT D/C. External LED + 330R to GND. |
| Driver AIN1 / IN1 | 27 | Direction/control |
| Driver AIN2 / IN2 | 33 | Direction/control |
| Driver PWMA | 21 | NEW. Was tied to 3.3V. The TB6612 test drives it HIGH; the dispenser uses 20 kHz PWM. |
| Encoder A | 34 | Input only, no internal pull-up |
| Encoder B | 14 | Input |
| Driver enable | 26 | CHANGED from 32, because 32 is now the pot. TB6612 STBY or DRV8833 nSLEEP. External 10k pull-down. |

The rest of the system (TFT, pot, Select, home switch, RTC, buzzer) is
listed in [wiring.md](wiring.md#b-pin-table).

All GPIO signals must stay within ESP32 3.3V logic levels. Disconnect power
before rewiring. Use a common logic ground. Power the encoder from 3.3V as in
the source program, because its output pull-ups follow that supply. Verify the
encoder output levels before connecting. Do not power the motor from the
Feather's 3V pin.

## Select the actual motor driver

The source motor program says **DRV8833, 8V**; the BOM lists **TB6612FNG and
12V**. The integrated `dispenser` firmware assumes the TB6612 from the BOM.
The two motor test environments select the bench wiring explicitly:

- `motor-drv8833`: IN1=27, IN2=33, nSLEEP=26. Keep the source's 8V test setup;
  do not apply the BOM's 12V to a DRV8833. Check the actual carrier's voltage
  and current ratings. If its sleep input is tied high, change that wiring so
  the enable signal can disable it.
- `motor-tb6612`: AIN1=27, AIN2=33, PWMA=21 (driven HIGH = full duty),
  STBY=26, logic VCC=3.3V. The motor supply connects to VM, not VCC. Tie the
  unused channel B inputs low. Verify the carrier's specifications and the
  motor stall current before choosing the supply and current limit.

Both tests drive in one direction at full duty and stop by lowering enable.
GPIO26 needs an external pull-down (for example 10k to ground) so the driver
stays disabled during reset. Make sure the carrier has compatible
direction-input pull-downs, or add them. Confirm all enable and PWM
connections on your actual board: compiling an environment cannot verify
wiring. Serial `x` is a software stop. Keep a physical power disconnect within
reach during bench testing.

**Rewiring note:** a bench setup wired for the earlier map (STBY on 32, PWMA
tied to 3.3V, LED on 13) must be changed to STBY on 26 and PWMA on 21 before
uploading any current firmware.

## Load cell and beam

HX711 VCC and VDD go to 3.3V, GND to ground. Load-cell wires: red E+, black
E-, green A+, white A-. For the first sensor tests, disconnect the motor and
the external regulator and power from USB. The cup plus its contents must
stay below the cell's 100g capacity, even after tare. Beam transmitter and
receiver: red to 3.3V, black to ground, receiver signal to GPIO16.

## RTC and TFT

DS3231 on I2C SDA=23 and SCL=22, powered from 3.3V so that its pull-ups go to
3.3V. TFT on VSPI: SCK=5, MOSI=18, CS=17, D/C=13, no MISO and no RST. VIN is
5V. Run the `ui-panel` component test to check them.
