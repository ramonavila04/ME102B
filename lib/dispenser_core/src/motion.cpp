#include "motion.h"

#include <math.h>

#include "dc_config.h"

namespace dc {

void TrapezoidProfile::plan(float distance, float vmax, float accelMs) {
  sign_ = distance < 0 ? -1.0f : 1.0f;
  dist_ = fabsf(distance);
  if (dist_ <= 0.0f || vmax <= 0.0f) {
    vpeak_ = ta_ = total_ = a_ = 0.0f;
    return;
  }
  const float ta = accelMs < 1.0f ? 1.0f : accelMs;
  a_ = vmax / ta;
  if (dist_ >= vmax * ta) {  // accel + decel together cover vmax * ta
    vpeak_ = vmax;
    ta_ = ta;
    total_ = dist_ / vmax + ta;
  } else {                   // too short to reach vmax: triangle
    vpeak_ = sqrtf(dist_ * a_);
    ta_ = vpeak_ / a_;
    total_ = 2.0f * ta_;
  }
}

float TrapezoidProfile::position(float t) const {
  if (t <= 0.0f || total_ <= 0.0f) return 0.0f;
  float p;
  if (t >= total_) {
    p = dist_;
  } else if (t < ta_) {
    p = 0.5f * a_ * t * t;
  } else if (t < total_ - ta_) {
    p = 0.5f * a_ * ta_ * ta_ + vpeak_ * (t - ta_);
  } else {
    const float r = total_ - t;
    p = dist_ - 0.5f * a_ * r * r;
  }
  return sign_ * p;
}

float TrapezoidProfile::velocity(float t) const {
  if (t <= 0.0f || t >= total_) return 0.0f;
  float v;
  if (t < ta_) {
    v = a_ * t;
  } else if (t < total_ - ta_) {
    v = vpeak_;
  } else {
    v = a_ * (total_ - t);
  }
  return sign_ * v;
}

bool StallDetector::update(uint32_t nowMs, bool armed, float speedAlongMotion) {
  if (stalled_) return true;
  if (!armed || speedAlongMotion >= threshold_) {
    timing_ = false;
    return false;
  }
  if (!timing_) {
    timing_ = true;
    since_ = nowMs;
  }
  if (nowMs - since_ >= stallMs_) stalled_ = true;
  return stalled_;
}

void MoveController::start(uint32_t nowMs, int32_t from, int32_t to, float vmaxCpms,
                           float accelMs, float jamSpeedFrac, uint32_t jamStallMs) {
  if (gains_.kff == 0.0f) {
    gains_.kff = 1.0f / rpmToCountsPerMs(kNoLoadRpm);
    gains_.kp = cfg::kKp;
    gains_.kv = cfg::kKv;
    gains_.ki = cfg::kKi;
  }
  from_ = from;
  target_ = to;
  startMs_ = endMs_ = nowMs;
  prof_.plan(static_cast<float>(to - from), vmaxCpms, accelMs);
  armSpeed_ = jamSpeedFrac * vmaxCpms;
  stall_.configure(armSpeed_, jamStallMs);
  refVel_ = 0.0f;
  integ_ = 0.0f;
  lastMs_ = nowMs;
  active_ = true;
  result_ = MoveResult::Running;
}

float MoveController::update(uint32_t nowMs, int32_t pos, float vel) {
  if (!active_) return 0.0f;
  const float t = static_cast<float>(nowMs - startMs_);
  const float T = prof_.durationMs();
  const float dir = prof_.distance() < 0 ? -1.0f : 1.0f;
  refVel_ = prof_.velocity(t);
  const float ref = static_cast<float>(from_) + prof_.position(t);
  const float finalErr = static_cast<float>(target_ - pos);

  auto finish = [&](MoveResult r) {
    active_ = false;
    result_ = r;
    endMs_ = nowMs;
    return 0.0f;
  };

  if (static_cast<float>(pos - from_) * dir < -cfg::kWrongDirDeg * kCountsPerDeg)
    return finish(MoveResult::WrongDirection);

  const bool armed = t < T && fabsf(refVel_) >= armSpeed_;
  if (stall_.update(nowMs, armed, vel * dir)) return finish(MoveResult::Stalled);

  if (t >= T && fabsf(finalErr) <= cfg::kPosTolDeg * kCountsPerDeg)
    return finish(MoveResult::Done);
  if (t >= T + static_cast<float>(cfg::kMoveExtraMs))
    return finish(fabsf(finalErr) <= cfg::kFinalTolDeg * kCountsPerDeg ? MoveResult::Done
                                                                       : MoveResult::PositionError);

  const float err = ref - static_cast<float>(pos);
  if (gains_.ki > 0.0f) {
    integ_ += err * static_cast<float>(nowMs - lastMs_);
    const float lim = cfg::kIntegralMaxDuty / gains_.ki;
    if (integ_ > lim) integ_ = lim;
    if (integ_ < -lim) integ_ = -lim;
  }
  lastMs_ = nowMs;
  float u = gains_.ki * integ_ + gains_.kff * refVel_ + gains_.kp * err + gains_.kv * (refVel_ - vel);
  if (u > 1.0f) u = 1.0f;
  if (u < -1.0f) u = -1.0f;
  return u;
}

}  // namespace dc
