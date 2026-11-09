// Dispenser state machine. Hardware-independent: the Arduino layer
// (firmware/dispenser/main.cpp) fills Inputs from the sensors every loop,
// calls update(), and applies Outputs to the motor driver, buzzer, LED, NVS,
// RTC and display. The host tests drive the same class with simulated sensors.
//
//   BOOT -> HOMING -> IDLE <-> MENU
//                      |  (dose due / "dispense now")
//                      v
//                 DISPENSING (baseline weigh -> forward index -> [jam: brake,
//                      |      reverse, retry] -> settle / drop window)
//                      v
//                    VERIFY --miss, retries left--> DISPENSING
//                      |  ok
//                      v
//                 WAIT_PICKUP -> REMINDER -> IDLE
//   any failure -> FAULT (Select acknowledges -> HOMING or IDLE)
#pragma once
#include <stdint.h>

#include "dc_config.h"
#include "menu.h"
#include "motion.h"
#include "schedule.h"
#include "verify.h"

namespace dc {

enum class State : uint8_t { Boot, Homing, Idle, Menu, Dispensing, Verify, WaitPickup, Reminder, Fault };
enum class FaultCode : uint8_t {
  None,
  Jam,               // stalled forward more than MECH_MAX_RETRIES times, or stalled reversing
  HomeNotFound,      // home switch not seen within cfg::kHomeMaxDeg
  EncoderDirection,  // encoder counts opposite to the commanded direction
  Double,            // 2+ beam events in one dispense
  Miss,              // no pill after 1 + MECH_MAX_RETRIES pockets (canister empty?)
  BeamBlocked,       // chute beam blocked before the move started
  SensorMismatch,    // beam and load cell disagree
  HomingDrop,        // a pill fell while homing
};
enum class DispensePhase : uint8_t { Baseline, Forward, JamBrake, Reverse, ReverseBrake, Settle };
enum class HomePhase : uint8_t { Seek, Brake, Offset, Finish };
enum class MenuPage : uint8_t { Main, EditDose, ClockHour, ClockMinute };

const char* stateName(State s);
const char* faultName(FaultCode f);

struct Inputs {
  uint32_t nowMs = 0;
  int32_t encoder = 0;         // output-shaft quadrature counts (forward = positive)
  uint32_t beamEvents = 0;     // cumulative beam BLOCK events (from the ISR)
  bool beamBlocked = false;    // current beam level
  bool homeRaw = false;        // home switch actuated (raw)
  bool selectRaw = false;      // Select pressed (raw)
  bool backRaw = false;        // Back pressed (raw)
  int potRaw = 0;              // 0..4095
  uint32_t scaleSeq = 0;       // increments once per new HX711 sample
  float scaleGrams = 0.0f;     // latest sample in grams (meaningful only if scaleOk)
  bool scaleOk = false;        // HX711 responding AND calibrated
  bool clockValid = false;     // RTC present and time set
  uint32_t unixLocal = 0;      // RTC local wall-clock seconds
  bool requestDispense = false;  // one-shot (serial "d")
  bool requestAck = false;       // one-shot (serial "a"), same as Select
};

struct Outputs {
  bool motorEnable = false;  // TB6612 STBY
  float duty = 0.0f;         // -1..1 on PWMA with AIN1/AIN2 for sign
  bool brake = false;        // short brake (AIN1 = AIN2 = HIGH)
  bool buzzer = false;
  bool led = false;
  bool saveSchedule = false;  // persist schedule() to NVS
  bool saveLastDose = false;  // persist lastDoseUnix() to NVS
  bool setClock = false;      // write clockUnix to the RTC
  uint32_t clockUnix = 0;
};

constexpr int kViewLines = 4;
constexpr int kViewCols = 27;  // 26 chars of 12 px (text size 2) fit in 320 px
struct View {
  char title[18];  // text size 3
  char line[kViewLines][kViewCols];
  char footer[kViewCols];
};

class Dispenser {
 public:
  void begin(const Schedule& schedule, uint32_t lastDoseUnix);
  Outputs update(const Inputs& in);

  // Serial/bring-up helpers (take effect on the next update()).
  void setDose(int slot, int16_t minuteOfDay);
  void requestHoming() { homingRequested_ = true; }

  State state() const { return state_; }
  FaultCode fault() const { return fault_; }
  Verdict lastVerdict() const { return verdict_; }
  DispensePhase dispensePhase() const { return dispPhase_; }
  const Schedule& schedule() const { return schedule_; }
  uint32_t lastDoseUnix() const { return lastDoseUnix_; }
  const View& view() const { return view_; }
  uint32_t viewSeq() const { return viewSeq_; }
  const char* lastEvent() const { return event_; }
  uint32_t eventSeq() const { return eventSeq_; }

