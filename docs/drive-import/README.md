# Files imported from the team Google Drive

Copied from the "ME 102B PROJECT" Drive folder on 2026-11-08 for reference.

- `potentiometer_code_to_screen.ino`: Caroline's potentiometer → 2.8" TFT
  (ILI9341) test, uploaded 2026-11-08. Its pins conflict with `include/pins.h`:
  the potentiometer uses GPIO32 (`pins.h` MOTOR_ENABLE) and TFT D/C uses GPIO13
  (`pins.h` LED). Resolve this before integrating.
