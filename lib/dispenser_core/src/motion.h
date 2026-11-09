// Trapezoidal motion profile, stall detector and closed-loop move controller.
// Units: encoder counts, milliseconds, counts/ms. Duty is -1..1 (sign = direction).
#pragma once
#include <stdint.h>

namespace dc {

// Symmetric trapezoid (or triangle for short moves) from 0 to `distance`.
class TrapezoidProfile {
 public:
  void plan(float distance, float vmax, float accelMs);
  float position(float tMs) const;
  float velocity(float tMs) const;
  float durationMs() const { return total_; }
  float distance() const { return sign_ * dist_; }
  float peakVelocity() const { return sign_ * vpeak_; }

 private:
  float dist_ = 0, sign_ = 1, vpeak_ = 0, ta_ = 0, total_ = 0, a_ = 0;
};

// Jam detector: speed in the commanded direction below `threshold` for
// `stallMs` continuously. Only counts while armed (reference speed high
// enough that the motor is supposed to be moving).
class StallDetector {
 public:
  void configure(float thresholdCpms, uint32_t stallMs) {
    threshold_ = thresholdCpms;
    stallMs_ = stallMs;
    reset();
  }
  void reset() { timing_ = false; stalled_ = false; }
  // Returns true once stalled (latched until reset()).
  bool update(uint32_t nowMs, bool armed, float speedAlongMotion);
  bool stalled() const { return stalled_; }

 private:
  float threshold_ = 0;
  uint32_t stallMs_ = 0, since_ = 0;
  bool timing_ = false, stalled_ = false;
};

enum class MoveResult : uint8_t { None, Running, Done, Stalled, WrongDirection, PositionError };

// Follows a trapezoid with feed-forward + position/velocity feedback.
class MoveController {
 public:
  struct Gains {
    float kff;  // duty per count/ms (1 / no-load speed)
    float kp;   // duty per count
    float kv;   // duty per count/ms
  };
  void start(uint32_t nowMs, int32_t from, int32_t to, float vmaxCpms, float accelMs,
             float jamSpeedFrac, uint32_t jamStallMs);
  // Call every control period. Returns duty and updates result().
  float update(uint32_t nowMs, int32_t pos, float vel);
  void abort() { active_ = false; }
  bool active() const { return active_; }
  MoveResult result() const { return result_; }
  int32_t target() const { return target_; }
  uint32_t startMs() const { return startMs_; }
  uint32_t elapsedMs() const { return endMs_ - startMs_; }  // valid once finished
  float plannedMs() const { return prof_.durationMs(); }
  float refVelocity() const { return refVel_; }
  void setGains(const Gains& g) { gains_ = g; }

 private:
  TrapezoidProfile prof_;
  StallDetector stall_;
  Gains gains_{};
  bool active_ = false;
  MoveResult result_ = MoveResult::None;
  int32_t from_ = 0, target_ = 0;
  uint32_t startMs_ = 0, endMs_ = 0;
  float refVel_ = 0, armSpeed_ = 0;
};

}  // namespace dc
