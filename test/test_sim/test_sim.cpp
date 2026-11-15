// Host-side simulation of the whole dispenser: the real state machine
// (lib/dispenser_core) drives a first-order gearmotor model with an encoder,
// a home switch, pills falling through the beam and an HX711 load cell.
// Scenarios follow the mechanism contract's index loop: up to
// MECH_MAX_INDEX_STEPS pocket moves, stop at the first step that drops a pill.
// Covered: pill on step 1 / step 3, none after max steps, double on one
// step, stall mid-loop (recovered and not), schedule, reboot, menu.
#include <math.h>
#include <stdio.h>
#include <unity.h>

#include "../sim_plant.h"

using namespace dc;

void setUp() {}
void tearDown() {}

namespace ex = simt::expect;
static float expectedMoveMs() { return ex::indexMoveMs(); }

static void homeAndIdle(simt::Plant& p) {
  p.begin();
  const uint32_t t0 = p.nowMs;
  TEST_ASSERT_TRUE_MESSAGE(p.runUntilState(State::Idle, 6000), "homing did not finish");
  TEST_ASSERT_TRUE(p.disp.homed());
  // Home switch at 61 deg, sought at cfg::kHomeRpm (deg/s = 6 * rpm).
  const float homeMs = 61.0f / (6.0f * cfg::kHomeRpm) * 1000.0f;
  TEST_ASSERT_FLOAT_WITHIN(0.2f * homeMs + 300.0f, homeMs + 300.0f, float(p.nowMs - t0));
  TEST_ASSERT_INT32_WITHIN(degToCounts(1.0f), p.homeAt, p.disp.indexPosition());
}

static void dispenseNow(simt::Plant& p) {
  p.in.requestDispense = true;
  TEST_ASSERT_TRUE(p.runUntilState(State::Dispensing, 50));
}

void test_normal_dispense_timing() {
  simt::Plant p;
  homeAndIdle(p);
  const int32_t start = p.disp.indexPosition();
  const uint32_t t0 = p.nowMs;
  dispenseNow(p);
  TEST_ASSERT_TRUE(p.runUntilState(State::WaitPickup, ex::limit(ex::dispenseMs(1))));
  const uint32_t total = p.nowMs - t0;
  const float move = float(p.disp.lastForwardMoveMs());
  printf("normal: move %.0f ms (expected %.0f), dispense->pickup %u ms\n", move, expectedMoveMs(),
         total);
  TEST_ASSERT_FLOAT_WITHIN(0.10f * expectedMoveMs(), expectedMoveMs(), move);
  // baseline weigh + max(move + settle, drop window) + after-weigh.
  TEST_ASSERT_FLOAT_WITHIN(0.1f * ex::dispenseMs(1) + 150, ex::dispenseMs(1), float(total));
  TEST_ASSERT_EQUAL(int(Verdict::Ok), int(p.disp.lastVerdict()));
  TEST_ASSERT_EQUAL(1, p.disp.indexSteps());  // pill found on step 1
  TEST_ASSERT_EQUAL_UINT32(1, p.disp.lastBeamCount());
  TEST_ASSERT_FLOAT_WITHIN(0.2f * p.pillGrams, p.pillGrams, p.disp.lastMassDeltaG());
  TEST_ASSERT_EQUAL_INT32(start + degToCounts(MECH_INDEX_DEG), p.disp.indexPosition());
  TEST_ASSERT_INT32_WITHIN(degToCounts(1.5f), p.disp.indexPosition(), p.motor.count());
  // Pill was seen within the drop window measured from move start.
  TEST_ASSERT_EQUAL(1, (int)p.beamBlockStarts.size());
  // Motor is disabled while waiting, and the pickup is detected by the load cell.
  for (int i = 0; i < 300; ++i) p.step();
  TEST_ASSERT_FALSE(p.out.motorEnable);
  p.cupGrams -= p.pillGrams;
  TEST_ASSERT_TRUE(p.runUntilState(State::Idle, 4 * ex::kScalePeriodMs + 500));
}

