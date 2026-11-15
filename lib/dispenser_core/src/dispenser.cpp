#include "dispenser.h"

#include <math.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>

#include "dc_config.h"
#include "mechanism.h"

namespace dc {

namespace {
constexpr int kMenuItems = 7;
const char* const kMenuText[kMenuItems] = {"Dispense now", "Dose 1", "Dose 2", "Dose 3",
                                           "Set clock",    "Re-home", "Exit"};
constexpr int kDoseChoices = 1 + 1440 / cfg::kDoseStepMin;  // OFF + every step of the day

int32_t absI(int32_t v) { return v < 0 ? -v : v; }
}  // namespace

const char* stateName(State s) {
  switch (s) {
    case State::Boot: return "BOOT";
    case State::Homing: return "HOMING";
    case State::Idle: return "IDLE";
    case State::Menu: return "MENU";
    case State::Dispensing: return "DISPENSING";
    case State::Verify: return "VERIFY";
    case State::WaitPickup: return "WAIT_PICKUP";
    case State::Reminder: return "REMINDER";
    case State::Fault: return "FAULT";
  }
  return "?";
}

const char* faultName(FaultCode f) {
  switch (f) {
    case FaultCode::None: return "none";
    case FaultCode::Jam: return "JAM";
    case FaultCode::HomeNotFound: return "HOME NOT FOUND";
    case FaultCode::EncoderDirection: return "ENCODER DIRECTION";
    case FaultCode::Double: return "DOUBLE";
    case FaultCode::Miss: return "MISS / EMPTY";
    case FaultCode::BeamBlocked: return "BEAM BLOCKED";
    case FaultCode::SensorMismatch: return "SENSOR MISMATCH";
    case FaultCode::HomingDrop: return "HOMING DROP";
  }
  return "?";
}

// ---------------------------------------------------------------- Collector
void Dispenser::Collector::add(float g, bool ok) {
  if (!active || n >= cfg::kScaleSamples) return;
  if (!ok) {
    bad = true;
    return;
  }
  sum += g;
  ++n;
}
bool Dispenser::Collector::complete(uint32_t now) const {
  return n >= cfg::kScaleSamples || bad || now - start >= cfg::kScaleTimeoutMs;
}
bool Dispenser::Collector::valid() const { return n >= cfg::kScaleSamples && !bad; }

// ---------------------------------------------------------------- public
void Dispenser::begin(const Schedule& schedule, uint32_t lastDoseUnix) {
  schedule_ = schedule;
  schedule_.sanitize();
  lastDoseUnix_ = lastDoseUnix;
  started_ = false;
}

void Dispenser::setDose(int slot, int16_t minuteOfDay) {
  if (slot < 0 || slot >= kMaxDoses) return;
  schedule_.minuteOfDay[slot] = minuteOfDay;
  schedule_.sanitize();
  saveSchedule_ = true;
  viewDirty_ = true;
  char t[8];
  formatMinuteOfDay(schedule_.minuteOfDay[slot], t, sizeof t);
  log("dose %d set to %s", slot + 1, t);
}

Outputs Dispenser::update(const Inputs& in) {
  Outputs out;
  const uint32_t now = in.nowMs;
  if (!started_) {
    started_ = true;
    selDeb_.reset(in.selectRaw, now);
    backDeb_.reset(in.backRaw, now);
    homeDeb_.reset(in.homeRaw, now);
    lastEnc_ = in.encoder;
    lastCtrlMs_ = now;
    lastScaleSeq_ = in.scaleSeq;
    lastInputMs_ = now;
    enter(State::Boot, in);
  }

  const bool sel = selDeb_.update(now, in.selectRaw) || in.requestAck;
  const bool back = backDeb_.update(now, in.backRaw);
  homeDeb_.update(now, in.homeRaw);
  if (sel || back) lastInputMs_ = now;

  if (in.scaleSeq != lastScaleSeq_) {
    lastScaleSeq_ = in.scaleSeq;
    onScaleSample(in.scaleGrams, in.scaleOk);
  }

  // Speed estimate and closed-loop control at a fixed period.
  if (now - lastCtrlMs_ >= cfg::kControlPeriodMs) {
    const float dt = static_cast<float>(now - lastCtrlMs_);
    const float v = static_cast<float>(in.encoder - lastEnc_) / dt;
    vel_ += cfg::kVelFilterAlpha * (v - vel_);
    lastEnc_ = in.encoder;
    lastCtrlMs_ = now;
    if (move_.active()) {
      duty_ = move_.update(now, in.encoder, vel_);
      if (!move_.active()) startBrake(now);
    }
  }

  // Clock and schedule. Doses are only given from IDLE/MENU; a dose that
  // falls due while busy is reported as missed (never stacked).
  clockValid_ = in.clockValid;
  unix_ = in.unixLocal;
  if (homed_ && state_ != State::Boot && state_ != State::Homing) {
    uint32_t when = 0;
    if (checkSchedule(when)) {
      char t[10];
      formatClock(when, t, sizeof t);
      t[5] = '\0';
      if (state_ == State::Idle || state_ == State::Menu) {
        log("scheduled dose %s due", t);
        startDose(in, true, when);
      } else {
        note("Missed %s (busy)", t);
        log("dose %s skipped: busy in %s", t, stateName(state_));
      }
    }
  }

  if (homingRequested_ && (state_ == State::Idle || state_ == State::Menu)) {
    homingRequested_ = false;
    enter(State::Homing, in);
  }

  switch (state_) {
    case State::Boot:
      if (now - stateMs_ >= cfg::kBootSettleMs) enter(State::Homing, in);
      break;
    case State::Homing:
      handleHoming(in);
      break;
    case State::Idle:
      if (in.requestDispense) {
        log("manual dispense requested");
        startDose(in, false, 0);
      } else if (sel) {
        enter(State::Menu, in);
      }
      break;
    case State::Menu:
      handleMenu(in, sel, back);
      break;
    case State::Dispensing:
      handleDispensing(in);
      break;
    case State::Verify:
      handleVerify(in);
      break;
    case State::WaitPickup:
    case State::Reminder:
      handlePickup(in, sel);
      break;
    case State::Fault:
      if (sel) {
        const bool rehome = !homed_ || fault_ == FaultCode::Jam ||
                            fault_ == FaultCode::HomeNotFound ||
                            fault_ == FaultCode::EncoderDirection;
        log("fault %s acknowledged", faultName(fault_));
        fault_ = FaultCode::None;
        enter(rehome ? State::Homing : State::Idle, in);
      }
      break;
  }

  // Motor outputs.
  if (move_.active()) {
    out.motorEnable = true;
    out.duty = duty_;
  } else if (braking_ && !brakeDone(now)) {
    out.motorEnable = true;
    out.brake = true;
  } else {
    braking_ = false;
  }
  indicators(now, out);

  out.saveSchedule = saveSchedule_;
  out.saveLastDose = saveLastDose_;
  out.setClock = setClock_;
  out.clockUnix = clockUnix_;
  saveSchedule_ = saveLastDose_ = setClock_ = false;

  if (viewDirty_ || now - lastRenderMs_ >= 250) render(in);
  return out;
}

// ---------------------------------------------------------------- helpers
void Dispenser::log(const char* fmt, ...) {
  va_list ap;
  va_start(ap, fmt);
  vsnprintf(event_, sizeof event_, fmt, ap);
  va_end(ap);
  ++eventSeq_;
}

void Dispenser::note(const char* fmt, ...) {
  va_list ap;
  va_start(ap, fmt);
  vsnprintf(note_, sizeof note_, fmt, ap);
  va_end(ap);
  viewDirty_ = true;
}

void Dispenser::enter(State s, const Inputs& in) {
  const uint32_t now = in.nowMs;
  if (s != state_ || !eventSeq_) log("state %s -> %s", stateName(state_), stateName(s));
  state_ = s;
  stateMs_ = now;
  viewDirty_ = true;
  switch (s) {
    case State::Homing:
      move_.abort();
      homed_ = false;
      homeBeamStart_ = in.beamEvents;
      seenRelease_ = !homeDeb_.stable();
      homePhase_ = HomePhase::Seek;
      startMove(in, in.encoder + degToCounts(cfg::kHomeMaxDeg), cfg::kHomeRpm);
      break;
    case State::Menu:
      page_ = MenuPage::Main;
      pot_.reset(kMenuItems, in.potRaw, cfg::kAdcMax);
      lastInputMs_ = now;
      break;
    case State::Dispensing:
      startBaseline(in);
      break;
    case State::Verify:
      collector_.begin(now);
      break;
    case State::WaitPickup:
      doseReadyMs_ = now;
      belowCount_ = 0;
      break;
    default:
      break;
  }
}

void Dispenser::raise(FaultCode f, const Inputs& in) {
  if (move_.active()) {
    move_.abort();
    startBrake(in.nowMs);
  }
  fault_ = f;
  log("FAULT %s", faultName(f));
  enter(State::Fault, in);
}

void Dispenser::startMove(const Inputs& in, int32_t target, float rpm) {
  braking_ = false;
  duty_ = 0.0f;
  move_.start(in.nowMs, in.encoder, target, rpmToCountsPerMs(rpm), static_cast<float>(MECH_ACCEL_MS),
              MECH_JAM_MIN_SPEED_FRAC, MECH_JAM_STALL_MS);
}

void Dispenser::startBrake(uint32_t now) {
  braking_ = true;
  brakeStartMs_ = now;
  duty_ = 0.0f;
}

bool Dispenser::brakeDone(uint32_t now) const {
  return !braking_ || now - brakeStartMs_ >= cfg::kBrakeMs;
}

bool Dispenser::checkSchedule(uint32_t& when) {
  if (!clockValid_) {
    lastCheck_ = 0;
    return false;
  }
  if (resyncCheck_) {  // clock was just set by the user: no catch-up
    resyncCheck_ = false;
    lastCheck_ = unix_;
    return false;
  }
  if (lastCheck_ == 0 || unix_ < lastCheck_) {
    // First valid time after boot (or clock moved backwards): give a dose
    // that fell due within the grace period unless it was already given.
    const uint32_t floor = unix_ > cfg::kDoseGraceS ? unix_ - cfg::kDoseGraceS : 0;
    lastCheck_ = lastDoseUnix_ > floor && lastDoseUnix_ <= unix_ ? lastDoseUnix_ : floor;
  }
  int slot = -1;
  const bool due = schedule_.dueBetween(lastCheck_, unix_, when, slot) &&
                   unix_ - when <= cfg::kDoseGraceS;
  lastCheck_ = unix_;
  return due;
}

void Dispenser::onScaleSample(float grams, bool ok) {
  lastGrams_ = grams;
  lastScaleOk_ = ok;
  collector_.add(grams, ok);
  if (state_ == State::WaitPickup || state_ == State::Reminder) {
    const bool below = ok && massValid_ && grams <= afterMean_ - 0.5f * MECH_PILL_MASS_G_MIN;
    belowCount_ = below ? static_cast<uint8_t>(belowCount_ + 1) : 0;
  }
}

// ---------------------------------------------------------------- homing
void Dispenser::handleHoming(const Inputs& in) {
  const uint32_t now = in.nowMs;
  const bool home = homeDeb_.stable();
  switch (homePhase_) {
    case HomePhase::Seek:
      if (!move_.active()) {
        const MoveResult r = move_.result();
        if (r == MoveResult::WrongDirection) raise(FaultCode::EncoderDirection, in);
        else if (r == MoveResult::Stalled || r == MoveResult::PositionError) raise(FaultCode::Jam, in);
        else raise(FaultCode::HomeNotFound, in);
        return;
      }
      if (!seenRelease_) {
        if (!home) seenRelease_ = true;  // started on the switch: leave it first
      } else if (home) {
        homeEdge_ = in.encoder;
        move_.abort();
        startBrake(now);
        homePhase_ = HomePhase::Brake;
      }
      break;
    case HomePhase::Brake:
      if (!brakeDone(now)) break;
      homeTarget_ = homeEdge_ + degToCounts(MECH_HOME_OFFSET_DEG);
      if (absI(homeTarget_ - in.encoder) > degToCounts(cfg::kPosTolDeg)) {
        startMove(in, homeTarget_, cfg::kHomeRpm);
        homePhase_ = HomePhase::Offset;
      } else {
        homePhase_ = HomePhase::Finish;
      }
      break;
    case HomePhase::Offset:
      if (move_.active() || !brakeDone(now)) break;
      if (move_.result() == MoveResult::Done) homePhase_ = HomePhase::Finish;
      else if (move_.result() == MoveResult::WrongDirection) raise(FaultCode::EncoderDirection, in);
      else raise(FaultCode::Jam, in);
      break;
    case HomePhase::Finish:
      indexPos_ = homeTarget_;
      homed_ = true;
      log("homed: edge %ld, index position %ld", static_cast<long>(homeEdge_),
          static_cast<long>(indexPos_));
      if (in.beamEvents != homeBeamStart_) raise(FaultCode::HomingDrop, in);
      else enter(State::Idle, in);
      break;
  }
}

// ---------------------------------------------------------------- menu
void Dispenser::handleMenu(const Inputs& in, bool sel, bool back) {
  const uint32_t now = in.nowMs;
  const int before = pot_.index();
  const int idx = pot_.update(in.potRaw);
  if (idx != before) {
    lastInputMs_ = now;
    viewDirty_ = true;
  }
  if (now - lastInputMs_ >= cfg::kMenuTimeoutMs) {
    enter(State::Idle, in);
    return;
  }
  switch (page_) {
    case MenuPage::Main:
      if (back) {
        enter(State::Idle, in);
      } else if (sel) {
        if (idx == 0) {
          log("menu: dispense now");
          startDose(in, false, 0);
        } else if (idx >= 1 && idx <= 3) {
          editSlot_ = idx - 1;
          page_ = MenuPage::EditDose;
          pot_.reset(kDoseChoices, in.potRaw, cfg::kAdcMax);
        } else if (idx == 4) {
          page_ = MenuPage::ClockHour;
          pot_.reset(24, in.potRaw, cfg::kAdcMax);
        } else if (idx == 5) {
          enter(State::Homing, in);
        } else {
          enter(State::Idle, in);
        }
        viewDirty_ = true;
      }
      break;
    case MenuPage::EditDose:
      if (sel) {
        setDose(editSlot_, idx == 0 ? kDoseOff : static_cast<int16_t>((idx - 1) * cfg::kDoseStepMin));
      }
      if (sel || back) {
        page_ = MenuPage::Main;
        pot_.reset(kMenuItems, in.potRaw, cfg::kAdcMax);
        viewDirty_ = true;
      }
      break;
    case MenuPage::ClockHour:
      if (sel) {
        editHour_ = idx;
        page_ = MenuPage::ClockMinute;
        pot_.reset(60, in.potRaw, cfg::kAdcMax);
      } else if (back) {
        page_ = MenuPage::Main;
        pot_.reset(kMenuItems, in.potRaw, cfg::kAdcMax);
      }
      if (sel || back) viewDirty_ = true;
      break;
    case MenuPage::ClockMinute:
      if (sel) {
        clockUnix_ = (unix_ / 86400UL) * 86400UL + static_cast<uint32_t>(editHour_) * 3600UL +
                     static_cast<uint32_t>(idx) * 60UL;
        setClock_ = true;
        resyncCheck_ = true;
        log("clock set to %02d:%02d", editHour_, idx);
        page_ = MenuPage::Main;
        pot_.reset(kMenuItems, in.potRaw, cfg::kAdcMax);
      } else if (back) {
        page_ = MenuPage::ClockHour;
        pot_.reset(24, in.potRaw, cfg::kAdcMax);
      }
      if (sel || back) viewDirty_ = true;
      break;
  }
}

// ---------------------------------------------------------------- dispensing
void Dispenser::startDose(const Inputs& in, bool scheduled, uint32_t when) {
  doseScheduled_ = scheduled;
  if (scheduled) {
    lastDoseUnix_ = when;
    saveLastDose_ = true;  // persisted before the motor moves (baseline phase)
  }
  indexSteps_ = 0;
  enter(State::Dispensing, in);
}

void Dispenser::startBaseline(const Inputs& in) {
  dispPhase_ = DispensePhase::Baseline;
  collector_.begin(in.nowMs);
}

void Dispenser::startStep(const Inputs& in) {
  ++indexSteps_;
  jamRetries_ = 0;  // MECH_MAX_RETRIES applies to each index move
  dispTarget_ = indexPos_ + degToCounts(MECH_INDEX_DEG);
  startForward(in);
}

void Dispenser::startForward(const Inputs& in) {
  fwdStartMs_ = in.nowMs;
  dispPhase_ = DispensePhase::Forward;
  startMove(in, dispTarget_, MECH_TARGET_RPM);
  viewDirty_ = true;
}

void Dispenser::handleDispensing(const Inputs& in) {
  const uint32_t now = in.nowMs;
  switch (dispPhase_) {
    case DispensePhase::Baseline:
      if (in.beamBlocked) {
        raise(FaultCode::BeamBlocked, in);
        return;
      }
      if (!collector_.complete(now)) break;
      baseValid_ = collector_.valid();
      baseMean_ = collector_.mean();
      beamStart_ = in.beamEvents;
      startStep(in);
      break;
    case DispensePhase::Forward:
      if (move_.active()) break;
      switch (move_.result()) {
        case MoveResult::Done:
          indexPos_ = dispTarget_;
          lastFwdMs_ = move_.elapsedMs();
          moveDoneMs_ = now;
          dispPhase_ = DispensePhase::Settle;
          break;
        case MoveResult::WrongDirection:
          raise(FaultCode::EncoderDirection, in);
          return;
        default:  // Stalled or PositionError
          ++jamEvents_;
          log("jam detected at %ld counts (target %ld)", static_cast<long>(in.encoder),
              static_cast<long>(dispTarget_));
          dispPhase_ = DispensePhase::JamBrake;
          viewDirty_ = true;
          break;
      }
      break;
    case DispensePhase::JamBrake:
      if (!brakeDone(now)) break;
      if (jamRetries_ >= MECH_MAX_RETRIES) {
        raise(FaultCode::Jam, in);
        return;
      }
      ++jamRetries_;
      ++reverseMoves_;
      startMove(in, in.encoder - degToCounts(MECH_REVERSE_DEG), MECH_TARGET_RPM);
      dispPhase_ = DispensePhase::Reverse;
      break;
    case DispensePhase::Reverse:
      if (move_.active()) break;
      if (move_.result() == MoveResult::Done) {
        dispPhase_ = DispensePhase::ReverseBrake;
      } else if (move_.result() == MoveResult::WrongDirection) {
        raise(FaultCode::EncoderDirection, in);
      } else {
        raise(FaultCode::Jam, in);  // cannot back off either
      }
      break;
    case DispensePhase::ReverseBrake:
      if (brakeDone(now)) startForward(in);  // retry to the same absolute target
      break;
    case DispensePhase::Settle:
      if (!brakeDone(now) || now - moveDoneMs_ < MECH_SETTLE_MS) break;
      if (in.beamEvents != beamStart_) {
        // Pill seen: stop indexing. Keep counting (no motion) until
        // MECH_DROP_WINDOW_MS after this move started so a trailing second
        // pill is still classified as DOUBLE.
        dispPhase_ = DispensePhase::DropWait;
      } else if (indexSteps_ < MECH_MAX_INDEX_STEPS) {
        log("step %d: no pill, indexing next pocket", indexSteps_);
        startStep(in);
      } else {
        enter(State::Verify, in);  // 0 pills after all steps -> MISS
      }
      break;
    case DispensePhase::DropWait:
      if (now - fwdStartMs_ >= MECH_DROP_WINDOW_MS) enter(State::Verify, in);
      break;
  }
}

void Dispenser::handleVerify(const Inputs& in) {
  if (!collector_.complete(in.nowMs)) return;
  lastBeams_ = in.beamEvents - beamStart_;
  afterMean_ = collector_.mean();
  massValid_ = baseValid_ && collector_.valid();
  lastDelta_ = massValid_ ? afterMean_ - baseMean_ : 0.0f;
  verdict_ = classifyDispense(lastBeams_, massValid_, lastDelta_, MECH_PILL_MASS_G_MIN);
  log("verify: beam %lu, mass %s %+.3f g -> %s", static_cast<unsigned long>(lastBeams_),
      massValid_ ? "ok" : "n/a", static_cast<double>(lastDelta_), verdictName(verdict_));
  switch (verdict_) {
    case Verdict::Ok:
    case Verdict::OkBeamOnly:
      enter(State::WaitPickup, in);
      break;
    case Verdict::Miss:
      raise(FaultCode::Miss, in);
      break;
    case Verdict::Double:
      raise(FaultCode::Double, in);
      break;
    case Verdict::SensorMismatch:
      raise(FaultCode::SensorMismatch, in);
      break;
  }
}

void Dispenser::handlePickup(const Inputs& in, bool sel) {
  const uint32_t now = in.nowMs;
  char t[10];
  formatClock(unix_, t, sizeof t);
  t[5] = '\0';
  if (sel || belowCount_ >= 2) {
    note("Last dose %s taken", clockValid_ ? t : "");
    log(sel ? "pickup acknowledged" : "pickup detected by load cell");
    enter(State::Idle, in);
    return;
  }
  if (state_ == State::WaitPickup && now - stateMs_ >= cfg::kPickupRemindMs) {
    enter(State::Reminder, in);
  } else if (state_ == State::Reminder && now - doseReadyMs_ >= cfg::kReminderGiveUpMs) {
    note("Dose NOT taken");
    log("pickup timeout: dose not taken");
    enter(State::Idle, in);
  }
}

// ---------------------------------------------------------------- outputs
void Dispenser::indicators(uint32_t now, Outputs& out) const {
  const uint32_t t = now - stateMs_;
  switch (state_) {
    case State::WaitPickup:
      out.buzzer = t < 1500 && (t % 500) < 150;
      out.led = (now % 1000) < 500;
      break;
    case State::Reminder: {
      const uint32_t r = t % cfg::kReminderPeriodMs;
      out.buzzer = r < 3000 && (r % 600) < 300;
      out.led = (now % 500) < 250;
      break;
    }
    case State::Fault:
      out.buzzer = t < cfg::kFaultBeepMs && (t % 2000) < 400;
      out.led = (now % 250) < 125;
      break;
    case State::Homing:
    case State::Dispensing:
    case State::Verify:
      out.led = true;
      break;
    default:
      out.led = (now % 3000) < 60;  // heartbeat
      break;
  }
}

void Dispenser::render(const Inputs& in) {
  View v{};
  char a[12], b[12], c[12];
  auto L = [&v](int i, const char* fmt, ...) {
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(v.line[i], kViewCols, fmt, ap);
    va_end(ap);
  };
  const uint32_t now = in.nowMs;
  switch (state_) {
    case State::Boot:
      snprintf(v.title, sizeof v.title, "Pill Dispenser");
      L(0, "Starting...");
      L(1, "Mechanism: %s", MECH_NAME);
      break;
    case State::Homing:
      snprintf(v.title, sizeof v.title, "Homing");
      L(0, "Finding drum home");
      L(1, "Keep hands clear");
      break;
    case State::Idle: {
      snprintf(v.title, sizeof v.title, "Pill Dispenser");
      if (clockValid_) {
        formatClock(unix_, a, sizeof a);
        L(0, "Time  %s", a);
        uint32_t when = 0;
        int slot = -1;
        if (schedule_.nextAfter(unix_, when, slot)) {
          formatClock(when, b, sizeof b);
          b[5] = '\0';
          formatDuration(when - unix_, c, sizeof c);
          L(1, "Next  %s (in %s)", b, c);
        } else {
          L(1, "No doses scheduled");
        }
      } else {
        L(0, "Clock not set!");
        L(1, "Menu > Set clock");
      }
      L(2, "%s", note_);
      if (in.beamBlocked) L(3, "Chute sensor blocked");
      else if (!lastScaleOk_) L(3, "Scale n/a: beam-only");
      snprintf(v.footer, kViewCols, "Select: menu");
      break;
    }
    case State::Menu:
      switch (page_) {
        case MenuPage::Main: {
          snprintf(v.title, sizeof v.title, "Menu");
          const int sel = pot_.index();
          int first = sel - 1;
          if (first < 0) first = 0;
          if (first > kMenuItems - kViewLines) first = kMenuItems - kViewLines;
          for (int i = 0; i < kViewLines; ++i) {
            const int item = first + i;
            if (item >= 1 && item <= 3) {
              formatMinuteOfDay(schedule_.minuteOfDay[item - 1], a, sizeof a);
              L(i, "%s%s: %s", item == sel ? "> " : "  ", kMenuText[item], a);
            } else {
              L(i, "%s%s", item == sel ? "> " : "  ", kMenuText[item]);
            }
          }
          snprintf(v.footer, kViewCols, "Sel: choose  Back: exit");
          break;
        }
        case MenuPage::EditDose: {
          snprintf(v.title, sizeof v.title, "Dose %c time", static_cast<char>('1' + editSlot_));
          const int idx = pot_.index();
          formatMinuteOfDay(idx == 0 ? kDoseOff : static_cast<int16_t>((idx - 1) * cfg::kDoseStepMin),
                            a, sizeof a);
          formatMinuteOfDay(schedule_.minuteOfDay[editSlot_], b, sizeof b);
          L(0, "Turn knob to choose");
          L(1, "  New: %s", a);
          L(2, "  Was: %s", b);
          snprintf(v.footer, kViewCols, "Sel: save  Back: cancel");
          break;
        }
        case MenuPage::ClockHour:
        case MenuPage::ClockMinute:
          snprintf(v.title, sizeof v.title, "Set clock");
          if (page_ == MenuPage::ClockHour) {
            L(0, "Hour: %02d", pot_.index());
          } else {
            L(0, "Time: %02d:%02d", editHour_, pot_.index());
          }
          L(1, "Turn knob, Sel to set");
          snprintf(v.footer, kViewCols, "Sel: next  Back: back");
          break;
      }
      break;
    case State::Dispensing:
      snprintf(v.title, sizeof v.title, "Dispensing");
      switch (dispPhase_) {
        case DispensePhase::Baseline: L(0, "Weighing cup"); break;
        case DispensePhase::Forward: L(0, "Indexing %d deg", static_cast<int>(MECH_INDEX_DEG)); break;
        case DispensePhase::JamBrake:
        case DispensePhase::Reverse:
        case DispensePhase::ReverseBrake:
          L(0, "Jam: backing off %u/%u", static_cast<unsigned>(jamRetries_),
            static_cast<unsigned>(MECH_MAX_RETRIES));
          break;
        case DispensePhase::Settle:
        case DispensePhase::DropWait: L(0, "Waiting for drop"); break;
      }
      L(1, "Pocket %d of %d", indexSteps_, MECH_MAX_INDEX_STEPS);
      break;
    case State::Verify:
      snprintf(v.title, sizeof v.title, "Checking");
      L(0, "Counting pills...");
      break;
    case State::WaitPickup:
    case State::Reminder:
      snprintf(v.title, sizeof v.title, state_ == State::Reminder ? "REMINDER" : "Take your pill");
      L(0, "1 pill in the cup");
      if (verdict_ == Verdict::OkBeamOnly) L(1, "(scale not used)");
      L(2, "Take it, then press Sel");
      if (state_ == State::Reminder) {
        formatDuration((now - doseReadyMs_) / 1000, a, sizeof a);
        L(3, "Waiting %s", a);
      }
      snprintf(v.footer, kViewCols, "Sel: taken");
      break;
    case State::Fault:
      snprintf(v.title, sizeof v.title, "FAULT");
      L(0, "%s", faultName(fault_));
      switch (fault_) {
        case FaultCode::Jam: L(1, "Drum jammed (%u tries)", static_cast<unsigned>(MECH_MAX_RETRIES + 1));
          L(2, "Unplug 12V, clear jam"); break;
        case FaultCode::HomeNotFound: L(1, "Home switch not found"); L(2, "Check switch/wiring"); break;
        case FaultCode::EncoderDirection: L(1, "Motor/encoder reversed"); L(2, "Swap motor leads"); break;
        case FaultCode::Double: L(1, "2+ pills dropped!"); L(2, "Remove extras first"); break;
        case FaultCode::Miss: L(1, "No pill in %d pockets", MECH_MAX_INDEX_STEPS);
          L(2, "Canister empty: REFILL"); break;
        case FaultCode::BeamBlocked: L(1, "Chute sensor blocked"); L(2, "Clear chute/align beam"); break;
        case FaultCode::SensorMismatch: L(1, "Beam/scale disagree"); L(2, "Check cup by hand"); break;
        case FaultCode::HomingDrop: L(1, "Pill fell while homing"); L(2, "Check cup by hand"); break;
        case FaultCode::None: break;
      }
      snprintf(v.footer, kViewCols, "Sel: acknowledge");
      break;
  }
  lastRenderMs_ = now;
  viewDirty_ = false;
  if (memcmp(&v, &view_, sizeof v) != 0) {
    view_ = v;
    ++viewSeq_;
  }
}

}  // namespace dc
