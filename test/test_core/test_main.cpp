// Unit tests for lib/dispenser_core (host, Unity). Run: pio test -e native
#include <math.h>
#include <unity.h>

#include "../sim_plant.h"
#include "dc_config.h"
#include "dispenser.h"
#include "mechanism.h"
#include "menu.h"
#include "motion.h"
#include "schedule.h"
#include "sim_motor.h"
#include "verify.h"

using namespace dc;

void setUp() {}
void tearDown() {}

static uint32_t hm(int h, int m, int s = 0, uint32_t day = 20000) {
  return day * 86400UL + h * 3600UL + m * 60UL + s;
}

// ------------------------------------------------------------ motion profile
void test_counts_per_rev_matches_motor_test() {
  TEST_ASSERT_DOUBLE_WITHIN(0.01, 11836.88, kCountsPerRev);
  TEST_ASSERT_EQUAL_INT32(3946, degToCounts(120.0f));
  TEST_ASSERT_EQUAL_INT32(-986, degToCounts(-30.0f));
}

void test_trapezoid_endpoints_and_duration() {
  TrapezoidProfile p;
  const float D = static_cast<float>(degToCounts(MECH_INDEX_DEG));
  const float v = rpmToCountsPerMs(MECH_TARGET_RPM);
  p.plan(D, v, MECH_ACCEL_MS);
  const float expected = MECH_INDEX_DEG / (6.0f * MECH_TARGET_RPM) * 1000.0f + MECH_ACCEL_MS;
  TEST_ASSERT_FLOAT_WITHIN(2.0f, expected, p.durationMs());
  TEST_ASSERT_FLOAT_WITHIN(0.01f, 0.0f, p.position(0));
  TEST_ASSERT_FLOAT_WITHIN(0.01f, D, p.position(p.durationMs()));
  TEST_ASSERT_FLOAT_WITHIN(0.01f, D, p.position(p.durationMs() + 100));
  TEST_ASSERT_FLOAT_WITHIN(1e-3f, v, p.velocity(p.durationMs() / 2));
  TEST_ASSERT_FLOAT_WITHIN(1e-3f, v / 2, p.velocity(MECH_ACCEL_MS / 2.0f));
  TEST_ASSERT_FLOAT_WITHIN(0.5f, D / 2, p.position(p.durationMs() / 2));  // symmetric
}

void test_trapezoid_short_move_is_triangle() {
  TrapezoidProfile p;
  const float v = rpmToCountsPerMs(20.0f);
  p.plan(-100.0f, v, 150.0f);  // 100 counts < v * 150 ms
  TEST_ASSERT_TRUE(fabsf(p.peakVelocity()) < v);
  TEST_ASSERT_FLOAT_WITHIN(0.01f, -100.0f, p.position(p.durationMs()));
  TEST_ASSERT_FLOAT_WITHIN(0.5f, -50.0f, p.position(p.durationMs() / 2));
}

// Index move with the closed-loop controller on the simulated gearmotor.
static MoveResult runMove(SimMotor& m, MoveController& mc, int32_t target, uint32_t& tEnd,
                          uint32_t limitMs = 5000) {
  float vel = 0;
  int32_t last = m.count();
  float duty = 0;
  mc.start(0, m.count(), target, rpmToCountsPerMs(MECH_TARGET_RPM), MECH_ACCEL_MS,
           MECH_JAM_MIN_SPEED_FRAC, MECH_JAM_STALL_MS);
  for (uint32_t t = 0; t < limitMs; ++t) {
    if (t % cfg::kControlPeriodMs == 0 && t > 0) {
      const int32_t c = m.count();
      vel += cfg::kVelFilterAlpha * ((c - last) / float(cfg::kControlPeriodMs) - vel);
      last = c;
      duty = mc.update(t, c, vel);
      if (!mc.active()) {
        tEnd = t;
        return mc.result();
      }
    }
    m.step(1.0f, duty, true, false);
  }
  tEnd = limitMs;
  return mc.result();
}