void test_jam_then_recovery() {
  simt::Plant p;
  homeAndIdle(p);
  p.jamArmed = true;
  p.clearAfterReverses = 1;  // backing off once frees the drum
  p.jamAtPos = p.disp.indexPosition() + 0.3 * degToCounts(MECH_INDEX_DEG);
  const int32_t start = p.disp.indexPosition();
  const uint32_t t0 = p.nowMs;
  dispenseNow(p);
  const float jamMs = 0.3f * ex::indexMoveMs() + MECH_JAM_STALL_MS + ex::moveMs(MECH_REVERSE_DEG) +
                      ex::moveMs(0.7f * MECH_INDEX_DEG + MECH_REVERSE_DEG);
  TEST_ASSERT_TRUE(p.runUntilState(State::WaitPickup, ex::limit(ex::dispenseMs(1) + jamMs)));
  printf("jam+recovery: dispense->pickup %u ms, last move %u ms\n", p.nowMs - t0,
         p.disp.lastForwardMoveMs());
  TEST_ASSERT_EQUAL_UINT32(1, p.disp.jamEvents());
  TEST_ASSERT_EQUAL_UINT32(1, p.disp.reverseMoves());
  TEST_ASSERT_EQUAL(int(Verdict::Ok), int(p.disp.lastVerdict()));
  TEST_ASSERT_EQUAL_INT32(start + degToCounts(MECH_INDEX_DEG), p.disp.indexPosition());
  // Retry moves from (jam - reverse) back to the same absolute target:
  // (0.7 * index + reverse) at target speed + ramp.
  const float retryMs = ex::moveMs(0.7f * MECH_INDEX_DEG + MECH_REVERSE_DEG);
  TEST_ASSERT_FLOAT_WITHIN(0.15f * retryMs, retryMs, float(p.disp.lastForwardMoveMs()));
}

void test_double_on_one_step_faults() {
  simt::Plant p;
  p.pillsPerPocket = {0, 2};  // step 1 empty, step 2 drops two pills
  homeAndIdle(p);
  dispenseNow(p);
  TEST_ASSERT_TRUE(p.runUntilState(State::Fault, ex::limit(ex::dispenseMs(2))));
  TEST_ASSERT_EQUAL(int(FaultCode::Double), int(p.disp.fault()));
  TEST_ASSERT_EQUAL(2, p.disp.indexSteps());  // stopped after the step that dropped pills
  TEST_ASSERT_EQUAL_UINT32(2, p.disp.lastBeamCount());
  for (int i = 0; i < 300; ++i) p.step();
  TEST_ASSERT_FALSE(p.out.motorEnable);
  TEST_ASSERT_EQUAL_STRING("DOUBLE", p.disp.view().line[0]);
  p.pressSelect();  // acknowledge -> idle (no re-home needed)
  TEST_ASSERT_EQUAL(int(State::Idle), int(p.disp.state()));
}


void test_none_after_max_steps_is_miss_refill() {
  simt::Plant p;
  p.pillsPerPocket.assign(MECH_MAX_INDEX_STEPS + 2, 0);
  homeAndIdle(p);
  const int32_t start = p.disp.indexPosition();
  const uint32_t t0 = p.nowMs;
  dispenseNow(p);
  TEST_ASSERT_TRUE(p.runUntilState(State::Fault, ex::limit(ex::missMs())));
  const uint32_t total = p.nowMs - t0;
  printf("miss: %d steps in %u ms (expected ~%.0f)\n", p.disp.indexSteps(), total,
         ex::missMs());
  TEST_ASSERT_EQUAL(int(FaultCode::Miss), int(p.disp.fault()));
  TEST_ASSERT_EQUAL(MECH_MAX_INDEX_STEPS, p.disp.indexSteps());
  TEST_ASSERT_EQUAL_UINT32(0, p.disp.lastBeamCount());
  TEST_ASSERT_EQUAL_INT32(start + MECH_MAX_INDEX_STEPS * degToCounts(MECH_INDEX_DEG),
                          p.disp.indexPosition());
  TEST_ASSERT_FLOAT_WITHIN(0.1f * ex::missMs() + 150, ex::missMs(), float(total));
  for (int i = 0; i < 300; ++i) p.step();
  TEST_ASSERT_EQUAL_STRING("Canister empty: REFILL", p.disp.view().line[2]);
}

