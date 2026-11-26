// Host tests for the motion board (lib/motion_bank): the UART link framing and the
// six-module bank driving six simulated gearmotors through one shared encoder counter.
#include <unity.h>

#include <vector>

#include "bank.h"
#include "dc_config.h"
#include "boardlink.h"
#include "mechanism.h"
#include "sim_motor.h"

using namespace mb;

// ---------------------------------------------------------------- link
void test_link_roundtrip() {
  uint8_t buf[boardlink::kMaxFrame];
  const uint8_t pl[5] = {3, 1, 1, 2, 0};
  const size_t n = boardlink::encode(boardlink::kResult, 42, pl, 5, buf);
  TEST_ASSERT_EQUAL(10, n);
  boardlink::Parser p;
  bool got = false;
  for (size_t i = 0; i < n; ++i) got = p.feed(buf[i]);
  TEST_ASSERT_TRUE(got);
  TEST_ASSERT_EQUAL_HEX8(boardlink::kResult, p.frame().type);
  TEST_ASSERT_EQUAL(42, p.frame().seq);
  TEST_ASSERT_EQUAL(5, p.frame().len);
  TEST_ASSERT_EQUAL_UINT8_ARRAY(pl, p.frame().payload, 5);
}

void test_link_rejects_corruption_and_resyncs() {
  uint8_t a[boardlink::kMaxFrame], b[boardlink::kMaxFrame];
  const uint8_t m = 4;
  const size_t na = boardlink::encode(boardlink::kDispense, 1, &m, 1, a);
  const size_t nb = boardlink::encode(boardlink::kHome, 2, &m, 1, b);
  a[4] ^= 0x10;  // corrupt the payload
  boardlink::Parser p;
  std::vector<uint8_t> stream = {0x00, 0x13, 0xA5};  // garbage, including a stray start byte
  stream.insert(stream.end(), a, a + na);
  stream.insert(stream.end(), b, b + nb);
  int frames = 0;
  uint8_t lastType = 0;
  for (uint8_t c : stream)
    if (p.feed(c)) {
      ++frames;
      lastType = p.frame().type;
    }
  TEST_ASSERT_EQUAL(1, frames);  // only the good frame
  TEST_ASSERT_EQUAL_HEX8(boardlink::kHome, lastType);
  TEST_ASSERT_TRUE(p.crcErrors() >= 1);
}

void test_link_rejects_oversize() {
  uint8_t big[boardlink::kMaxPayload + 1] = {};
  uint8_t buf[64];
  TEST_ASSERT_EQUAL(0, boardlink::encode(boardlink::kPing, 0, big, boardlink::kMaxPayload + 1, buf));
  boardlink::Parser p;
  const uint8_t bad[] = {boardlink::kStart, 200, 1, 1};
  for (uint8_t c : bad) TEST_ASSERT_FALSE(p.feed(c));
  TEST_ASSERT_EQUAL(1, p.lengthErrors());
}

// ---------------------------------------------------------------- six-module plant
struct Bank6 {
  dc::SimMotor m[kModules];
  ModuleBank bank;
  Inputs in;
  Outputs out;
  int32_t counter = 0;               // the single hardware counter behind the encoder multiplexer
  int32_t lastCount[kModules] = {};  // motor count when last summed into the counter
  int8_t lastSel = -1;
  int32_t homeAt[kModules], homeWidth = dc::degToCounts(6.0f);
  int encoderSign[kModules] = {1, 1, 1, 1, 1, 1};
  std::vector<int> pills[kModules];  // pills released by pocket 0, 1, 2, ... of each module
  int nextPocket[kModules] = {};
  std::vector<uint32_t> pendingBeams;  // times at which a block event happens
  // jam: forward motion of module `jamModule` is blocked beyond jamAt until it has reversed
  int jamModule = -1;
  double jamAt = 0;
  int clearAfterReverses = 1, reverses = 0;
  bool wasReversing = false;
  int32_t index0[kModules];

