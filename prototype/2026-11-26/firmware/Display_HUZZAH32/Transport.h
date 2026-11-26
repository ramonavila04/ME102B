#pragma once
#include <Arduino.h>
#include <stdint.h>
#include <string.h>

// Private wired UART protocol between two little-endian ESP32s. Each endpoint
// receives one packet type. A damaged packet cannot act as a motion command.
namespace Link {
// Both boards agree on each action before enabling motor drive.
constexpr uint8_t VERSION = 10;
constexpr uint8_t NUDGE = 4;
constexpr uint8_t ROCK = 5;  // One complete empty-wheel jitter pattern on canister 1.
constexpr uint8_t JOG = 6;   // One standalone 15-degree forward bench move on canister 1.
constexpr uint8_t ROCK2 = 7; // Half-size manual jitter with full drive through each cruise segment.
// EDGE is a one-piece commissioning test. The motor waits for a separate scale-approved retry.
constexpr uint8_t EDGE = 8;
constexpr uint8_t EDGE_BACKED_OFF = 1, EDGE_FINISHED = 2; // indexed values when the motor reports DONE
constexpr uint8_t EDGE_FORWARD_DEGREES = 60, EDGE_BACKOFF_DEGREES = 8, EDGE_CREEP_DEG_PER_SEC = 5;
constexpr uint16_t EDGE_QUIET_MS = 250;
constexpr bool isBenchRock(uint8_t command) {
  return command == ROCK || command == ROCK2;
}
constexpr uint8_t NUDGE_DEGREES = 15, MAX_NUDGES = 8;
constexpr uint8_t STEP_DEGREES = 60, ROCK_NUDGE_ORDINAL = 2, ROCK_DEGREES = 15;
constexpr uint16_t ROCK_HOLD_MS = 250;  // quiet time at the backward endpoint before returning
// Manual ROCK endpoints in wheel degrees from its starting position. Negative is backward.
constexpr int16_t BENCH_ROCK_TARGETS[] = {-60, -45, -120, -105, -180, -120, -135, -60, -75, 0};
constexpr unsigned BENCH_ROCK_LEGS = sizeof(BENCH_ROCK_TARGETS) / sizeof(BENCH_ROCK_TARGETS[0]);
constexpr double benchRockTargetDegrees(uint8_t command, unsigned index) {
  return command == ROCK2 ? 0.5 * BENCH_ROCK_TARGETS[index] : BENCH_ROCK_TARGETS[index];
}
constexpr unsigned benchRockTravelDegrees(uint8_t command = ROCK) {
  unsigned distance = 0;
  int previous = 0;
  for (int target : BENCH_ROCK_TARGETS) {
    distance += target >= previous ? target - previous : previous - target;
    previous = target;
  }
  return command == ROCK2 ? distance / 2 : distance;
}
static_assert(BENCH_ROCK_TARGETS[BENCH_ROCK_LEGS - 1] == 0 && benchRockTravelDegrees() == 480 &&
              benchRockTravelDegrees(ROCK2) == 240,
              "Check the manual rock travel and its return to the starting position");
constexpr uint8_t MAX_PATH_DEGREES = 120;
static_assert(EDGE_FORWARD_DEGREES + 2 * EDGE_BACKOFF_DEGREES < MAX_PATH_DEGREES,
              "Allow room for a single back-off and retry within the measured travel budget");
constexpr uint32_t NUDGE_WAIT_MS = 2000;
static_assert(NUDGE_DEGREES * MAX_NUDGES == MAX_PATH_DEGREES, "Check the maximum travel per requested piece");
static_assert(STEP_DEGREES > 0 && ROCK_DEGREES > 0 && STEP_DEGREES + 2 * ROCK_DEGREES < MAX_PATH_DEGREES,
              "Leave travel for coast after the step and both rock strokes");
constexpr uint8_t maxAttempts(uint8_t wheel) {
  return wheel == 1 ? ROCK_NUDGE_ORDINAL : MAX_NUDGES;
}
constexpr unsigned forwardTargetDegrees(uint8_t wheel, uint8_t attempt) {
  // The recovery stroke returns to the endpoint of the first forward move.
  return wheel == 1 ? STEP_DEGREES : attempt * NUDGE_DEGREES;
}
struct Control {
  uint32_t session, job;
  uint8_t command, wheel, qty, reserved; // for NUDGE, qty is the 1-based attempt number
  int32_t encoder[3];  // cumulative A/B counts for wheels 4, 5 and 6
};
struct Status {
  uint32_t session, job;
  uint8_t phase, indexed, fault, configuredMask;  // NUDGE: settled steps for this piece; bench STEP: pockets
  int32_t encoder;
};
static_assert(sizeof(Control) == 24 && sizeof(Status) == 16, "Packet layout changed");
inline uint8_t type(const Control&) { return 1; }
inline uint8_t type(const Status&) { return 2; }
inline uint16_t crc(const uint8_t *data, size_t size) {
  uint16_t v = 0xffff;
  while (size--) {
    v ^= uint16_t(*data++) << 8;
    for (int i = 0; i < 8; ++i) v = (v & 0x8000) ? (v << 1) ^ 0x1021 : v << 1;
  }
  return v;
}
template<class IO, class T> void send(IO& io, const T& message) {
  uint8_t frame[sizeof(T)+7] = {0xc5,0x39,VERSION,type(message),sizeof(T)};
  memcpy(frame+5,&message,sizeof(T));
  uint16_t sum = crc(frame+2,3+sizeof(T));
  frame[sizeof(frame)-2] = uint8_t(sum);
  frame[sizeof(frame)-1] = uint8_t(sum>>8);
  io.write(frame,sizeof(frame));
}
template<class IO, class T> bool receive(IO& io, T& message) {
  static uint8_t frame[sizeof(T)+7];
  static size_t used = 0;
  while (io.available()) {
    int b = io.read();
    if (b < 0) break;
    frame[used++] = uint8_t(b);
    // Retain a possible partial header even when it occurs in a corrupt frame.
    while (used && (frame[0] != 0xc5 || (used>1 && frame[1] != 0x39) ||
           (used>2 && frame[2] != VERSION) || (used>3 && frame[3] != type(message)) ||
           (used>4 && frame[4] != sizeof(T)) ||
           (used==sizeof(frame) && crc(frame+2,3+sizeof(T)) !=
            (frame[sizeof(frame)-2] | (uint16_t(frame[sizeof(frame)-1])<<8))))) {
      --used;
      memmove(frame,frame+1,used);
    }
    if (used == sizeof(frame)) {
      memcpy(&message,frame+5,sizeof(T));
      used = 0;
      return true;
    }
  }
  return false;
}
}