void test_index_move_reaches_target_counts() {
  SimMotor m;
  MoveController mc;
  const int32_t target = degToCounts(MECH_INDEX_DEG);
  uint32_t tEnd = 0;
  TEST_ASSERT_EQUAL(static_cast<int>(MoveResult::Done), static_cast<int>(runMove(m, mc, target, tEnd)));
  TEST_ASSERT_INT32_WITHIN(degToCounts(cfg::kPosTolDeg), target, m.count());
  const float expected = MECH_INDEX_DEG / (6.0f * MECH_TARGET_RPM) * 1000.0f + MECH_ACCEL_MS;
  TEST_ASSERT_FLOAT_WITHIN(0.10f * expected, expected, float(tEnd));
  // Brake and let it coast out: still within tolerance.
  for (int i = 0; i < 200; ++i) m.step(1.0f, 0, true, true);
  TEST_ASSERT_INT32_WITHIN(degToCounts(cfg::kPosTolDeg) * 2, target, m.count());
}

void test_reverse_move_reaches_target() {
  SimMotor m;
  MoveController mc;
  uint32_t tEnd = 0;
  const int32_t target = -degToCounts(MECH_REVERSE_DEG);
  TEST_ASSERT_EQUAL(static_cast<int>(MoveResult::Done), static_cast<int>(runMove(m, mc, target, tEnd)));
  TEST_ASSERT_INT32_WITHIN(degToCounts(cfg::kPosTolDeg), target, m.count());
}

void test_stall_detector_timing() {
  StallDetector s;
  s.configure(1.0f, 300);
  TEST_ASSERT_FALSE(s.update(0, true, 0.5f));
  TEST_ASSERT_FALSE(s.update(299, true, 0.5f));
  TEST_ASSERT_TRUE(s.update(300, true, 0.5f));
  s.reset();
  TEST_ASSERT_FALSE(s.update(1000, true, 0.5f));
  TEST_ASSERT_FALSE(s.update(1200, true, 2.0f));  // recovered -> timer restarts
  TEST_ASSERT_FALSE(s.update(1250, true, 0.5f));
  TEST_ASSERT_FALSE(s.update(1500, true, 0.5f));
  TEST_ASSERT_TRUE(s.update(1550, true, 0.5f));
  s.reset();
  TEST_ASSERT_FALSE(s.update(2000, false, 0.0f));  // disarmed (ramp tails) never stalls
  TEST_ASSERT_FALSE(s.update(5000, false, 0.0f));
  TEST_ASSERT_FALSE(s.update(5001, true, -3.0f));  // wrong way counts as slow
  TEST_ASSERT_TRUE(s.update(5301, true, -3.0f));
}

void test_move_controller_detects_stall() {
  SimMotor m;
  m.load = 3.0f;  // locked rotor
  MoveController mc;
  uint32_t tEnd = 0;
  TEST_ASSERT_EQUAL(static_cast<int>(MoveResult::Stalled),
                    static_cast<int>(runMove(m, mc, degToCounts(MECH_INDEX_DEG), tEnd)));
  // Armed once the reference passes 10 % of target speed (~15 ms), then 300 ms.
  TEST_ASSERT_UINT32_WITHIN(30, MECH_JAM_STALL_MS + 15, tEnd);
}

void test_move_controller_wrong_direction() {
  SimMotor m;
  MoveController mc;
  mc.start(0, 0, 4000, rpmToCountsPerMs(20), 150, 0.1f, 300);
  float duty = 0, vel = 0;
  int32_t last = 0;
  MoveResult r = MoveResult::Running;
  for (uint32_t t = 1; t < 3000 && mc.active(); ++t) {
    m.step(1.0f, duty, true, false);
    if (t % 5 == 0) {
      const int32_t c = -m.count();  // encoder reversed
      vel += 0.35f * ((c - last) / 5.0f - vel);
      last = c;
      duty = mc.update(t, c, vel);
      r = mc.result();
    }
  }
  TEST_ASSERT_EQUAL(static_cast<int>(MoveResult::WrongDirection), static_cast<int>(r));
}