void test_pill_found_on_step_3() {
  simt::Plant p;
  p.pillsPerPocket = {0, 0, 1};
  homeAndIdle(p);
  const int32_t start = p.disp.indexPosition();
  dispenseNow(p);
  TEST_ASSERT_TRUE(p.runUntilState(State::WaitPickup, ex::limit(ex::dispenseMs(3))));
  TEST_ASSERT_EQUAL(3, p.disp.indexSteps());
  TEST_ASSERT_EQUAL(int(Verdict::Ok), int(p.disp.lastVerdict()));
  TEST_ASSERT_EQUAL_UINT32(1, p.disp.lastBeamCount());
  TEST_ASSERT_EQUAL_INT32(start + 3 * degToCounts(MECH_INDEX_DEG), p.disp.indexPosition());
}

void test_stall_mid_loop_recovers() {
  simt::Plant p;
  p.pillsPerPocket = {0, 0, 1};
  homeAndIdle(p);
  const int32_t start = p.disp.indexPosition();
  p.jamArmed = true;  // obstruction during the second index move
  p.clearAfterReverses = 1;
  p.jamAtPos = start + 1.4 * degToCounts(MECH_INDEX_DEG);
  dispenseNow(p);
  TEST_ASSERT_TRUE(p.runUntilState(State::WaitPickup, ex::limit(ex::dispenseMs(3) + 3000)));
  TEST_ASSERT_EQUAL(3, p.disp.indexSteps());
  TEST_ASSERT_EQUAL_UINT32(1, p.disp.jamEvents());
  TEST_ASSERT_EQUAL_UINT32(1, p.disp.reverseMoves());
  TEST_ASSERT_EQUAL(int(Verdict::Ok), int(p.disp.lastVerdict()));
  TEST_ASSERT_EQUAL_INT32(start + 3 * degToCounts(MECH_INDEX_DEG), p.disp.indexPosition());
}

void test_stall_mid_loop_persistent_faults() {
  simt::Plant p;
  p.pillsPerPocket = {0, 0, 1};
  homeAndIdle(p);
  const int32_t start = p.disp.indexPosition();
  p.jamArmed = true;
  p.clearAfterReverses = -1;
  p.jamAtPos = start + 1.4 * degToCounts(MECH_INDEX_DEG);
  dispenseNow(p);
  TEST_ASSERT_TRUE(p.runUntilState(State::Fault, ex::limit(ex::dispenseMs(2) + 6000)));
  TEST_ASSERT_EQUAL(int(FaultCode::Jam), int(p.disp.fault()));
  TEST_ASSERT_EQUAL(2, p.disp.indexSteps());
  TEST_ASSERT_EQUAL_UINT32(1u + MECH_MAX_RETRIES, p.disp.jamEvents());  // retries are per move
  TEST_ASSERT_EQUAL_UINT32(MECH_MAX_RETRIES, p.disp.reverseMoves());
}

void test_beam_only_when_scale_uncalibrated() {
  simt::Plant p;
  p.scaleCalibrated = false;
  homeAndIdle(p);
  dispenseNow(p);
  TEST_ASSERT_TRUE(p.runUntilState(State::WaitPickup, ex::limit(ex::dispenseMs(1))));
  TEST_ASSERT_EQUAL(int(Verdict::OkBeamOnly), int(p.disp.lastVerdict()));
  // No load cell: pickup must be acknowledged; after 60 s a reminder starts.
  TEST_ASSERT_TRUE(p.runUntilState(State::Reminder, cfg::kPickupRemindMs + 100));
  bool beeped = p.runUntil([&] { return p.out.buzzer; }, 1000);
  TEST_ASSERT_TRUE(beeped);
  p.pressSelect();
  TEST_ASSERT_EQUAL(int(State::Idle), int(p.disp.state()));
}

