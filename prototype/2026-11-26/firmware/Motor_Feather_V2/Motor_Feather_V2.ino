// USB-C Feather ESP32 V2. Change wheel geometry, timeouts and speed in MotorSettings.h.
// Each dispensing job seeks one piece. Canister 1 advances 60 degrees, then
// allows one backward-and-return rock if the display's scale still reads empty.
#include <Arduino.h>
#include <math.h>
#include <soc/gpio_struct.h>
#include "MotorSettings.h"
#include "Transport.h"

#if defined(ARDUINO) && !defined(ARDUINO_ADAFRUIT_FEATHER_ESP32_V2)
#error "Select Adafruit Feather ESP32 V2 (USB-C) for the motor sketch."
#endif

namespace Motion {
using namespace MotorSettings;
constexpr uint8_t DIR1 = 33, DIR2 = 26, STBY = 21;
constexpr uint8_t MOTOR_PWM[6] = {27, 25, 19, 13, 4, 14};
constexpr int UART_RX = 7, UART_TX = 8;
constexpr uint16_t TICK_US = 125;                  // eight ticks per 1 kHz PWM cycle
constexpr uint16_t LEASE_TICKS = 100000 / TICK_US; // five missing 20 ms control frames
constexpr uint32_t STATUS_MS = 25;
// Pololu #5229: 12 quadrature counts per motor-shaft turn, about 986.41:1 gearbox.
constexpr double GEAR_RATIO =
    (25.0 * 34 * 35 * 34 * 34 * 34 * 27) / (12.0 * 9 * 12 * 14 * 14 * 14 * 9);
constexpr double COUNTS_PER_OUTPUT_TURN = 12.0 * GEAR_RATIO;
// One encoder transition spends TICKS_PER_SECOND credits. The speed (counts per
// second) adds credits each timer tick, keeping the interrupt math integral.
constexpr int32_t TICKS_PER_SECOND = 1000000 / TICK_US;
constexpr double C1_COUNTS_PER_DEGREE =
    COUNTS_PER_OUTPUT_TURN * CARTRIDGES[0].gearboxOutputTurnsPerWheelTurn / 360.0;
constexpr int32_t C1_CRUISE_RATE = int32_t(C1_COUNTS_PER_DEGREE * C1_CRUISE_DEG_PER_SEC + 0.5);
constexpr int32_t C1_APPROACH_RATE = int32_t(C1_COUNTS_PER_DEGREE * C1_APPROACH_DEG_PER_SEC + 0.5);
constexpr int32_t C1_APPROACH_COUNTS = int32_t(C1_COUNTS_PER_DEGREE * C1_APPROACH_DEGREES + 0.5);
constexpr int32_t EDGE_CREEP_RATE = int32_t(C1_COUNTS_PER_DEGREE * Link::EDGE_CREEP_DEG_PER_SEC + 0.5);
constexpr int32_t EDGE_GOAL_COUNTS = int32_t(C1_COUNTS_PER_DEGREE * Link::EDGE_FORWARD_DEGREES + 0.5);
constexpr int32_t EDGE_BACKOFF_COUNTS = int32_t(C1_COUNTS_PER_DEGREE * Link::EDGE_BACKOFF_DEGREES + 0.5);
constexpr int32_t EDGE_PROVE_COUNTS = int32_t(C1_COUNTS_PER_DEGREE * EDGE_PROVE_MOTION_DEGREES + 0.5);
constexpr int32_t ROCK_COUNTS = int32_t(C1_COUNTS_PER_DEGREE * Link::ROCK_DEGREES + 0.5);
constexpr int32_t ROCK_TOLERANCE_COUNTS = int32_t(C1_COUNTS_PER_DEGREE * ROCK_TOLERANCE_DEGREES + 0.5);
constexpr int32_t ROCK_CRUISE_RATE = int32_t(C1_COUNTS_PER_DEGREE * ROCK_CRUISE_DEG_PER_SEC + 0.5);
constexpr int32_t ROCK_APPROACH_RATE = int32_t(C1_COUNTS_PER_DEGREE * ROCK_APPROACH_DEG_PER_SEC + 0.5);
constexpr int32_t ROCK_APPROACH_COUNTS = int32_t(C1_COUNTS_PER_DEGREE * ROCK_APPROACH_DEGREES + 0.5);
constexpr int32_t BENCH_ROCK_APPROACH_COUNTS = int32_t(C1_COUNTS_PER_DEGREE * BENCH_ROCK_APPROACH_DEGREES + 0.5);
constexpr int32_t ROCK2_RAMP_RATE = int32_t(C1_COUNTS_PER_DEGREE * ROCK2_RAMP_TARGET_DEG_PER_SEC + 0.5);
constexpr int32_t ROCK2_APPROACH_COUNTS = int32_t(C1_COUNTS_PER_DEGREE * ROCK2_APPROACH_DEGREES + 0.5);
constexpr int32_t ROCK_RAMP_TICKS = ROCK_RAMP_MS * 1000 / TICK_US;
constexpr uint32_t C1_PATH_LIMIT = uint32_t(C1_COUNTS_PER_DEGREE * Link::MAX_PATH_DEGREES);
static_assert(EDGE_CREEP_RATE > 0 && EDGE_CREEP_RATE < TICKS_PER_SECOND && EDGE_PROVE_COUNTS > 0 &&
              EDGE_GOAL_COUNTS + 2 * EDGE_BACKOFF_COUNTS < C1_PATH_LIMIT, "Review EDGE travel settings");
// A reversal may add outward coast and return travel. Allow 2 degrees per leg in this bench job.
constexpr uint32_t benchRockPathLimit(uint8_t command) {
  return uint32_t(C1_COUNTS_PER_DEGREE * (Link::benchRockTravelDegrees(command) + 2 * Link::BENCH_ROCK_LEGS));
}
static_assert(Link::ROCK_HOLD_MS >= STOP_SETTLE_MS, "Let the wheel settle before reversing direction");
static_assert(ROCK_CRUISE_RATE < TICKS_PER_SECOND && ROCK2_RAMP_RATE < TICKS_PER_SECOND &&
              ROCK_APPROACH_COUNTS < ROCK_COUNTS &&
              ROCK_TOLERANCE_COUNTS > 0 && ROCK_TOLERANCE_COUNTS < ROCK_COUNTS,
              "Review the rock settings for this encoder");
// Allow at most half a degree of catch-up if the wheel sticks, and remember up
// to eight degrees of coasting ahead, during which PWM stays low.
constexpr int32_t C1_MAX_CREDIT = int32_t(0.5 * C1_COUNTS_PER_DEGREE + 1) * TICKS_PER_SECOND;
constexpr int32_t C1_MAX_LEAD = int32_t(8 * C1_COUNTS_PER_DEGREE + 1) * TICKS_PER_SECOND;
static_assert(C1_APPROACH_RATE > 0 && C1_CRUISE_RATE < TICKS_PER_SECOND,
              "Review encoder resolution and requested speed for canister 1");

enum Phase : uint8_t { IDLE = 0, ADVANCING = 1, SPINNING = 2, DONE = 3, FAULT = 4 };
enum RockLeg : uint8_t { NO_ROCK, ROCK_BACK, ROCK_RETURN };
enum Fault : uint8_t {
  NONE = 0,
  STALL = 1,
  SETUP_REQUIRED = 2,
  LINK_LOST = 4,
  OVERRUN = 5,
  ABORTED = 6,
  ENCODER = 7,
  TIMED_OUT = 8
};
struct Encoder {
  uint8_t a, b, last;
  volatile uint32_t raw;
};
Encoder local[3] = {{34, 32, 0, 0}, {36, 20, 0, 0}, {39, 22, 0, 0}};
uint32_t remote[3] = {}; // encoder snapshots sent by the display board
DRAM_ATTR const int8_t quad[16] = {0, -1, 1, 0, 1, 0, 0, -1, -1, 0, 0, 1, 0, 1, -1, 0};
struct Reference {
  bool known = false, inspection = false;
  uint32_t lastGoal = 0;
  double fraction = 0; // fractional encoder count carried into the next job
} reference[6];

Link::Status status{};
uint8_t wheel = 0, quantity = 0; // wheel is 1–6 while servicing a job
uint8_t activeCommand = 0;       // for NUDGE, quantity is the requested move ordinal
uint32_t nudgeDoneAt = 0;
uint32_t edgeLegStarted = 0, edgeWindowAt = 0;
int32_t edgeWindowTravel = 0;
bool edgeStoppingForBackoff = false;
bool handshake = false, timerReady = false, settling = false;
uint32_t highestJob = 0, jobStarted = 0, lastProgress = 0, stoppedAt = 0, lastStatus = 0;
int32_t lastTravel = 0, progressMark = 0;
uint32_t spinProgressRaw = 0;
int32_t pocketMark[6] = {}, tolerance = 0, slowZone = 0;
double nextFraction = 0;
int32_t settledTravel = 0;
uint32_t settledPath = 0;
portMUX_TYPE ioLock = portMUX_INITIALIZER_UNLOCKED;
volatile bool armed = false, reached = false, expired = false;
volatile uint16_t lease = 0;
volatile uint8_t localChannel = 3, pwmStep = 0, duty = 0;
volatile int8_t sign = 1;
volatile int32_t targetTravel = 0;
volatile uint32_t origin = 0, selectedMask = 0, appliedMask = 0;
volatile bool paceC1 = false;
volatile int32_t paceCredit = 0;
volatile RockLeg rockLeg = NO_ROCK;
volatile uint16_t rampTicks = 0;
volatile int32_t rockApproachCounts = ROCK_APPROACH_COUNTS;
volatile bool fullSpeedRock = false;
volatile bool edgeCreep = false;
int32_t rockReturnTarget = 0;
uint8_t benchRockLegIndex = 0;
// The local encoder ISR counts each valid edge in either direction, including
// backlash, coast and the two-second weighing dwell between attempts.
volatile bool measurePath = false, pathTripped = false;
volatile uint32_t pathCounts = 0;
volatile uint32_t pathLimit = C1_PATH_LIMIT;

static inline __attribute__((always_inline)) bool readPin(uint8_t pin) {
  return pin < 32 ? ((GPIO.in >> pin) & 1U) : ((GPIO.in1.val >> (pin - 32)) & 1U);
}

static inline __attribute__((always_inline)) void low(uint8_t pin) {
  if (pin < 32)
    GPIO.out_w1tc = uint32_t(1) << pin;
  else
    GPIO.out1_w1tc.val = uint32_t(1) << (pin - 32);
}

static inline __attribute__((always_inline)) void high(uint8_t pin) {
  if (pin < 32)
    GPIO.out_w1ts = uint32_t(1) << pin;
  else
    GPIO.out1_w1ts.val = uint32_t(1) << (pin - 32);
}

static inline __attribute__((always_inline)) int32_t forwardTravel(uint32_t raw) {
  // Subtraction in uint32_t also works when an encoder counter wraps through zero.
  return int32_t(sign > 0 ? raw - origin : origin - raw);
}

static inline __attribute__((always_inline)) void applyPwmLocked(uint32_t mask) {
  if (appliedMask == mask)
    return;
  GPIO.out_w1tc = appliedMask;
  GPIO.out_w1ts = mask;
  appliedMask = mask;
}

static inline __attribute__((always_inline)) void offLocked() {
  low(STBY);
  applyPwmLocked(0);
  low(DIR1);
  low(DIR2);
  duty = 0;
  selectedMask = 0;
  paceC1 = false;
}

static inline __attribute__((always_inline)) void stopAtTargetLocked(uint32_t raw) {
  const int32_t travel = forwardTravel(raw);
  if (armed && !expired && !pathTripped && !reached &&
      (rockLeg == ROCK_BACK ? travel <= targetTravel : travel >= targetTravel)) {
    if (rockLeg == NO_ROCK) {
      offLocked();
    } else {
      // TB6612 short brake: keep the selected direction and STBY high with PWM low.
      applyPwmLocked(0);
      selectedMask = 0;
      duty = 0;
      paceC1 = false;
    }
    reached = true;
  }
}

// EXTERNAL INTERRUPT / EVENT CHECKER: record a real A/B transition on motors 1–3.
void IRAM_ATTR onEncoder(void *arg) {
  Encoder &e = *static_cast<Encoder *>(arg);
  portENTER_CRITICAL_ISR(&ioLock);
  const uint8_t ab = (uint8_t(readPin(e.a)) << 1) | uint8_t(readPin(e.b));
  const int8_t step = quad[(e.last << 2) | ab];
  e.raw += step;
  e.last = ab;
  if (paceC1 && &e == &local[0]) {
    const int32_t signedStep = rockLeg == ROCK_BACK ? -step : step;
    const int32_t credit = paceCredit - signedStep * sign * TICKS_PER_SECOND;
    paceCredit = credit < -C1_MAX_LEAD ? -C1_MAX_LEAD : (credit > C1_MAX_CREDIT ? C1_MAX_CREDIT : credit);
  }
  if (localChannel < 3 && &e == &local[localChannel])
    stopAtTargetLocked(e.raw);
  if (measurePath && step && &e == &local[0]) {
    ++pathCounts;
    if (pathCounts > pathLimit || (pathCounts == pathLimit && !reached)) {
      pathTripped = true;
      offLocked();
    }
  }
  portEXIT_CRITICAL_ISR(&ioLock);
}

// TIMER INTERRUPT: pace canister 1 with its encoder, generate PWM and supervise the link.
void IRAM_ATTR onTimer() {
  portENTER_CRITICAL_ISR(&ioLock);
  if (armed && lease && --lease == 0) {
    expired = true;
    offLocked();
  }
  pwmStep = (pwmStep + 1) & 7;
  bool fullCruise = false;
  if (paceC1) {
    const int32_t travel = forwardTravel(local[0].raw);
    int32_t rate;
    if (rockLeg == NO_ROCK) {
      rate = targetTravel > 0 && travel >= targetTravel - C1_APPROACH_COUNTS ? C1_APPROACH_RATE : C1_CRUISE_RATE;
    } else if (edgeCreep) {
      rate = EDGE_CREEP_RATE;
    } else {
      const int32_t remaining = rockLeg == ROCK_BACK ? travel - targetTravel : targetTravel - travel;
      if (rampTicks < ROCK_RAMP_TICKS) ++rampTicks;
      const int32_t cruiseRate = fullSpeedRock ? ROCK2_RAMP_RATE : ROCK_CRUISE_RATE;
      const bool approaching = remaining <= rockApproachCounts;
      fullCruise = fullSpeedRock && !approaching && rampTicks == ROCK_RAMP_TICKS;
      rate = approaching ? ROCK_APPROACH_RATE :
             ROCK_APPROACH_RATE + (cruiseRate - ROCK_APPROACH_RATE) * rampTicks / ROCK_RAMP_TICKS;
    }
    const int32_t credit = paceCredit + rate;
    paceCredit = credit > C1_MAX_CREDIT ? C1_MAX_CREDIT : credit;
  }
  const bool drive = pwmStep < duty && (!paceC1 || fullCruise || paceCredit > 0);
  applyPwmLocked(drive ? selectedMask : 0);
  portEXIT_CRITICAL_ISR(&ioLock);
}

uint32_t readEncoder(uint8_t index) {
  if (index >= 3)
    return remote[index - 3];
  portENTER_CRITICAL(&ioLock);
  const uint32_t raw = local[index].raw;
  portEXIT_CRITICAL(&ioLock);
  return raw;
}

bool settingsValid(uint8_t i) {
  const Cartridge &w = CARTRIDGES[i];
  if (!w.enabled || !w.pocketsPerTurn || (w.forwardSign != 1 && w.forwardSign != -1))
    return false;
  const double pitch =
      COUNTS_PER_OUTPUT_TURN * w.gearboxOutputTurnsPerWheelTurn / w.pocketsPerTurn;
  return pitch >= 32 &&
         pitch <= 10000000; // guarantees enough resolution and bounded integer targets
}

uint8_t configuredMask() {
  uint8_t bits = 0;
  for (uint8_t i = 0; i < 6; i++)
    if (settingsValid(i) && !reference[i].inspection)
      bits |= 1U << i;
  return bits;
}

// SERVICE: stop the bridge, latch the reason and prevent an automatic retry of partial travel.
void fault(Fault why) {
  portENTER_CRITICAL(&ioLock);
  offLocked();
  armed = false;
  lease = 0;
  measurePath = false;
  portEXIT_CRITICAL(&ioLock);
  if (wheel && (status.phase == ADVANCING || status.phase == SPINNING || why == OVERRUN || why == ENCODER))
    reference[wheel - 1].inspection = true;
  if (status.phase != FAULT) {
    status.phase = FAULT;
    status.fault = why;
  }
}

// SERVICE: accept STOP. A partial job requires inspection and re-indexing before restarting.
void enterIdle(uint32_t job) {
  if (wheel && status.phase == ADVANCING)
    reference[wheel - 1].inspection = true;
  portENTER_CRITICAL(&ioLock);
  offLocked();
  armed = false;
  reached = false;
  expired = false;
  measurePath = false;
  pathTripped = false;
  rockLeg = NO_ROCK;
  lease = 0;
  localChannel = 3;
  portEXIT_CRITICAL(&ioLock);
  settling = false;
  wheel = 0;
  quantity = 0;
  activeCommand = 0;
  status.job = job;
  status.phase = IDLE;
  status.fault = NONE;
  status.indexed = 0;
  status.encoder = 0;
}

// Shared drive startup. Channel 3 bypasses the local encoder's indexed-stop interrupt.
void startDrive(uint8_t i, uint8_t channel, uint8_t speed, int32_t goal, RockLeg leg = NO_ROCK) {
  portENTER_CRITICAL(&ioLock);
  if ((armed && expired) || pathTripped) {
    portEXIT_CRITICAL(&ioLock);
    return; // retain the hardware cutoff until the foreground reports LINK_LOST
  }
  offLocked();
  if (measurePath) {
    const int32_t travel = forwardTravel(local[0].raw);
    const uint32_t remaining = uint32_t(goal > travel ? goal - travel : travel - goal);
    if (pathCounts >= pathLimit || remaining > pathLimit - pathCounts) {
      pathTripped = true;
      portEXIT_CRITICAL(&ioLock);
      return; // there is insufficient measured travel left for this leg
    }
  }
  targetTravel = goal;
  localChannel = channel;
  rockLeg = leg;
  edgeCreep = activeCommand == Link::EDGE;
  fullSpeedRock = activeCommand == Link::ROCK2;
  rockApproachCounts = activeCommand == Link::ROCK ? BENCH_ROCK_APPROACH_COUNTS : ROCK_APPROACH_COUNTS;
  if (fullSpeedRock)
    rockApproachCounts = ROCK2_APPROACH_COUNTS;
  rampTicks = 0;
  armed = true;
  reached = false;
  expired = false;
  lease = LEASE_TICKS;
  if (leg == ROCK_BACK) high(DIR2);
  else high(DIR1);
  selectedMask = uint32_t(1) << MOTOR_PWM[i];
  paceC1 = i == 0;
  paceCredit = 0;
  if (paceC1)
    pwmStep = 7; // start on the first pulse of a fresh PWM cycle
  duty = paceC1 && leg == NO_ROCK ? C1_MAX_DUTY : speed;
  high(STBY);
  portEXIT_CRITICAL(&ioLock);
}

// Establish the mechanical forward coordinate and start a fresh piece travel budget.
void beginNudgeOrigin(uint8_t i) {
  const uint32_t actual = readEncoder(i);
  portENTER_CRITICAL(&ioLock);
  origin = i == 0 ? local[0].raw : actual;
  sign = CARTRIDGES[i].forwardSign;
  measurePath = i == 0;
  pathLimit = Link::isBenchRock(activeCommand) ? benchRockPathLimit(activeCommand) : C1_PATH_LIMIT;
  pathCounts = 0;
  pathTripped = false;
  portEXIT_CRITICAL(&ioLock);
  reference[i].known = false;
}

// Every endpoint is relative to the same encoder origin, so coast cannot accumulate between legs.
void startRockLeg(RockLeg leg, int32_t goal, uint32_t now) {
  const int32_t travel = forwardTravel(readEncoder(0));
  lastTravel = progressMark = leg == ROCK_BACK ? -travel : travel;
  tolerance = ROCK_TOLERANCE_COUNTS;
  settling = false;
  lastProgress = now;
  status.phase = ADVANCING;
  const uint8_t rockDuty = activeCommand == Link::ROCK2 ? 8 : ROCK_MAX_DUTY;
  startDrive(0, 0, rockDuty, goal, leg);
}

void startBenchRockLeg(uint32_t now) {
  const double goalDegrees = Link::benchRockTargetDegrees(activeCommand, benchRockLegIndex);
  const double previousDegrees = benchRockLegIndex ? Link::benchRockTargetDegrees(activeCommand, benchRockLegIndex - 1) : 0;
  const RockLeg direction = goalDegrees < previousDegrees ? ROCK_BACK : ROCK_RETURN;
  startRockLeg(direction, int32_t(lround(C1_COUNTS_PER_DEGREE * goalDegrees)), now);
}

void startEdgeLeg(RockLeg direction, int32_t goal, uint32_t now) {
  const int32_t forward = forwardTravel(readEncoder(0));
  lastTravel = progressMark = direction == ROCK_BACK ? -forward : forward;
  edgeLegStarted = edgeWindowAt = lastProgress = now;
  edgeWindowTravel = lastTravel;
  edgeStoppingForBackoff = false;
  settling = false;
  tolerance = ROCK_TOLERANCE_COUNTS;
  status.phase = ADVANCING;
  startDrive(0, 0, C1_MAX_DUTY, goal, direction);
}

// This window measures net progress in the driven direction. Jitter alone cannot satisfy it.
void checkEdgeSlowdown(int32_t travel, uint32_t now) {
  if (now - edgeLegStarted < EDGE_STARTUP_MS) {
    edgeWindowTravel = travel;
    edgeWindowAt = now;
    return;
  }
  const uint32_t elapsed = now - edgeWindowAt;
  if (elapsed < EDGE_WINDOW_MS || now - edgeLegStarted < EDGE_STARTUP_MS + EDGE_WINDOW_MS)
    return;
  const int32_t progress = travel - edgeWindowTravel;
  edgeWindowTravel = travel;
  edgeWindowAt = now;
  if (int64_t(progress) * 100000 >= int64_t(EDGE_CREEP_RATE) * EDGE_MIN_SPEED_PERCENT * elapsed)
    return;
  // An encoder or timer interrupt may have already stopped this leg since the window was sampled.
  bool stalled = false;
  portENTER_CRITICAL(&ioLock);
  if (armed && !expired && !pathTripped && !reached) {
    stalled = rockLeg == ROCK_BACK || quantity == 2 || travel < EDGE_PROVE_COUNTS;
    if (stalled) {
      offLocked();
    } else {
      targetTravel = forwardTravel(local[0].raw);
      stopAtTargetLocked(local[0].raw);
      edgeStoppingForBackoff = true;
    }
  }
  portEXIT_CRITICAL(&ioLock);
  if (stalled)
    fault(STALL);
}

// SERVICE: all nudge endpoints for this piece use the same encoder origin. A small
// amount of coast on one move therefore shortens the following move automatically.
void startNudge(uint8_t ordinal, uint32_t now) {
  const uint8_t i = wheel - 1;
  const Cartridge &w = CARTRIDGES[i];
  const double countsPerDegree = COUNTS_PER_OUTPUT_TURN * w.gearboxOutputTurnsPerWheelTurn / 360.0;
  if (ordinal == 1) beginNudgeOrigin(i);
  const int32_t travel = forwardTravel(readEncoder(i));
  if (ordinal > 1 && (travel < targetTravel - tolerance || travel > targetTravel + tolerance)) {
    fault(OVERRUN);
    return;
  }
  quantity = ordinal;
  jobStarted = now;
  if (i == 0 && ordinal == Link::ROCK_NUDGE_ORDINAL) {
    rockReturnTarget = targetTravel; // return to the initial 60-degree endpoint
    startRockLeg(ROCK_BACK, rockReturnTarget - ROCK_COUNTS, now);
    return;
  }
  const unsigned degrees = activeCommand == Link::JOG ? Link::NUDGE_DEGREES :
                           Link::forwardTargetDegrees(wheel, ordinal);
  const int32_t goal = int32_t(lround(countsPerDegree * degrees));
  tolerance = int32_t(ceil(countsPerDegree * NUDGE_TOLERANCE_DEGREES));
  lastTravel = progressMark = travel;
  lastProgress = now;
  settling = false;
  status.phase = ADVANCING;
  startDrive(i, i < 3 ? i : 3, NUDGE_DUTY, goal);
}

// SERVICE: validate a new job before the selected wheel receives power.
void startJob(const Link::Control &c, uint32_t now) {
  highestJob = c.job;
  status.job = c.job;
  status.indexed = 0;
  status.fault = NONE;
  if (!timerReady) {
    fault(TIMED_OUT);
    return;
  }
  const bool spin = c.command == 3;
  const bool nudge = c.command == Link::NUDGE;
  const bool rock = Link::isBenchRock(c.command);
  const bool jog = c.command == Link::JOG;
  const bool step = c.command == 1;
  if (c.wheel < 1 || c.wheel > 6 || (spin && (c.wheel != 1 || c.qty != 0)) ||
      ((rock || jog || c.command == Link::EDGE) && (c.wheel != 1 || c.qty != 1)) || (nudge && c.qty != 1) ||
      (step && (c.qty < 1 || c.qty > 6 || (c.wheel == 1 && c.qty != 1)))) {
    fault(ABORTED);
    return;
  }
  wheel = c.wheel;
  quantity = c.qty;
  activeCommand = c.command;
  const uint8_t i = wheel - 1;
  if (!(configuredMask() & (1U << i))) {
    fault(SETUP_REQUIRED);
    return;
  }
  if (nudge || jog) {
    startNudge(1, now);
    return;
  }
  if (activeCommand == Link::EDGE) {
    beginNudgeOrigin(0);
    jobStarted = now;
    startEdgeLeg(ROCK_RETURN, EDGE_GOAL_COUNTS, now);
    return;
  }
  if (rock) {
    beginNudgeOrigin(0);
    benchRockLegIndex = 0;
    jobStarted = now;
    startBenchRockLeg(now);
    return;
  }
  const Cartridge &w = CARTRIDGES[i];
  Reference &ref = reference[i];
  const uint32_t actual = readEncoder(i);
  if (spin) {
    ref.known = false;  // An unindexed stop establishes no physical pocket alignment.
    spinProgressRaw = actual;
    sign = w.forwardSign;
    lastProgress = now;
    status.phase = SPINNING;
    startDrive(i, 3, C1_MAX_DUTY, 0);
    return;
  }
  if (!ref.known) {
    ref.lastGoal = actual;
    ref.fraction = 0;
    ref.known = true;
  }
  // C1's empty-wheel STEP spans 60 degrees, independent of its three physical
  // pockets. Other wheels still index by pocket. Carry previous coast and rounding.
  const double pitch = i == 0 ? C1_COUNTS_PER_DEGREE * Link::STEP_DEGREES :
                                COUNTS_PER_OUTPUT_TURN * w.gearboxOutputTurnsPerWheelTurn / w.pocketsPerTurn;
  for (uint8_t n = 0; n < quantity; n++)
    pocketMark[n] = int32_t(lround(pitch * (n + 1) + ref.fraction));
  nextFraction = pitch * quantity + ref.fraction - pocketMark[quantity - 1];
  tolerance = int32_t(ceil(pitch * MAX_OVERSHOOT_POCKETS));
  slowZone = int32_t(ceil(pitch * 0.25));
  sign = w.forwardSign;
  origin = ref.lastGoal;
  lastTravel = forwardTravel(actual);
  progressMark = lastTravel;
  if (lastTravel < -tolerance || lastTravel > tolerance) {
    fault(OVERRUN);
    return;
  }
  jobStarted = now;
  lastProgress = now;
  settling = false;
  status.phase = ADVANCING;
  startDrive(i, i < 3 ? i : 3, RUN_DUTY, pocketMark[quantity - 1]);
}

void updateMotion(uint32_t now);

void renewDriveLease() {
  portENTER_CRITICAL(&ioLock);
  if (armed && !expired) {
    lease = LEASE_TICKS;
    if (wheel > 3)
      stopAtTargetLocked(remote[wheel - 4]);
  }
  portEXIT_CRITICAL(&ioLock);
}

// EVENT CHECKER / DISPATCH: validate the session, job identity and remote encoder sample.
void control(const Link::Control &c, uint32_t now) {
  if (!c.session)
    return;
  if (c.session != status.session) {
    enterIdle(c.job);
    highestJob = 0;
    handshake = false;
    status.session = c.session;
    // A reboot of the display resets its three incremental encoders.
    for (uint8_t i = 3; i < 6; i++)
      reference[i].known = false;
  }
  for (uint8_t i = 0; i < 3; i++)
    remote[i] = uint32_t(c.encoder[i]);
  if (c.command == 0 || c.command == 2) {
    enterIdle(c.job);
    handshake = (c.command == 0);
    return;
  }
  if ((c.command != 1 && c.command != 3 && c.command != Link::NUDGE &&
       !Link::isBenchRock(c.command) && c.command != Link::JOG && c.command != Link::EDGE) ||
      !handshake || !c.job) {
    if (c.job > highestJob)
      highestJob = c.job;
    if (!wheel)
      status.job = c.job;
    fault(ABORTED);
    return;
  }
  if (status.phase == IDLE) {
    if (c.job > highestJob)
      startJob(c, now);
    return;
  }
  if (activeCommand == Link::EDGE && c.command == Link::EDGE) {
    if (c.job < status.job || (c.job == status.job && c.qty == 1 && quantity == 2))
      return;
    if (c.job == status.job && c.wheel == wheel && quantity == 1 && c.qty == 2 &&
        status.phase == DONE && status.indexed == Link::EDGE_BACKED_OFF) {
      updateMotion(now); // Check stopped position, remaining travel, and the original drive lease.
      if (status.phase != DONE)
        return;
      if (now - nudgeDoneAt < Link::NUDGE_WAIT_MS) {
        renewDriveLease();
        return;
      }
      quantity = 2;
      startEdgeLeg(ROCK_RETURN, EDGE_GOAL_COUNTS, now);
      return;
    }
  }
  // EVENT CHECKER: a settled nudge is held until the display requests one new
  // ordinal or explicitly starts the next piece. Repeated UART packets are heartbeats.
  if (activeCommand == Link::NUDGE && c.command == Link::NUDGE) {
    if (c.job < status.job || (c.job == status.job && c.qty > 0 && c.qty < quantity))
      return; // ignore stale commands without refreshing the watchdog
    const bool nextPiece = c.job > highestJob && c.qty == 1;
    const bool nextNudge = c.job == status.job && c.qty == quantity + 1 && c.qty <= Link::maxAttempts(wheel);
    if (status.phase == DONE && c.wheel == wheel && (nextNudge || nextPiece)) {
      // Check the previous stopped position and lease before rearming the bridge.
      // A delayed receive after an ISR cutoff must never clear the cutoff.
      updateMotion(now);
      if (status.phase != DONE)
        return;
      if (now - nudgeDoneAt < Link::NUDGE_WAIT_MS) {
        renewDriveLease(); // legitimate request, still held off for the full dwell
        return;
      }
      if (nextPiece)
        startJob(c, now);
      else
        startNudge(c.qty, now);
      return;
    }
  }
  if (c.job != status.job || c.command != activeCommand ||
      (wheel && (wheel != c.wheel || quantity != c.qty))) {
    if (c.job > highestJob)
      highestJob = c.job;
    fault(ABORTED);
    handshake = false;
    return;
  }
  renewDriveLease();
}

// EVENT CHECKER: target angle reached, feedback inconsistent, clock expired or wheel stalled.
// SERVICE: slow near the target, stop and allow the wheel to settle before reporting DONE.
void updateMotion(uint32_t now) {
  if (status.phase == SPINNING) {
    const uint32_t raw = readEncoder(0);
    status.encoder = int32_t(raw);
    // Measure short intervals so a continuously running encoder may wrap freely.
    const int32_t advance = int32_t(sign > 0 ? raw - spinProgressRaw : spinProgressRaw - raw);
    if (expired)
      fault(LINK_LOST);
    else if (advance < -64 || advance > 2500)
      fault(ENCODER);
    else if (advance >= 8) {
      spinProgressRaw = raw;
      lastProgress = now;
    } else if (now - lastProgress >= NO_PROGRESS_MS)
      fault(STALL);
    return;
  }
  if (status.phase != ADVANCING && status.phase != DONE)
    return;
  const uint32_t raw = readEncoder(wheel - 1);
  status.encoder = int32_t(raw);
  const bool reverse = rockLeg == ROCK_BACK;
  const bool rocking = rockLeg != NO_ROCK;
  const int32_t travel = reverse ? -forwardTravel(raw) : forwardTravel(raw);
  const int32_t goal = reverse ? -targetTravel : targetTravel;
  portENTER_CRITICAL(&ioLock);
  stopAtTargetLocked(raw); // also handles local changes since the previous foreground pass
  const bool lost = expired, atTarget = reached, exhausted = pathTripped;
  const uint32_t measuredPath = pathCounts;
  portEXIT_CRITICAL(&ioLock);
  if (lost) {
    fault(LINK_LOST);
    return;
  }
  if (exhausted) {
    fault(OVERRUN);
    return;
  }
  if (travel < progressMark - (rocking ? ROCK_TOLERANCE_COUNTS : 64) || int64_t(travel) - lastTravel > 2500) {
    fault(ENCODER);
    return;
  }
  lastTravel = travel;
  const bool nudge = activeCommand == Link::NUDGE;
  if (activeCommand == 1) {
    while (status.indexed < quantity && travel >= pocketMark[status.indexed])
      ++status.indexed;
  }
  // C1's two attempts travel 90 degrees gross; its separate encoder path budget remains active.
  const bool finalFullTravel = wheel != 1 && nudge && quantity == Link::MAX_NUDGES;
  const int32_t forwardLimit = goal + (finalFullTravel ? 0 : tolerance);
  const bool edge = activeCommand == Link::EDGE;
  if (travel > forwardLimit || (edge && status.phase == DONE && travel < goal - tolerance)) {
    fault(OVERRUN);
    return;
  }
  if (status.phase == DONE)
    return;
  if (now - jobStarted >= MAX_JOB_MS) {
    fault(TIMED_OUT);
    return;
  }
  if (atTarget) {
    if (!settling) {
      settling = true;
      stoppedAt = now;
      settledTravel = travel;
      settledPath = measuredPath;
    }
    if (travel < goal - tolerance) {
      fault(ENCODER);
      return;
    }
    // Count actual travel during coast. Require a quiet interval, including remote sample
    // latency.
    if (travel != settledTravel || (rocking && measuredPath != settledPath)) {
      stoppedAt = now;
      settledTravel = travel;
      settledPath = measuredPath;
    }
    uint32_t quietTime = nudge && reverse ? Link::ROCK_HOLD_MS : STOP_SETTLE_MS;
    if (edge && reverse)
      quietTime = Link::EDGE_QUIET_MS;
    if (now - stoppedAt >= quietTime) {
      if (edge && edgeStoppingForBackoff) {
        startEdgeLeg(ROCK_BACK, forwardTravel(readEncoder(0)) - EDGE_BACKOFF_COUNTS, now);
        return;
      }
      if (Link::isBenchRock(activeCommand) && benchRockLegIndex + 1 < Link::BENCH_ROCK_LEGS) {
        ++benchRockLegIndex;
        startBenchRockLeg(now);
        return;
      }
      if (nudge && reverse) {
        startRockLeg(ROCK_RETURN, rockReturnTarget, now);
        return;
      }
      if (rocking) {
        portENTER_CRITICAL(&ioLock);
        offLocked(); // release the short brake after the wheel is stationary
        portEXIT_CRITICAL(&ioLock);
      }
      if (nudge || edge) {
        nudgeDoneAt = now;
      } else if (activeCommand == 1) {
        Reference &ref = reference[wheel - 1];
        ref.lastGoal =
            sign > 0 ? origin + uint32_t(targetTravel) : origin - uint32_t(targetTravel);
        ref.fraction = nextFraction;
      }
      status.phase = DONE;
      status.indexed = edge ? (reverse ? Link::EDGE_BACKED_OFF : Link::EDGE_FINISHED) : quantity;
    }
    return;
  }
  if (travel - progressMark >= 8) {
    progressMark = travel;
    lastProgress = now;
  }
  if (edge) {
    checkEdgeSlowdown(travel, now);
    return;
  }
  if (now - lastProgress >= (rocking ? ROCK_NO_PROGRESS_MS : NO_PROGRESS_MS)) {
    fault(STALL);
    return;
  }
  if (wheel != 1 && !nudge && targetTravel - travel <= slowZone) {
    portENTER_CRITICAL(&ioLock);
    if (armed && !reached && !expired)
      duty = APPROACH_DUTY;
    portEXIT_CRITICAL(&ioLock);
  }
}

void begin() {
  low(STBY);
  pinMode(STBY, OUTPUT);
  for (uint8_t pin : {DIR1, DIR2}) {
    low(pin);
    pinMode(pin, OUTPUT);
  }
  for (uint8_t pin : MOTOR_PWM) {
    low(pin);
    pinMode(pin, OUTPUT);
  }
  Serial.begin(115200);
  Serial2.begin(115200, SERIAL_8N1, UART_RX, UART_TX);
  for (size_t i = 0; i < 3; ++i) {
    if (!CARTRIDGES[i].enabled)
      continue; // Leave absent encoders disconnected during staged installation.
    Encoder &e = local[i];
    pinMode(e.a, INPUT);
    pinMode(e.b, INPUT);
    e.last = (uint8_t(readPin(e.a)) << 1) | uint8_t(readPin(e.b));
    attachInterruptArg(e.a, onEncoder, &e, CHANGE);
    attachInterruptArg(e.b, onEncoder, &e, CHANGE);
  }
  hw_timer_t *timer = timerBegin(1000000);
  if (timer) {
    timerAttachInterrupt(timer, onTimer);
    timerAlarm(timer, TICK_US, true, 0);
    timerReady = true;
  }
  Serial.printf("Motion controller. Enabled wheel mask 0x%02X. Motor timer %s.\n",
                configuredMask(), timerReady ? "ready" : "FAILED");
}

void run() {
  const uint32_t now = millis();
  Link::Control c;
  for (uint8_t n = 0; n < 8 && Link::receive(Serial2, c); n++) {
    control(c, now);
    updateMotion(now);
  }
  updateMotion(now);
  status.configuredMask = configuredMask();
  static uint8_t oldPhase = 255, oldFault = 255, oldCount = 255, oldMask = 255;
  if (oldPhase != status.phase || oldFault != status.fault || oldCount != status.indexed ||
      oldMask != status.configuredMask) {
    oldPhase = status.phase;
    oldFault = status.fault;
    oldCount = status.indexed;
    oldMask = status.configuredMask;
    Serial.printf("job=%lu wheel=%u phase=%u indexed=%u fault=%u enabled=0x%02X\n",
                  (unsigned long)status.job, wheel, status.phase, status.indexed, status.fault,
                  status.configuredMask);
    Link::send(Serial2, status);
    lastStatus = now;
  } else if (now - lastStatus >= STATUS_MS) {
    Link::send(Serial2, status);
    lastStatus = now;
  }
}
}

void setup() {
  Motion::begin();
}
void loop() {
  Motion::run();
}
