# Hardware baseline and shared pin map

Target: original Adafruit HUZZAH32, product 3591, PlatformIO `featheresp32`.
The original beam-break document targets Feather V2 (RX=GPIO7). That mapping must
not be used on the original ESP32, where GPIO7 is connected to flash. This project
uses original HUZZAH32 RX=GPIO16. Confirm the physical board before wiring.

| Signal | GPIO | Notes |
| --- | --- | --- |
| Beam receiver | 16 | RX on original board; external 10k pull-up to 3.3V |
| HX711 DAT | 36 | Input only; external 10k pull-up to 3.3V |
| HX711 SCK | 4 | Clock |
| Motor button | 19 | Switch to ground; internal pull-up |
| Onboard LED | 13 | Motor status |
| Driver AIN1 / IN1 | 27 | Direction/control |
| Driver AIN2 / IN2 | 33 | Direction/control |
| Encoder A | 34 | Input only, no internal pull-up |
| Encoder B | 14 | Input |
| Driver enable | 32 | NEW: TB6612 STBY or DRV8833 nSLEEP |

All GPIO signals must stay within ESP32 3.3V logic levels. Disconnect power before
rewiring. Use a common logic ground. Power the encoder from 3.3V as in the source
program, since its output pull-ups follow that supply. Verify encoder output
levels before connecting. Do not power the motor from the Feather's 3V pin.

## Select the actual motor driver

The source motor program says **DRV8833, 8V**; the BOM lists **TB6612FNG and 12V**.
The two build environments explicitly select the bench wiring:

- `motor-drv8833`: IN1=27, IN2=33, nSLEEP=32. Keep the source's 8V test setup;
  do not apply the BOM's 12V to a DRV8833. Check the actual carrier's voltage and
  current ratings. If its sleep input is tied high, modify that wiring to allow
  the enable signal to disable it.
- `motor-tb6612`: AIN1=27, AIN2=33, STBY=32, PWMA tied to 3.3V for full-speed
  testing, logic VCC=3.3V. Motor supply connects to VM, not VCC. Keep unused
  channel inputs low. Verify the carrier's specifications and motor stall current
  before choosing the supply/current limit.

Both tests drive in one direction at full duty and stop by lowering enable.
GPIO32 requires an external pull-down (for example 10k to ground) so the driver
stays disabled during reset. Ensure the carrier has compatible direction-input
pull-downs or add them. Confirm all enables/PWM connections on your actual board;
compiling an environment cannot verify wiring. Serial `x` is a software stop;
keep a physical power disconnect accessible during bench testing.

## Load cell and beam

HX711 VCC and VDD -> 3.3V, GND -> ground. Cell red E+, black E-, green A+, white A-.
For initial sensor tests disconnect the motor and external regulator, using USB
power. Cup plus contents must remain below the cell's 100g capacity even after tare.
Beam transmitter/receiver red -> 3.3V; black -> ground; receiver signal -> GPIO16.

RTC and TFT wiring is intentionally deferred. GPIO19 is commonly SPI MISO, so
plan and review the TFT bus before combining it with the motor test.