  Bank6() {
    for (int k = 0; k < kModules; ++k) {
      homeAt[k] = dc::degToCounts(30.0f + 10.0f * k);
      index0[k] = homeAt[k] + dc::degToCounts(MECH_HOME_OFFSET_DEG);
      pills[k] = {1, 1, 1, 1, 1, 1, 1, 1};
    }
  }
  bool home(int k) const {
    const int32_t p = m[k].count();
    const int32_t rev = static_cast<int32_t>(dc::kCountsPerRev + 0.5);
    int32_t r = p % rev;
    if (r < 0) r += rev;
    return r >= homeAt[k] && r < homeAt[k] + homeWidth;
  }
  void step() {
    out = bank.update(in);
    const int sel = out.selected;
    if (sel != lastSel) {  // the multiplexer switches: the counter carries on from its value
      if (sel >= 0) lastCount[sel] = m[sel].count();
      lastSel = static_cast<int8_t>(sel);
    }
    for (int k = 0; k < kModules; ++k) {
      const bool on = k == sel;
      float load = 0.0f;
      if (k == jamModule && reverses < clearAfterReverses + 0 && m[k].pos >= jamAt && out.duty > 0) load = 1.0f;
      m[k].load = on ? load : 0.0f;
      m[k].step(1.0f, on ? out.duty : 0.0f, on && out.motorEnable, on && out.brake);
      if (k == jamModule && on) {
        const bool rev = m[k].vel < -0.05f;
        if (rev && !wasReversing) ++reverses;
        wasReversing = rev;
      }
      // pills: pocket j of module k drops when the drum passes 60 % of index move j
      const double idx = dc::degToCounts(MECH_INDEX_DEG);
      while (nextPocket[k] < static_cast<int>(pills[k].size()) &&
             m[k].pos >= index0[k] + (nextPocket[k] + 0.6) * idx) {
        for (int n = 0; n < pills[k][nextPocket[k]]; ++n) pendingBeams.push_back(in.nowMs + 120 + 60 * n);
        ++nextPocket[k];
      }
    }
    if (sel >= 0) {
      const int32_t c = m[sel].count();
      counter += encoderSign[sel] * (c - lastCount[sel]);
      lastCount[sel] = c;
    }
    in.nowMs += 1;
    in.encoder = counter;
    in.homeMask = 0;
    for (int k = 0; k < kModules; ++k)
      if (home(k)) in.homeMask |= static_cast<uint8_t>(1u << k);
    in.beamBlocked = false;
    for (auto it = pendingBeams.begin(); it != pendingBeams.end();) {
      if (in.nowMs >= *it) {
        ++in.beamEvents;
        it = pendingBeams.erase(it);
      } else {
        ++it;
      }
    }
  }
  // Run until the bank finishes the current command (or the limit passes).
  Result run(uint32_t limitMs = 200000) {  // caplet: 16 x 90 deg at 5 rpm is ~1 min
    const uint32_t seq = bank.resultSeq(), end = in.nowMs + limitMs;
    while (bank.resultSeq() == seq && in.nowMs < end) step();
    return bank.result();
  }
  Result homeModule(int k) {
    TEST_ASSERT_EQUAL(static_cast<int>(Outcome::None), static_cast<int>(bank.command(Command::Home, k, in)));
    return run();
  }
  Result dispense(int k) {
    TEST_ASSERT_EQUAL(static_cast<int>(Outcome::None), static_cast<int>(bank.command(Command::Dispense, k, in)));
    return run();
  }
};

void test_home_all_six_independently() {
  Bank6 p;
  for (int k = 0; k < kModules; ++k) {
    double before[kModules];
    for (int j = 0; j < kModules; ++j) before[j] = p.m[j].pos;
    const Result r = p.homeModule(k);
    TEST_ASSERT_EQUAL_STRING("HOMED", outcomeName(r.outcome));
    TEST_ASSERT_EQUAL(k, r.module);
    for (int j = 0; j < kModules; ++j)
      if (j != k) TEST_ASSERT_DOUBLE_WITHIN(0.5, before[j], p.m[j].pos);  // nobody else moved
    // stopped just past its own home edge (MECH_HOME_OFFSET_DEG after it)
    TEST_ASSERT_INT_WITHIN(dc::degToCounts(2.0f), p.index0[k], p.m[k].count());
  }
  TEST_ASSERT_EQUAL_HEX8(0x3F, p.bank.homedMask());
  TEST_ASSERT_EQUAL_STRING("IDLE", bankStateName(p.bank.state()));
}