// ------------------------------------------------------------ jam sequence (state machine)
void test_jam_reverse_retry_then_fault() {
  simt::Plant p;
  p.begin();
  TEST_ASSERT_TRUE(p.runUntilState(State::Idle, 5000));
  p.jamArmed = true;
  p.clearAfterReverses = -1;  // never clears
  p.jamAtPos = p.disp.indexPosition() + 0.3 * degToCounts(MECH_INDEX_DEG);
  p.in.requestDispense = true;
  TEST_ASSERT_TRUE(p.runUntilState(State::Dispensing, 100));
  // Record the phase sequence.
  std::vector<DispensePhase> seq;
  bool done = p.runUntil(
      [&] {
        if (p.disp.state() == State::Dispensing &&
            (seq.empty() || seq.back() != p.disp.dispensePhase()))
          seq.push_back(p.disp.dispensePhase());
        return p.disp.state() == State::Fault;
      },
      20000);
  TEST_ASSERT_TRUE(done);
  TEST_ASSERT_EQUAL(static_cast<int>(FaultCode::Jam), static_cast<int>(p.disp.fault()));
  TEST_ASSERT_EQUAL_UINT32(1u + MECH_MAX_RETRIES, p.disp.jamEvents());
  TEST_ASSERT_EQUAL_UINT32(MECH_MAX_RETRIES, p.disp.reverseMoves());
  // Baseline, then (Forward, JamBrake, Reverse, ReverseBrake) x retries, Forward, JamBrake.
  std::vector<DispensePhase> want = {DispensePhase::Baseline};
  for (int i = 0; i < MECH_MAX_RETRIES; ++i) {
    want.push_back(DispensePhase::Forward);
    want.push_back(DispensePhase::JamBrake);
    want.push_back(DispensePhase::Reverse);
    want.push_back(DispensePhase::ReverseBrake);
  }
  want.push_back(DispensePhase::Forward);
  want.push_back(DispensePhase::JamBrake);
  TEST_ASSERT_EQUAL(want.size(), seq.size());
  for (size_t i = 0; i < want.size(); ++i)
    TEST_ASSERT_EQUAL(static_cast<int>(want[i]), static_cast<int>(seq[i]));
  // Motor is off in FAULT and the screen says so.
  for (int i = 0; i < 300; ++i) p.step();
  TEST_ASSERT_FALSE(p.out.motorEnable);
  TEST_ASSERT_EQUAL_STRING("FAULT", p.disp.view().title);
  TEST_ASSERT_EQUAL_STRING("JAM", p.disp.view().line[0]);
}

// ------------------------------------------------------------ verification
void test_classify_ok_double_miss() {
  const float m = MECH_PILL_MASS_G_MIN;
  TEST_ASSERT_EQUAL(int(Verdict::Ok), int(classifyDispense(1, true, m, m)));
  TEST_ASSERT_EQUAL(int(Verdict::Ok), int(classifyDispense(1, true, 0.3f, m)));
  TEST_ASSERT_EQUAL(int(Verdict::OkBeamOnly), int(classifyDispense(1, false, 0.0f, m)));
  TEST_ASSERT_EQUAL(int(Verdict::Double), int(classifyDispense(2, true, 0.5f, m)));
  TEST_ASSERT_EQUAL(int(Verdict::Double), int(classifyDispense(3, false, 0.0f, m)));
  TEST_ASSERT_EQUAL(int(Verdict::Miss), int(classifyDispense(0, true, 0.01f, m)));
  TEST_ASSERT_EQUAL(int(Verdict::Miss), int(classifyDispense(0, false, 0.0f, m)));
  TEST_ASSERT_EQUAL(int(Verdict::SensorMismatch), int(classifyDispense(0, true, 0.2f, m)));
  TEST_ASSERT_EQUAL(int(Verdict::SensorMismatch), int(classifyDispense(1, true, 0.02f, m)));
}

// ------------------------------------------------------------ schedule
void test_schedule_next_dose_and_midnight_rollover() {
  Schedule s;
  s.minuteOfDay[0] = 7 * 60;
  s.minuteOfDay[1] = 23 * 60 + 30;
  uint32_t when = 0;
  int slot = -1;
  TEST_ASSERT_TRUE(s.nextAfter(hm(12, 0), when, slot));
  TEST_ASSERT_EQUAL_UINT32(hm(23, 30), when);
  TEST_ASSERT_EQUAL(1, slot);
  TEST_ASSERT_TRUE(s.nextAfter(hm(23, 45), when, slot));  // past the last dose today
  TEST_ASSERT_EQUAL_UINT32(hm(7, 0, 0, 20001), when);     // -> tomorrow 07:00
  TEST_ASSERT_EQUAL(0, slot);
  TEST_ASSERT_TRUE(s.nextAfter(hm(7, 0), when, slot));    // strictly after
  TEST_ASSERT_EQUAL_UINT32(hm(23, 30), when);
}

void test_schedule_due_across_midnight() {
  Schedule s;
  s.minuteOfDay[2] = 0;  // 00:00
  uint32_t when = 0;
  int slot = -1;
  TEST_ASSERT_TRUE(s.dueBetween(hm(23, 59, 30), hm(0, 0, 30, 20001), when, slot));
  TEST_ASSERT_EQUAL_UINT32(hm(0, 0, 0, 20001), when);
  TEST_ASSERT_EQUAL(2, slot);
  TEST_ASSERT_FALSE(s.dueBetween(hm(0, 0, 0, 20001), hm(0, 0, 30, 20001), when, slot));  // exclusive
  TEST_ASSERT_FALSE(s.dueBetween(hm(10, 0), hm(10, 0), when, slot));
}

