// Simulated dispenser hardware for host tests: gearmotor + encoder, home
// switch, pill drops through the beam, HX711 load cell, buttons and RTC.
// Header-only; included by test/test_*/ programs.
#pragma once
#include <math.h>
#include <stdint.h>

#include <vector>

#include "dc_config.h"
#include "dispenser.h"
#include "mechanism.h"
#include "sim_motor.h"

namespace simt {

// ---- Expectations derived ONLY from include/mechanism.h and dc_config.h, so
// the same tests hold for every generated pill block (-DMECH_PILL_*).
namespace expect {
constexpr uint32_t kScalePeriodMs = 100;  // simulated HX711 at 10 SPS
// Nominal pill mass: the generator sets MECH_PILL_MASS_G_MIN = 0.8 x nominal.
constexpr float pillGrams() { return MECH_PILL_MASS_G_MIN / 0.8f; }
// Trapezoid: distance / cruise speed + one ramp time (deg/s = 6 * rpm).
inline float moveMs(float deg) {
  return deg / (6.0f * MECH_TARGET_RPM) * 1000.0f + static_cast<float>(MECH_ACCEL_MS);
}
inline float indexMoveMs() { return moveMs(MECH_INDEX_DEG); }
inline float baselineMs() { return dc::cfg::kScaleSamples * kScalePeriodMs; }
inline float verifyMs() { return dc::cfg::kScaleSamples * kScalePeriodMs; }
// Empty step: move, then settle (the post-move brake overlaps the settle).
inline float emptyStepMs() { return indexMoveMs() + MECH_SETTLE_MS; }
// Step that drops a pill: settle, then wait out the drop window from move start.
inline float pillStepMs() {
  const float a = indexMoveMs() + MECH_SETTLE_MS;
  const float b = static_cast<float>(MECH_DROP_WINDOW_MS);
  return a > b ? a : b;
}
// Dispense command -> VERIFY done, pill found on step `n`.
inline float dispenseMs(int n) {
  return baselineMs() + (n - 1) * emptyStepMs() + pillStepMs() + verifyMs();
}
inline float missMs() { return baselineMs() + MECH_MAX_INDEX_STEPS * emptyStepMs() + verifyMs(); }
// Generous run limit for runUntil(): 2x the expectation plus 2 s.
inline uint32_t limit(float ms) { return static_cast<uint32_t>(2.0f * ms + 2000.0f); }
}  // namespace expect


struct PillEvent {
  uint32_t beamAtMs;   // block start
  uint32_t landAtMs;   // mass appears on the scale
};

class Plant {
 public:
  dc::SimMotor motor;
  dc::Dispenser disp;
  dc::Inputs in;
  dc::Outputs out;

  // Geometry (counts). The home switch is actuated over a 6 deg window.
  int32_t homeAt = dc::degToCounts(61.0f);
  int32_t homeWidth = dc::degToCounts(6.0f);
  // A pocket releases its pill when the drum passes 60 % of the index move
  // after the pocket was loaded; pocket k is loaded at homeAt + k * index.
  std::vector<int> pillsPerPocket;  // pills released by pocket 0,1,2,... (default 1)
  int nextPocket = 0;
  double nextDropPos = 0;

  // Jam injection: forward motion is blocked at jamAtPos until the motor has
  // reversed `clearAfterReverses` times (-1 = never clears).
  bool jamArmed = false;
  double jamAtPos = 0;
  int clearAfterReverses = 1;
  int reversesSeen = 0;
  bool jamHit = false;
  bool wasReversing = false;

  int encoderSign = 1;   // -1 simulates swapped encoder channels
  float cupGrams = 5.0f;  // empty cup on the cell (tare is not needed: deltas are used)
  float pillGrams = expect::pillGrams();
  bool scaleCalibrated = true;
  uint32_t nowMs = 0;
  uint32_t nextScaleMs = expect::kScalePeriodMs;
  std::vector<PillEvent> pending;
  std::vector<uint32_t> beamBlockStarts;  // for timing checks
  uint32_t beamCount = 0;
  uint32_t clockBase = 0;  // unix at nowMs = 0

