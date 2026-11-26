#include "bank.h"

namespace mb {

using dc::degToCounts;
using dc::MoveResult;
using dc::rpmToCountsPerMs;
namespace cfg = dc::cfg;

static int32_t absI(int32_t v) { return v < 0 ? -v : v; }

const char* outcomeName(Outcome o) {
  switch (o) {
    case Outcome::None: return "NONE";
    case Outcome::Ok: return "OK";
    case Outcome::Double: return "DOUBLE";
    case Outcome::Miss: return "MISS";
    case Outcome::Jam: return "JAM";
    case Outcome::EncoderDirection: return "ENCODER DIRECTION";
    case Outcome::HomeNotFound: return "HOME NOT FOUND";
    case Outcome::BeamBlocked: return "BEAM BLOCKED";
    case Outcome::HomingDrop: return "HOMING DROP";
    case Outcome::NotHomed: return "NOT HOMED";
    case Outcome::Busy: return "BUSY";
    case Outcome::BadModule: return "BAD MODULE";
    case Outcome::Aborted: return "ABORTED";
    case Outcome::Homed: return "HOMED";
  }
  return "?";
}

const char* bankStateName(BankState s) {
  switch (s) {
    case BankState::Idle: return "IDLE";
    case BankState::Selecting: return "SELECTING";
    case BankState::Homing: return "HOMING";
    case BankState::Dispensing: return "DISPENSING";
    case BankState::Fault: return "FAULT";
  }
  return "?";
}

void ModuleBank::setState(BankState s) {
  if (s != state_) ++stateSeq_;
  state_ = s;
}

Outcome ModuleBank::command(Command c, int module, const Inputs& in) {
  if (module < 0 || module >= kModules) return Outcome::BadModule;
  if (state_ != BankState::Idle) return Outcome::Busy;
  if (c == Command::Dispense && !(homedMask_ & (1u << module))) return Outcome::NotHomed;
  pending_ = c;
  select(module, in);
  return Outcome::None;
}

void ModuleBank::select(int module, const Inputs& in) {
  if (module_ >= 0) pos_[module_] = modPos(in);  // remember where the old module stopped
  module_ = module;
  selectMs_ = in.nowMs;
  move_.abort();
  braking_ = false;
  duty_ = 0.0f;
  setState(BankState::Selecting);
}

void ModuleBank::abort(const Inputs& in) {
  if (state_ == BankState::Idle || state_ == BankState::Fault) return;
  move_.abort();
  startBrake(in.nowMs);
  finish(Outcome::Aborted, in);
}

void ModuleBank::clearFault() {
  if (state_ == BankState::Fault) {
    fault_ = Outcome::None;
    setState(BankState::Idle);
  }
}

void ModuleBank::startMove(const Inputs& in, int32_t target, float rpm) {
  braking_ = false;
  duty_ = 0.0f;
  move_.start(in.nowMs, modPos(in), target, rpmToCountsPerMs(rpm), static_cast<float>(MECH_ACCEL_MS),
              MECH_JAM_MIN_SPEED_FRAC, MECH_JAM_STALL_MS);
}

void ModuleBank::startBrake(uint32_t now) {
  braking_ = true;
  brakeStartMs_ = now;
  duty_ = 0.0f;
}

bool ModuleBank::brakeDone(uint32_t now) const { return !braking_ || now - brakeStartMs_ >= cfg::kBrakeMs; }

void ModuleBank::finish(Outcome o, const Inputs& in) {
  result_.module = static_cast<uint8_t>(module_ < 0 ? 0 : module_);
  result_.outcome = o;
  result_.beams = static_cast<uint8_t>(in.beamEvents - beamStart_ > 255 ? 255 : in.beamEvents - beamStart_);
  result_.steps = steps_;
  result_.jams = jams_;
  ++resultSeq_;
  const bool fault = o == Outcome::Jam || o == Outcome::EncoderDirection || o == Outcome::HomeNotFound ||
                     o == Outcome::HomingDrop || o == Outcome::BeamBlocked;
  if (fault) {
    fault_ = o;
    if (module_ >= 0 && o != Outcome::BeamBlocked) homedMask_ &= static_cast<uint8_t>(~(1u << module_));
    setState(BankState::Fault);
  } else {
    setState(BankState::Idle);
  }
}

void ModuleBank::startStep(const Inputs& in) {
  ++steps_;
  jamRetries_ = 0;  // MECH_MAX_RETRIES applies to each index move
  target_ = index_[module_] + degToCounts(MECH_INDEX_DEG);
  startForward(in);
}

void ModuleBank::startForward(const Inputs& in) {
  fwdStartMs_ = in.nowMs;
  phase_ = Phase::Forward;
  startMove(in, target_, MECH_TARGET_RPM);
}

Outputs ModuleBank::update(const Inputs& in) {
  const uint32_t now = in.nowMs;
  Outputs out;

  if (state_ == BankState::Selecting) {
    out.selected = static_cast<int8_t>(module_);
    if (now - selectMs_ < kSelectSettleMs) return out;  // multiplexer and counter settling
    // The selected module has not moved since it was last deselected (the gearboxes do
    // not back-drive), so its position continues from pos_.
    base_ = in.encoder - pos_[module_];
    lastPos_ = modPos(in);
    lastCtrlMs_ = now;
    vel_ = 0.0f;
    const bool home = (in.homeMask >> module_) & 1u;
    homeDeb_.reset(home, now);
    beamStart_ = in.beamEvents;
    steps_ = jams_ = rocks_ = 0;
    if (pending_ == Command::Home) {
      setState(BankState::Homing);
      seenRelease_ = !home;
      phase_ = Phase::Seek;
      startMove(in, modPos(in) + degToCounts(cfg::kHomeMaxDeg), cfg::kHomeRpm);
    } else {
      setState(BankState::Dispensing);
      if (in.beamBlocked) {
        finish(Outcome::BeamBlocked, in);
        return out;
      }
      startStep(in);
    }
  }

  if (module_ >= 0) {
    homeDeb_.update(now, (in.homeMask >> module_) & 1u);
    // Speed estimate and closed-loop control at a fixed period.
    if (now - lastCtrlMs_ >= cfg::kControlPeriodMs) {
      const int32_t p = modPos(in);
      const float dt = static_cast<float>(now - lastCtrlMs_);
      vel_ += cfg::kVelFilterAlpha * (static_cast<float>(p - lastPos_) / dt - vel_);
      lastPos_ = p;
      lastCtrlMs_ = now;
      if (move_.active()) {
        duty_ = move_.update(now, p, vel_);
        if (!move_.active()) startBrake(now);
      }
    }
    if (state_ == BankState::Homing) handleHoming(in);
    else if (state_ == BankState::Dispensing) handleDispensing(in);
  }

  out.selected = static_cast<int8_t>(module_);
  const bool moving = move_.active();
  const bool braking = braking_ && now - brakeStartMs_ < cfg::kBrakeMs;
  out.motorEnable = moving || braking;
  out.brake = !moving && braking;
  out.duty = moving ? duty_ : 0.0f;
  if (module_ >= 0) pos_[module_] = modPos(in);
  return out;
}

void ModuleBank::handleHoming(const Inputs& in) {
  const uint32_t now = in.nowMs;
  const bool home = homeDeb_.stable();
  switch (phase_) {
    case Phase::Seek:
      if (!move_.active()) {
        const MoveResult r = move_.result();
        if (r == MoveResult::WrongDirection) finish(Outcome::EncoderDirection, in);
        else if (r == MoveResult::Stalled || r == MoveResult::PositionError) finish(Outcome::Jam, in);
        else finish(Outcome::HomeNotFound, in);
        return;
      }
      if (!seenRelease_) {
        if (!home) seenRelease_ = true;  // started on the switch: leave it first
      } else if (home) {
        homeEdge_ = modPos(in);
        move_.abort();
        startBrake(now);
        phase_ = Phase::SeekBrake;
      }
      break;
    case Phase::SeekBrake:
      if (!brakeDone(now)) break;
      homeTarget_ = homeEdge_ + degToCounts(MECH_HOME_OFFSET_DEG);
      if (absI(homeTarget_ - modPos(in)) > degToCounts(cfg::kPosTolDeg)) {
        startMove(in, homeTarget_, cfg::kHomeRpm);
        phase_ = Phase::Offset;
      } else {
        index_[module_] = homeTarget_;
        homedMask_ |= static_cast<uint8_t>(1u << module_);
        finish(in.beamEvents != beamStart_ ? Outcome::HomingDrop : Outcome::Homed, in);
      }
      break;
    case Phase::Offset:
      if (move_.active() || !brakeDone(now)) break;
      if (move_.result() == MoveResult::Done) {
        index_[module_] = homeTarget_;
        homedMask_ |= static_cast<uint8_t>(1u << module_);
        finish(in.beamEvents != beamStart_ ? Outcome::HomingDrop : Outcome::Homed, in);
      } else if (move_.result() == MoveResult::WrongDirection) {
        finish(Outcome::EncoderDirection, in);
      } else {
        finish(Outcome::Jam, in);
      }
      break;
    default:
      break;
  }
}

void ModuleBank::handleDispensing(const Inputs& in) {
  const uint32_t now = in.nowMs;
  switch (phase_) {
    case Phase::Forward:
      if (move_.active()) break;
      switch (move_.result()) {
        case MoveResult::Done:
          index_[module_] = target_;
          moveDoneMs_ = now;
          phase_ = Phase::Settle;
          break;
        case MoveResult::WrongDirection:
          finish(Outcome::EncoderDirection, in);
          return;
        default:  // Stalled or PositionError
          ++jams_;
          phase_ = Phase::JamBrake;
          break;
      }
      break;
    case Phase::JamBrake:
      if (!brakeDone(now)) break;
      if (jamRetries_ >= MECH_MAX_RETRIES) {
        finish(Outcome::Jam, in);
        return;
      }
      ++jamRetries_;
      startMove(in, modPos(in) - degToCounts(MECH_REVERSE_DEG), MECH_TARGET_RPM);
      phase_ = Phase::Reverse;
      break;
    case Phase::Reverse:
      if (move_.active()) break;
      if (move_.result() == MoveResult::Done) phase_ = Phase::ReverseBrake;
      else if (move_.result() == MoveResult::WrongDirection) finish(Outcome::EncoderDirection, in);
      else finish(Outcome::Jam, in);  // cannot back off either
      break;
    case Phase::ReverseBrake:
      if (brakeDone(now)) startForward(in);  // retry to the same absolute target
      break;
    case Phase::Settle:
      if (!brakeDone(now) || now - moveDoneMs_ < MECH_SETTLE_MS) break;
      if (in.beamEvents != beamStart_) {
        phase_ = Phase::DropWait;  // keep counting so a trailing second pill reads as DOUBLE
      } else if (steps_ < MECH_MAX_INDEX_STEPS) {
        if (MECH_ROCK_AFTER > 0 && steps_ % MECH_ROCK_AFTER == 0) {
          // empty for MECH_ROCK_AFTER pockets: back off one pitch and return, so a tablet
          // standing on edge in the pool is dragged the other way and falls flat
          ++rocks_;
          startMove(in, index_[module_] - degToCounts(MECH_INDEX_DEG), MECH_TARGET_RPM);
          phase_ = Phase::RockBack;
        } else {
          startStep(in);
        }
      } else {
        finish(Outcome::Miss, in);
      }
      break;
    case Phase::RockBack:
    case Phase::RockReturn:
      if (move_.active() || !brakeDone(now)) break;
      if (move_.result() == MoveResult::WrongDirection) {
        finish(Outcome::EncoderDirection, in);
        return;
      }
      if (move_.result() != MoveResult::Done) {  // a stall while rocking: no retries
        ++jams_;
        finish(Outcome::Jam, in);
        return;
      }
      if (phase_ == Phase::RockBack) {
        fwdStartMs_ = now;
        startMove(in, index_[module_], MECH_TARGET_RPM);  // back to the same pocket
        phase_ = Phase::RockReturn;
      } else {
        moveDoneMs_ = now;
        phase_ = Phase::RockSettle;
      }
      break;
    case Phase::RockSettle:
      if (now - moveDoneMs_ < MECH_SETTLE_MS) break;
      if (in.beamEvents != beamStart_) phase_ = Phase::DropWait;  // a pill fell during the rock
      else startStep(in);
      break;
    case Phase::DropWait:
      if (now - fwdStartMs_ >= MECH_DROP_WINDOW_MS) {
        finish(in.beamEvents - beamStart_ >= 2 ? Outcome::Double : Outcome::Ok, in);
      }
      break;
    default:
      break;
  }
}

}  // namespace mb