void test_dispense_one_pill() {
  Bank6 p;
  p.homeModule(2);
  const Result r = p.dispense(2);
  TEST_ASSERT_EQUAL_STRING("OK", outcomeName(r.outcome));
  TEST_ASSERT_EQUAL(1, r.beams);
  TEST_ASSERT_EQUAL(1, r.steps);
  TEST_ASSERT_INT_WITHIN(dc::degToCounts(dc::cfg::kFinalTolDeg), p.index0[2] + dc::degToCounts(MECH_INDEX_DEG),
                         p.m[2].count());
}

void test_empty_pockets_then_pill() {
  Bank6 p;
  p.pills[5] = {0, 0, 1, 1};
  p.homeModule(5);
  const Result r = p.dispense(5);
  TEST_ASSERT_EQUAL_STRING("OK", outcomeName(r.outcome));
  TEST_ASSERT_EQUAL(3, r.steps);
}

void test_double_and_miss() {
  Bank6 p;
  p.pills[1] = {2, 1};
  p.pills[3] = {};
  p.homeModule(1);
  p.homeModule(3);
  TEST_ASSERT_EQUAL_STRING("DOUBLE", outcomeName(p.dispense(1).outcome));
  const Result m = p.dispense(3);
  TEST_ASSERT_EQUAL_STRING("MISS", outcomeName(m.outcome));
  TEST_ASSERT_EQUAL(MECH_MAX_INDEX_STEPS, m.steps);
  TEST_ASSERT_EQUAL((MECH_MAX_INDEX_STEPS - 1) / MECH_ROCK_AFTER, p.bank.rocks());
  TEST_ASSERT_EQUAL_STRING("IDLE", bankStateName(p.bank.state()));  // a miss is not a fault
  // the rocks returned to the pocket each time: the drum ends MAX steps on
  TEST_ASSERT_INT_WITHIN(dc::degToCounts(dc::cfg::kFinalTolDeg),
                         p.index0[3] + MECH_MAX_INDEX_STEPS * dc::degToCounts(MECH_INDEX_DEG), p.m[3].count());
}

void test_rock_after_empty_revolution() {
  Bank6 p;
  p.pills[4].assign(MECH_ROCK_AFTER + 4, 0);
  p.pills[4].push_back(1);  // first pill in pocket MECH_ROCK_AFTER + 5
  p.homeModule(4);
  double minPos = 1e18;
  const uint32_t seq = p.bank.resultSeq();
  TEST_ASSERT_EQUAL(static_cast<int>(Outcome::None), static_cast<int>(p.bank.command(Command::Dispense, 4, p.in)));
  while (p.bank.resultSeq() == seq && p.in.nowMs < 400000) {
    p.step();
    // track how far back the drum went after the rock started
    if (p.bank.rocks() > 0 && p.m[4].pos < minPos) minPos = p.m[4].pos;
  }
  const Result r = p.bank.result();
  TEST_ASSERT_EQUAL_STRING("OK", outcomeName(r.outcome));
  TEST_ASSERT_EQUAL(MECH_ROCK_AFTER + 5, r.steps);
  TEST_ASSERT_EQUAL(1, p.bank.rocks());
  // it went back one pitch from the MECH_ROCK_AFTER-th pocket
  const double back = p.index0[4] + (MECH_ROCK_AFTER - 1) * dc::degToCounts(MECH_INDEX_DEG);
  TEST_ASSERT_DOUBLE_WITHIN(dc::degToCounts(2.0f), back, minPos);
}

void test_refusals() {
  Bank6 p;
  TEST_ASSERT_EQUAL_STRING("NOT HOMED", outcomeName(p.bank.command(Command::Dispense, 0, p.in)));
  TEST_ASSERT_EQUAL_STRING("BAD MODULE", outcomeName(p.bank.command(Command::Home, 6, p.in)));
  TEST_ASSERT_EQUAL_STRING("NONE", outcomeName(p.bank.command(Command::Home, 0, p.in)));
  TEST_ASSERT_EQUAL_STRING("BUSY", outcomeName(p.bank.command(Command::Home, 1, p.in)));
}