void test_scheduled_dose_past_midnight() {
  simt::Plant p;
  Schedule s;
  s.minuteOfDay[0] = 0;  // 00:00
  p.clockBase = 20000UL * 86400UL + 23 * 3600UL + 59 * 60UL + 50;  // 23:59:50
  p.begin(s, 0);
  TEST_ASSERT_TRUE(p.runUntilState(State::Idle, 6000));
  TEST_ASSERT_TRUE(p.runUntilState(State::Dispensing, 15000));
  const uint32_t due = 20001UL * 86400UL;
  TEST_ASSERT_UINT32_WITHIN(1, due, p.in.unixLocal);
  TEST_ASSERT_EQUAL_UINT32(due, p.disp.lastDoseUnix());
  TEST_ASSERT_TRUE(p.runUntilState(State::WaitPickup, ex::limit(ex::dispenseMs(1))));
  p.pressSelect();
  // Not repeated a second later.
  TEST_ASSERT_FALSE(p.runUntilState(State::Dispensing, 5000));
}

void test_reboot_does_not_repeat_given_dose() {
  simt::Plant p;
  Schedule s;
  s.minuteOfDay[0] = 8 * 60;
  const uint32_t dose = 20000UL * 86400UL + 8 * 3600UL;
  p.clockBase = dose + 120;  // rebooted 2 min after a dose that was already given
  p.begin(s, dose);
  TEST_ASSERT_TRUE(p.runUntilState(State::Idle, 6000));
  TEST_ASSERT_FALSE(p.runUntilState(State::Dispensing, 3000));
  // ...but a dose missed while powered off (within the grace period) is given.
  simt::Plant q;
  q.clockBase = dose + 120;
  q.begin(s, dose - 86400UL);
  TEST_ASSERT_TRUE(q.runUntilState(State::Dispensing, 6000));
}

void test_encoder_reversed_faults_during_homing() {
  simt::Plant p;
  p.encoderSign = -1;
  p.begin();
  TEST_ASSERT_TRUE(p.runUntilState(State::Fault, 5000));
  TEST_ASSERT_EQUAL(int(FaultCode::EncoderDirection), int(p.disp.fault()));
}

void test_menu_edit_dose_with_pot() {
  simt::Plant p;
  homeAndIdle(p);
  p.in.potRaw = 0;
  p.pressSelect();
  TEST_ASSERT_EQUAL(int(State::Menu), int(p.disp.state()));
  p.in.potRaw = int(1.5 * 4096 / 7);  // item 1 = "Dose 1"
  for (int i = 0; i < 50; ++i) p.step();
  p.pressSelect();
  // 97 choices: OFF + 96 quarter hours; pick 08:00 = choice 33.
  p.in.potRaw = int((33 + 0.5) * 4096 / 97);
  for (int i = 0; i < 50; ++i) p.step();
  bool saved = false;
  p.in.selectRaw = true;
  for (int i = 0; i < 60; ++i) {
    p.step();
    saved = saved || p.out.saveSchedule;
  }
  p.in.selectRaw = false;
  for (int i = 0; i < 60; ++i) p.step();
  TEST_ASSERT_TRUE(saved);
  TEST_ASSERT_EQUAL(8 * 60, p.disp.schedule().minuteOfDay[0]);
}

int main() {
  UNITY_BEGIN();
  RUN_TEST(test_normal_dispense_timing);
  RUN_TEST(test_jam_then_recovery);
  RUN_TEST(test_double_on_one_step_faults);
  RUN_TEST(test_none_after_max_steps_is_miss_refill);
  RUN_TEST(test_pill_found_on_step_3);
  RUN_TEST(test_stall_mid_loop_recovers);
  RUN_TEST(test_stall_mid_loop_persistent_faults);
  RUN_TEST(test_beam_only_when_scale_uncalibrated);
  RUN_TEST(test_scheduled_dose_past_midnight);
  RUN_TEST(test_reboot_does_not_repeat_given_dose);
  RUN_TEST(test_encoder_reversed_faults_during_homing);
  RUN_TEST(test_menu_edit_dose_with_pot);
  return UNITY_END();
}
