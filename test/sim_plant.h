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
  bool wasReversing = false;

  int encoderSign = 1;   // -1 simulates swapped encoder channels
  float cupGrams = 5.0f;  // empty cup on the cell (tare is not needed: deltas are used)
  float pillGrams = 0.25f;
  bool scaleCalibrated = true;
  uint32_t nowMs = 0;
  uint32_t nextScaleMs = 100;
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
      nextScaleMs += 100;
      ++in.scaleSeq;
      in.scaleGrams = cupGrams + 0.01f * static_cast<float>((in.scaleSeq * 7919u) % 5u) - 0.02f;
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
    if (reversing && !wasReversing) ++reversesSeen;
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
