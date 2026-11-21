// Motion board logic for six V2 modules that move one at a time (V8 housing).
//
// Hardware model (see docs/electronics_v8.md): each module has a gearmotor on a TB6612
// channel, a quadrature encoder, a home switch and an IR beam-break across its exit
// duct. Only the selected module's motor is driven (its direction lines are set, all
// others are left in TB6612 "stop"); its encoder is routed to the one counter through
// a multiplexer; the six beam receivers share one wired-OR line. So:
//   - Inputs.encoder is the count of whichever module is selected (it changes meaning when
//     the selection changes; the bank keeps each module's absolute position itself);
//   - Inputs.beamEvents counts blocks on the shared line (only the moving module can drop
//     a pill, so every event belongs to it).
//
// Per module the logic is the single-module firmware's (lib/dispenser_core/dispenser.cpp):
// homing seeks the home-switch press edge forward and moves MECH_HOME_OFFSET_DEG past it;
// a dispense indexes one pocket (MECH_INDEX_DEG) at a time, settles MECH_SETTLE_MS counting
// beam edges, stops once a pill is seen and waits out MECH_DROP_WINDOW_MS to catch a
// double; a stall brakes, reverses MECH_REVERSE_DEG and retries up to MECH_MAX_RETRIES.
// Weighing, the schedule and the UI stay on the main board.
#pragma once
#include <stdint.h>

#include "dc_config.h"
#include "mechanism.h"
#include "menu.h"
#include "motion.h"

namespace mb {

constexpr int kModules = 6;
constexpr uint32_t kSelectSettleMs = 3;  // after switching the encoder multiplexer

enum class BankState : uint8_t { Idle, Selecting, Homing, Dispensing, Fault };
enum class Outcome : uint8_t {
  None = 0,
  Ok = 1,                // exactly one pill seen
  Double = 2,            // two or more pills seen
  Miss = 3,              // no pill after MECH_MAX_INDEX_STEPS pockets (refill)
  Jam = 4,               // stalled more than MECH_MAX_RETRIES times, or could not back off
  EncoderDirection = 5,  // encoder counts against the commanded direction
  HomeNotFound = 6,      // home switch not seen within kHomeMaxDeg
  BeamBlocked = 7,       // beam already blocked before a dispense
  HomingDrop = 8,        // a pill fell while homing
  NotHomed = 9,          // dispense asked of a module not homed since power-up
  Busy = 10,             // command refused: another one is running
  BadModule = 11,        // module number out of range
  Aborted = 12,
  Homed = 13,            // homing finished
};
enum class Command : uint8_t { Home, Dispense };

const char* outcomeName(Outcome o);
const char* bankStateName(BankState s);

struct Inputs {
  uint32_t nowMs = 0;
  int32_t encoder = 0;      // count of the selected module (forward = positive)
  uint32_t beamEvents = 0;  // cumulative block events on the shared beam line
  bool beamBlocked = false;
  uint8_t homeMask = 0;     // bit k = module k's home switch actuated (raw)
};

struct Outputs {
  int8_t selected = -1;     // module whose direction lines and encoder are connected (-1 = none)
  bool motorEnable = false;  // TB6612 STBY (all three drivers)
  float duty = 0.0f;         // -1..1 on the shared PWM, direction on the selected module's lines
  bool brake = false;        // short brake on the selected module
};

struct Result {
  uint8_t module = 0;
  Outcome outcome = Outcome::None;
  uint8_t beams = 0, steps = 0, jams = 0;
};

class ModuleBank {
 public:
  // Start a command. Returns Outcome::None if accepted, else the reason it was refused.
  Outcome command(Command c, int module, const Inputs& in);
  void abort(const Inputs& in);
  void clearFault();
  Outputs update(const Inputs& in);

  BankState state() const { return state_; }
  int active() const { return module_; }
  uint8_t homedMask() const { return homedMask_; }
  Outcome fault() const { return fault_; }
  // The last finished command's result; resultSeq() increments once per result.
  const Result& result() const { return result_; }
  uint32_t resultSeq() const { return resultSeq_; }
  int32_t position(int module) const { return pos_[module]; }  // absolute counts
  uint32_t stateSeq() const { return stateSeq_; }

 private:
  enum class Phase : uint8_t { Seek, SeekBrake, Offset, Forward, JamBrake, Reverse, ReverseBrake, Settle, DropWait };
  int32_t modPos(const Inputs& in) const { return in.encoder - base_; }
  void select(int module, const Inputs& in);
  void startMove(const Inputs& in, int32_t target, float rpm);
  void startBrake(uint32_t now);
  bool brakeDone(uint32_t now) const;
  void startStep(const Inputs& in);
  void startForward(const Inputs& in);
  void finish(Outcome o, const Inputs& in);
  void handleHoming(const Inputs& in);
  void handleDispensing(const Inputs& in);
  void setState(BankState s);

  BankState state_ = BankState::Idle;
  Command pending_ = Command::Home;
  Phase phase_ = Phase::Seek;
  int module_ = -1;
  uint8_t homedMask_ = 0;
  Outcome fault_ = Outcome::None;
  uint32_t selectMs_ = 0;

  int32_t pos_[kModules] = {};    // absolute counts of each module (kept across selections)
  int32_t index_[kModules] = {};  // "pocket under the hopper" position of each module
  int32_t base_ = 0;              // encoder reading that corresponds to position 0 of module_

  dc::MoveController move_;
  dc::Debouncer homeDeb_{dc::cfg::kSwitchDebounceMs};
  bool homeDebInit_ = false;
  int32_t lastPos_ = 0;
  uint32_t lastCtrlMs_ = 0;
  float vel_ = 0.0f, duty_ = 0.0f;
  bool braking_ = false;
  uint32_t brakeStartMs_ = 0;

  bool seenRelease_ = false;
  int32_t homeEdge_ = 0, homeTarget_ = 0;
  int32_t target_ = 0;
  uint32_t fwdStartMs_ = 0, moveDoneMs_ = 0;
  uint8_t jamRetries_ = 0, steps_ = 0, jams_ = 0;
  uint32_t beamStart_ = 0;

  Result result_;
  uint32_t resultSeq_ = 0, stateSeq_ = 0;
};

}  // namespace mb