void test_schedule_disabled_and_sanitize() {
  Schedule s;
  uint32_t when = 0;
  int slot = -1;
  TEST_ASSERT_EQUAL(0, s.enabledCount());
  TEST_ASSERT_FALSE(s.nextAfter(hm(1, 0), when, slot));
  s.minuteOfDay[0] = 5000;  // corrupted NVS value
  s.minuteOfDay[1] = 600;
  s.sanitize();
  TEST_ASSERT_EQUAL(kDoseOff, s.minuteOfDay[0]);
  TEST_ASSERT_EQUAL(1, s.enabledCount());
  char buf[8];
  formatMinuteOfDay(s.minuteOfDay[1], buf, sizeof buf);
  TEST_ASSERT_EQUAL_STRING("10:00", buf);
  formatMinuteOfDay(kDoseOff, buf, sizeof buf);
  TEST_ASSERT_EQUAL_STRING("OFF", buf);
}

// ------------------------------------------------------------ menu input
void test_pot_menu_hysteresis() {
  PotSelector p;
  p.reset(4, 0);  // bins of 1024, hysteresis 256
  TEST_ASSERT_EQUAL(0, p.index());
  // Noise around the 0/1 edge (1024) does not change the selection.
  const int noisy[] = {1000, 1030, 1100, 1010, 1200, 1270, 1150};
  for (int r : noisy) TEST_ASSERT_EQUAL(0, p.update(r));
  TEST_ASSERT_EQUAL(1, p.update(1281));  // 1024 + 256 + margin
  for (int r : {1000, 900, 800, 1024}) TEST_ASSERT_EQUAL(1, p.update(r));
  TEST_ASSERT_EQUAL(0, p.update(760));  // 1024 - 256 - margin
  TEST_ASSERT_EQUAL(3, p.update(4095)); // big jumps go straight there
  TEST_ASSERT_EQUAL(3, p.update(5000)); // clamped
  TEST_ASSERT_EQUAL(0, p.update(-10));
}

void test_pot_menu_full_range_maps_all_items() {
  PotSelector p;
  p.reset(97, 0);
  TEST_ASSERT_EQUAL(0, p.index());
  TEST_ASSERT_EQUAL(96, p.update(4095));
  p.reset(7, 2048);
  TEST_ASSERT_EQUAL(3, p.index());
}

void test_debouncer() {
  Debouncer d(30);
  d.reset(false, 0);
  TEST_ASSERT_FALSE(d.update(1, true));
  TEST_ASSERT_FALSE(d.update(10, false));  // bounce
  TEST_ASSERT_FALSE(d.update(12, true));
  TEST_ASSERT_FALSE(d.update(41, true));
  TEST_ASSERT_TRUE(d.update(42, true));    // stable 30 ms -> one press
  TEST_ASSERT_FALSE(d.update(100, true));
  TEST_ASSERT_FALSE(d.update(200, false));
  TEST_ASSERT_FALSE(d.update(231, false)); // release is not a press
  TEST_ASSERT_FALSE(d.stable());
}

int main() {
  UNITY_BEGIN();
  RUN_TEST(test_counts_per_rev_matches_motor_test);
  RUN_TEST(test_trapezoid_endpoints_and_duration);
  RUN_TEST(test_trapezoid_short_move_is_triangle);
  RUN_TEST(test_index_move_reaches_target_counts);
  RUN_TEST(test_reverse_move_reaches_target);
  RUN_TEST(test_stall_detector_timing);
  RUN_TEST(test_move_controller_detects_stall);
  RUN_TEST(test_move_controller_wrong_direction);
  RUN_TEST(test_jam_reverse_retry_then_fault);
  RUN_TEST(test_classify_ok_double_miss);
  RUN_TEST(test_schedule_next_dose_and_midnight_rollover);
  RUN_TEST(test_schedule_due_across_midnight);
  RUN_TEST(test_schedule_disabled_and_sanitize);
  RUN_TEST(test_pot_menu_hysteresis);
  RUN_TEST(test_pot_menu_full_range_maps_all_items);
  RUN_TEST(test_debouncer);
  return UNITY_END();
}
