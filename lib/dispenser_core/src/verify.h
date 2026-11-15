// Pill-count verification from beam-break events and load-cell delta.
#pragma once
#include <stdint.h>

namespace dc {

enum class Verdict : uint8_t {
  Ok,            // 1 beam event and the cup gained >= min pill mass
  OkBeamOnly,    // 1 beam event; load cell unavailable/uncalibrated
  Miss,          // 0 beam events and no mass gain (empty pocket)
  Double,        // 2+ beam events: do not let the user take both
  SensorMismatch // beam and load cell disagree: stop and let a person check
};

// beamEvents: block events counted from move start to verification.
// massValid: baseline and after-drop averages both valid and scale calibrated.
inline Verdict classifyDispense(uint32_t beamEvents, bool massValid, float massDeltaG,
                                float minPillMassG) {
  if (beamEvents >= 2) return Verdict::Double;
  const bool massGain = massValid && massDeltaG >= minPillMassG;
  if (beamEvents == 1) {
    if (!massValid) return Verdict::OkBeamOnly;
    return massGain ? Verdict::Ok : Verdict::SensorMismatch;
  }
  // No beam event: a mass gain means the beam missed a pill (sensor fault).
  return massGain ? Verdict::SensorMismatch : Verdict::Miss;
}

inline const char* verdictName(Verdict v) {
  switch (v) {
    case Verdict::Ok: return "OK";
    case Verdict::OkBeamOnly: return "OK (beam only)";
    case Verdict::Miss: return "MISS";
    case Verdict::Double: return "DOUBLE";
    case Verdict::SensorMismatch: return "SENSOR MISMATCH";
  }
  return "?";
}

}  // namespace dc