void test_positions_kept_across_selection() {
  // Home 0 and 1, dispense 0, then 1, then 0 again: each module indexes from its own
  // position, whatever the shared counter did in between.
  Bank6 p;
  p.homeModule(0);
  p.homeModule(1);
  const int32_t idx = dc::degToCounts(MECH_INDEX_DEG);
  const int32_t tol = dc::degToCounts(dc::cfg::kFinalTolDeg);
  TEST_ASSERT_EQUAL_STRING("OK", outcomeName(p.dispense(0).outcome));
  TEST_ASSERT_EQUAL_STRING("OK", outcomeName(p.dispense(1).outcome));
  TEST_ASSERT_EQUAL_STRING("OK", outcomeName(p.dispense(0).outcome));
  TEST_ASSERT_INT_WITHIN(tol, p.index0[0] + 2 * idx, p.m[0].count());
  TEST_ASSERT_INT_WITHIN(tol, p.index0[1] + idx, p.m[1].count());
}

void test_jam_cleared_by_reverse() {
  Bank6 p;
  p.homeModule(4);
  p.jamModule = 4;
  p.jamAt = p.index0[4] + 0.3 * dc::degToCounts(MECH_INDEX_DEG);
  p.clearAfterReverses = 1;
  const Result r = p.dispense(4);
  TEST_ASSERT_EQUAL_STRING("OK", outcomeName(r.outcome));
  TEST_ASSERT_EQUAL(1, r.jams);
}

void test_permanent_jam_faults_and_unhomes() {
  Bank6 p;
  p.homeModule(4);
  p.jamModule = 4;
  p.jamAt = p.index0[4] + 0.3 * dc::degToCounts(MECH_INDEX_DEG);
  p.clearAfterReverses = 1000;
  const Result r = p.dispense(4);
  TEST_ASSERT_EQUAL_STRING("JAM", outcomeName(r.outcome));
  TEST_ASSERT_EQUAL_STRING("FAULT", bankStateName(p.bank.state()));
  TEST_ASSERT_FALSE(p.bank.homedMask() & (1u << 4));
  TEST_ASSERT_EQUAL_STRING("BUSY", outcomeName(p.bank.command(Command::Home, 4, p.in)));
  p.bank.clearFault();
  TEST_ASSERT_EQUAL_STRING("IDLE", bankStateName(p.bank.state()));
}

void test_reversed_encoder_detected() {
  Bank6 p;
  p.encoderSign[3] = -1;
  const Result r = p.homeModule(3);
  TEST_ASSERT_EQUAL_STRING("ENCODER DIRECTION", outcomeName(r.outcome));
}

void test_abort_stops_motion() {
  Bank6 p;
  p.homeModule(0);
  p.bank.command(Command::Dispense, 0, p.in);
  for (int i = 0; i < 200; ++i) p.step();
  p.bank.abort(p.in);
  TEST_ASSERT_EQUAL_STRING("ABORTED", outcomeName(p.bank.result().outcome));
  TEST_ASSERT_EQUAL_STRING("IDLE", bankStateName(p.bank.state()));
  for (int i = 0; i < 300; ++i) p.step();
  TEST_ASSERT_FALSE(p.out.motorEnable);
}

int main(int, char**) {
  UNITY_BEGIN();
  RUN_TEST(test_link_roundtrip);
  RUN_TEST(test_link_rejects_corruption_and_resyncs);
  RUN_TEST(test_link_rejects_oversize);
  RUN_TEST(test_home_all_six_independently);
  RUN_TEST(test_dispense_one_pill);
  RUN_TEST(test_empty_pockets_then_pill);
  RUN_TEST(test_double_and_miss);
  RUN_TEST(test_rock_after_empty_revolution);
  RUN_TEST(test_refusals);
  RUN_TEST(test_positions_kept_across_selection);
  RUN_TEST(test_jam_cleared_by_reverse);
  RUN_TEST(test_permanent_jam_faults_and_unhomes);
  RUN_TEST(test_reversed_encoder_detected);
  RUN_TEST(test_abort_stops_motion);
  return UNITY_END();
}