  // Diagnostics (also used by the host tests).
  bool homed() const { return homed_; }
  int32_t indexPosition() const { return indexPos_; }
  uint32_t lastForwardMoveMs() const { return lastFwdMs_; }
  uint32_t jamEvents() const { return jamEvents_; }
  uint32_t reverseMoves() const { return reverseMoves_; }
  uint8_t missRetries() const { return missRetries_; }
  uint32_t lastBeamCount() const { return lastBeams_; }
  float lastMassDeltaG() const { return lastDelta_; }
  float speedCpms() const { return vel_; }

 private:
  struct Collector {
    bool active = false, bad = false;
    uint8_t n = 0;
    float sum = 0.0f;
    uint32_t start = 0;
    void begin(uint32_t now) { active = true; bad = false; n = 0; sum = 0.0f; start = now; }
    void add(float g, bool ok);
    bool complete(uint32_t now) const;
    bool valid() const;
    float mean() const { return n ? sum / n : 0.0f; }
  };

  void enter(State s, const Inputs& in);
  void raise(FaultCode f, const Inputs& in);
  void startMove(const Inputs& in, int32_t target, float rpm);
  void startBrake(uint32_t now);
  bool brakeDone(uint32_t now) const;
  void startDose(const Inputs& in, bool scheduled, uint32_t when);
  void startBaseline(const Inputs& in);
  void startForward(const Inputs& in);
  bool checkSchedule(uint32_t& when);
  void onScaleSample(float grams, bool ok);
  void handleHoming(const Inputs& in);
  void handleMenu(const Inputs& in, bool sel, bool back);
  void handleDispensing(const Inputs& in);
  void handleVerify(const Inputs& in);
  void handlePickup(const Inputs& in, bool sel);
  void indicators(uint32_t now, Outputs& out) const;
  void render(const Inputs& in);
  void log(const char* fmt, ...);
  void note(const char* fmt, ...);

  // Configuration / persistent state
  Schedule schedule_;
  uint32_t lastDoseUnix_ = 0;

  // Core state
  bool started_ = false;
  State state_ = State::Boot;
  FaultCode fault_ = FaultCode::None;
  uint32_t stateMs_ = 0;
  bool homed_ = false, homingRequested_ = false;

  // Inputs conditioning
  Debouncer selDeb_{cfg::kButtonDebounceMs}, backDeb_{cfg::kButtonDebounceMs},
      homeDeb_{cfg::kSwitchDebounceMs};
  PotSelector pot_;
  uint32_t lastInputMs_ = 0;
  uint32_t lastScaleSeq_ = 0;
  float lastGrams_ = 0.0f;
  bool lastScaleOk_ = false;
  uint8_t belowCount_ = 0;

  // Motion
  MoveController move_;
  int32_t lastEnc_ = 0;
  uint32_t lastCtrlMs_ = 0;
  float vel_ = 0.0f, duty_ = 0.0f;
  bool braking_ = false;
  uint32_t brakeStartMs_ = 0;

  // Homing
  HomePhase homePhase_ = HomePhase::Seek;
  bool seenRelease_ = false;
  int32_t homeEdge_ = 0, homeTarget_ = 0;
  uint32_t homeBeamStart_ = 0;
  int32_t indexPos_ = 0;  // absolute encoder count of the current "pocket under hopper" position

  // Dispensing
  DispensePhase dispPhase_ = DispensePhase::Baseline;
  int32_t dispTarget_ = 0;
  uint32_t fwdStartMs_ = 0, moveDoneMs_ = 0, lastFwdMs_ = 0;
  uint8_t jamRetries_ = 0, missRetries_ = 0;
  uint32_t jamEvents_ = 0, reverseMoves_ = 0;
  uint32_t beamStart_ = 0, lastBeams_ = 0;
  Collector collector_;
  bool baseValid_ = false, massValid_ = false;
  float baseMean_ = 0.0f, afterMean_ = 0.0f, lastDelta_ = 0.0f;
  Verdict verdict_ = Verdict::Miss;
  bool doseScheduled_ = false;
  uint32_t doseReadyMs_ = 0;

  // Schedule
  bool clockValid_ = false, resyncCheck_ = false;
  uint32_t unix_ = 0, lastCheck_ = 0;

  // Menu
  MenuPage page_ = MenuPage::Main;
  int editSlot_ = 0, editHour_ = 0;

  // Pending outputs
  bool saveSchedule_ = false, saveLastDose_ = false, setClock_ = false;
  uint32_t clockUnix_ = 0;

  // UI
  View view_{};
  uint32_t viewSeq_ = 0, lastRenderMs_ = 0;
  bool viewDirty_ = true;
  char note_[kViewCols] = "";
  char event_[96] = "";
  uint32_t eventSeq_ = 0;
};

}  // namespace dc
