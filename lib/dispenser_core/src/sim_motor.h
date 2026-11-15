// First-order DC gearmotor model used by the host simulation tests and by the
// DISPENSER_SIM_MOTOR firmware build (Wokwi). Not used on the real dispenser.
#pragma once
#include <math.h>
#include <stdint.h>

#include "dc_config.h"

namespace dc {

class SimMotor {
 public:
  float noLoadCpms = rpmToCountsPerMs(kNoLoadRpm);  // speed at |duty| = 1, no load
  float tauMs = 40.0f;     // mechanical time constant (assumed)
  float deadband = 0.08f;  // duty needed to overcome static friction (assumed)
  float load = 0.0f;       // load torque as a fraction of stall torque at full duty
  double pos = 0.0;        // counts
  float vel = 0.0f;        // counts/ms

  // Linear torque-speed curve: speed = noLoad * (|duty| - deadband - load) / (1 - deadband).
  // A non-backdrivable 1000:1 gearbox: with no drive, or with load >= drive,
  // the output does not move backwards.
  void step(float dtMs, float duty, bool enabled, bool brake) {
    float target = 0.0f;
    if (enabled && !brake) {
      const float mag = fabsf(duty) - deadband - load;
      if (mag > 0.0f) target = (duty >= 0 ? 1.0f : -1.0f) * noLoadCpms * mag / (1.0f - deadband);
    }
    const float tau = (brake || !enabled) ? tauMs * 0.25f : tauMs;
    float k = dtMs / tau;
    if (k > 1.0f) k = 1.0f;
    vel += (target - vel) * k;
    pos += static_cast<double>(vel) * dtMs;
  }
  int32_t count() const { return static_cast<int32_t>(lround(pos)); }
};

}  // namespace dc
