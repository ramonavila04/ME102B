#pragma once
#include <stdint.h>

// Edit these six rows after checking the actual cartridge, then upload to USB-C.
// V7 CAD shows 3 uniformly spaced pockets and a 1:1 gearbox-output-to-wheel drive.
// Mark the empty disk, fit it in its intended phase. Only canister 1 is enabled in this kit.
// Physical pockets are 120 degrees apart. The C1 STEP bench test advances 60 degrees.
// If the physical wheel turns backward, correct the motor leads with power off.
// If physical forward is correct but encoder counts have the opposite sign,
// change forwardSign. Check several successive indexes before enabling schedules.
namespace MotorSettings {
struct Cartridge {
  uint8_t pocketsPerTurn;
  double gearboxOutputTurnsPerWheelTurn;  // 1.0 for the directly coupled V7 disk
  int8_t forwardSign;                     // +1 if raw counts rise when moving forward
  bool enabled;
};
constexpr Cartridge CARTRIDGES[6] = {
  // Pockets  Gear ratio  Sign   Enabled for bench test / service
  {3,         1.0,        -1,    true },  // canister 1
  {3,         1.0,        -1,    false},  // canister 2
  {3,         1.0,        -1,    false},  // canister 3
  {3,         1.0,        -1,    false},  // canister 4
  {3,         1.0,        -1,    false},  // canister 5
  {3,         1.0,        -1,    false},  // canister 6
};

// A job ends on measured angle. This time is an upper limit for a stalled/slow job.
constexpr uint32_t MAX_JOB_MS = 60000;
constexpr uint32_t NO_PROGRESS_MS = 750;
constexpr uint32_t STOP_SETTLE_MS = 150;      // minimum time after removing drive before reporting done
// Canister 1 has local encoder feedback. Change the wheel speeds here.
constexpr uint8_t C1_CRUISE_DEG_PER_SEC = 18;    // STEP, JOG15, dispensing and SPIN
constexpr uint8_t C1_APPROACH_DEG_PER_SEC = 5;
constexpr uint8_t C1_APPROACH_DEGREES = 3;       // final part of each finite move
constexpr uint8_t C1_MAX_DUTY = 4;               // at most 4/8 (50%) while catching up
// EDGE compares encoder travel with the commanded creep speed over each measurement window.
constexpr uint16_t EDGE_STARTUP_MS = 100;
constexpr uint16_t EDGE_WINDOW_MS = 200;
constexpr uint8_t EDGE_MIN_SPEED_PERCENT = 45;     // 0.45 degrees per 200 ms at 5 degrees/s
constexpr double EDGE_PROVE_MOTION_DEGREES = 0.5; // verify feedback before allowing a reverse stroke
static_assert(EDGE_WINDOW_MS > 0 && EDGE_STARTUP_MS + 2 * EDGE_WINDOW_MS < NO_PROGRESS_MS &&
              EDGE_MIN_SPEED_PERCENT > 0 && EDGE_MIN_SPEED_PERCENT < 100, "Review EDGE slowdown detection");
// Canister 1 rocking strokes, shared by ROCK, STEPROCK and scale-guided jam clearing.
constexpr uint8_t ROCK_CRUISE_DEG_PER_SEC = 144; // target wheel speed (24 rpm) through the middle of each stroke
constexpr uint8_t ROCK_MAX_DUTY = 6;             // 6/8 (75%) while catching up to the rocking target
constexpr uint16_t ROCK_NO_PROGRESS_MS = 250;    // release a wedged wheel promptly during either stroke
constexpr uint8_t ROCK_APPROACH_DEG_PER_SEC = 20;
constexpr uint8_t ROCK_APPROACH_DEGREES = 3;
constexpr uint8_t BENCH_ROCK_APPROACH_DEGREES = 5; // slow earlier on the long half-turn bench sweep
// ROCK2 ramps toward the #5229's nominal unloaded 12 V speed (35 rpm), then uses full drive.
constexpr uint8_t ROCK2_RAMP_TARGET_DEG_PER_SEC = 210;
constexpr uint8_t ROCK2_APPROACH_DEGREES = 7;     // brake earlier from full speed
constexpr double ROCK_TOLERANCE_DEGREES = 0.75;
constexpr uint16_t ROCK_RAMP_MS = 30;        // linear increase from approach to cruise on each leg
static_assert(ROCK_APPROACH_DEG_PER_SEC > 0 && ROCK_APPROACH_DEG_PER_SEC <= ROCK_CRUISE_DEG_PER_SEC &&
              ROCK_RAMP_MS > 0 && ROCK_APPROACH_DEGREES > 0 && ROCK_MAX_DUTY >= 1 && ROCK_MAX_DUTY <= 8 &&
              ROCK_NO_PROGRESS_MS > ROCK_RAMP_MS && ROCK_NO_PROGRESS_MS <= NO_PROGRESS_MS,
              "Review the rock speed settings");
static_assert(C1_APPROACH_DEG_PER_SEC > 0 && C1_APPROACH_DEG_PER_SEC <= C1_CRUISE_DEG_PER_SEC &&
              C1_APPROACH_DEGREES > 0 && C1_APPROACH_DEGREES < 15 &&
              C1_MAX_DUTY >= 1 && C1_MAX_DUTY <= 8, "Review the canister 1 speed settings");
constexpr uint8_t RUN_DUTY = 8;               // motors 2–6, eighths of full voltage
constexpr uint8_t APPROACH_DUTY = 5;          // motors 2–6, last quarter of a pocket
constexpr double MAX_OVERSHOOT_POCKETS = 0.15; // larger position error requires an inspection
constexpr uint8_t NUDGE_DUTY = 4;              // 4/8 (50%) for short, weighed dispensing moves
constexpr double NUDGE_TOLERANCE_DEGREES = 2;  // encoder error allowed at intermediate stops
static_assert(NUDGE_DUTY >= 1 && NUDGE_DUTY <= 8, "Invalid dispense nudge duty");
static_assert(RUN_DUTY >= 1 && RUN_DUTY <= 8 && APPROACH_DUTY >= 1 && APPROACH_DUTY <= RUN_DUTY,
              "Set duty in eighths from 1 to 8");
static_assert(STOP_SETTLE_MS >= 40 && NO_PROGRESS_MS > 40 && MAX_JOB_MS > NO_PROGRESS_MS + STOP_SETTLE_MS,
              "Review the motion timing limits");
static_assert(MAX_OVERSHOOT_POCKETS > 0 && MAX_OVERSHOOT_POCKETS < 0.5, "Review the overtravel limit");
}
