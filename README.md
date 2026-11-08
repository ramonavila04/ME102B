# ME102B automatic pill dispenser

ESP32 firmware bring-up for the original Adafruit HUZZAH32 (BOM product 3591).
**This is a bench-test baseline, not a completed automatic dispenser.** The default
program holds motor controls low. Component tests are uploaded one at a time and
replace the currently installed program.

## Build and upload

Install Python 3.11 and Git, then:

```sh
git clone https://github.com/ramonavila04/ME102B.git
cd ME102B
python -m venv .venv
# macOS/Linux:
source .venv/bin/activate
# Windows PowerShell instead: .venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
pio run                         # motor-disabled scaffold
pio run -e beam-break           # compile a standalone test
pio run -e load-cell
pio run -e motor-drv8833
pio run -e motor-tb6612
pio device list
pio run -e beam-break -t upload --upload-port YOUR_PORT
pio device monitor -e beam-break --port YOUR_PORT
```

Use the same environment for building, uploading and monitoring. Close the serial
monitor before uploading. Linux ports commonly look like `/dev/ttyUSB0`; Windows
ports like `COM3`. PlatformIO's VS Code extension can also open this project.
First build downloads the pinned ESP32 platform and toolchain. HX711 is fetched
from the registry; no missing bundled library is assumed.

## Project layout

- `include/pins.h`: shared original-HUZZAH32 GPIO assignments.
- `firmware/dispenser`: motor-disabled integration scaffold.
- `firmware/component-tests`: standalone sensor and motor programs.
- `docs/source-programs`: verbatim text extracted from the three supplied Word documents.
- [Hardware and wiring](docs/hardware.md): board and driver differences to check first.
- [Component test procedures](docs/component-tests.md): commands and pass criteria.
- [Team workflow](CONTRIBUTING.md): branches and pull requests.

The supplied motor and load-cell text each lacked the final closing brace;
working copies repair those endings. The load-cell working copy uses the pinned
HX711 dependency. Board-specific pins now come from the shared header.

## Scope and verification

Builds check compilation, not wiring or dispensing accuracy. Hardware tests must
be recorded by the team. RTC, TFT, potentiometer and scheduling are not implemented.
Reserve their pins only after checking the shared map; the current motor button
uses GPIO19, which can conflict with SPI display wiring. PlatformIO currently pins
Arduino-ESP32 2.x through espressif32 6.9.0; the source motor comments referred to
3.x, so this is a deliberately reproducible toolchain choice, not a claim of
matching the original development environment.

BOM reference: https://docs.google.com/spreadsheets/d/1BoI9oJ1YArM_2erMtDLeQ5Mq1EgGvAHdgItUuWvoSn4/edit