  void begin(const dc::Schedule& s = dc::Schedule(), uint32_t lastDose = 0) {
    nextDropPos = homeAt + 0.6 * dc::degToCounts(MECH_INDEX_DEG);
    disp.begin(s, lastDose);
  }

  bool homeSwitch() const {
    const double rev = dc::kCountsPerRev;
    double p = fmod(motor.pos, rev);
    if (p < 0) p += rev;
    return p >= homeAt && p < homeAt + homeWidth;
  }

  void step() {
    // --- sensors -> inputs
    in.nowMs = nowMs;
    in.encoder = encoderSign * motor.count();
    in.homeRaw = homeSwitch();
    bool blocked = false;
    for (const auto& e : pending)
      if (nowMs >= e.beamAtMs && nowMs < e.beamAtMs + 6) blocked = true;
    if (blocked && !in.beamBlocked) {
      ++beamCount;
      beamBlockStarts.push_back(nowMs);
    }
    in.beamBlocked = blocked;
    in.beamEvents = beamCount;
    for (auto it = pending.begin(); it != pending.end();) {
      if (nowMs >= it->landAtMs) {
        cupGrams += pillGrams;
        it = pending.erase(it);
      } else {
        ++it;
      }
    }
    if (nowMs >= nextScaleMs) {  // HX711 at 10 SPS with small noise
      nextScaleMs += expect::kScalePeriodMs;
      ++in.scaleSeq;
      // Noise of +/- 5 % of the smallest pill mass.
      in.scaleGrams = cupGrams + 0.025f * MECH_PILL_MASS_G_MIN *
                                     (static_cast<float>((in.scaleSeq * 7919u) % 5u) - 2.0f);
      in.scaleOk = scaleCalibrated;
    }
    in.clockValid = clockBase != 0;
    in.unixLocal = clockBase + nowMs / 1000;

    // --- controller
    out = disp.update(in);
    in.requestDispense = false;
    in.requestAck = false;

    // --- plant dynamics (1 ms)
    const bool reversing = out.motorEnable && !out.brake && out.duty < -0.05f;
    if (jamArmed && motor.pos >= jamAtPos - 1) jamHit = true;
    if (reversing && !wasReversing && jamHit) ++reversesSeen;  // only back-offs after hitting the jam
    wasReversing = reversing;
    if (jamArmed && clearAfterReverses >= 0 && reversesSeen >= clearAfterReverses) jamArmed = false;
    const bool forwardDrive = out.motorEnable && !out.brake && out.duty > 0;
    motor.load = (jamArmed && forwardDrive && motor.pos >= jamAtPos) ? 3.0f : 0.0f;
    motor.step(1.0f, out.duty, out.motorEnable, out.brake);
    if (jamArmed && motor.pos > jamAtPos && motor.vel >= 0) {  // hard stop at the obstruction
      motor.pos = jamAtPos;
      motor.vel = 0;
    }

    // --- pills
    if (motor.pos >= nextDropPos) {
      const int n = nextPocket < static_cast<int>(pillsPerPocket.size()) ? pillsPerPocket[nextPocket] : 1;
      for (int i = 0; i < n; ++i)
        pending.push_back({nowMs + 150 + 40u * i, nowMs + 300 + 40u * i});
      ++nextPocket;
      nextDropPos += dc::degToCounts(MECH_INDEX_DEG);
    }
    ++nowMs;
  }

  // Run until predicate or timeout; returns true if predicate met.
  template <class F>
  bool runUntil(F pred, uint32_t timeoutMs) {
    const uint32_t end = nowMs + timeoutMs;
    while (nowMs < end) {
      step();
      if (pred()) return true;
    }
    return false;
  }
  bool runUntilState(dc::State s, uint32_t timeoutMs) {
    return runUntil([&] { return disp.state() == s; }, timeoutMs);
  }
  void pressSelect() {
    in.selectRaw = true;
    for (int i = 0; i < 60; ++i) step();
    in.selectRaw = false;
    for (int i = 0; i < 60; ++i) step();
  }
};

}  // namespace simt
