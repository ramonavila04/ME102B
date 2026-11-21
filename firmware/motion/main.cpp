// Motion-board firmware (Adafruit ESP32 Feather V2): drives the six V2 modules of the V8
// housing, one at a time, for the main board (HUZZAH32). Thin Arduino adapter around
// lib/motion_bank (ModuleBank: homing, indexing, beam counting, jam recovery; link: the
// framed UART protocol). Pins: include/pins_motion.h. Wiring: docs/electronics_v8.md.
//
// Link (Serial1, 115200 8N1): the main board sends HOME/DISPENSE/ABORT/CLEAR/PING frames;
// this board answers ACK (accepted or not) at once, RESULT when a command finishes, and
// STATUS on every state change and on PING.
// USB serial (115200) for bring-up: "h <k>" home, "d <k>" dispense, "a" abort,
// "c" clear fault, "s" status, "?" help.
#include <Arduino.h>

#include "bank.h"
#include "boardlink.h"
#include "mechanism.h"
#include "pins_motion.h"

namespace {
using namespace MotionPins;

// Per-module polarity, fixed in software if a motor or encoder is wired backwards (the
// bank faults with ENCODER DIRECTION if they disagree).
constexpr bool kMotorInvert[mb::kModules] = {false, false, false, false, false, false};
constexpr bool kEncoderInvert[mb::kModules] = {false, false, false, false, false, false};

constexpr uint8_t kPwmChannel = 0;
constexpr uint8_t kPwmBits = 10;
constexpr uint32_t kPwmHz = 20000;
constexpr uint32_t kPwmMax = (1u << kPwmBits) - 1;
constexpr uint32_t kBeamMinClearUs = 300;
constexpr uint32_t kLinkBaud = 115200;

mb::ModuleBank bank;
mb::Inputs in;
boardlink::Parser parser;
uint8_t txSeq = 0;
uint8_t cmdSeq = 0;           // seq of the command whose RESULT is pending
uint32_t lastResultSeq = 0, lastStateSeq = 0;

// ---------------------------------------------------------------- encoder (multiplexed)
DRAM_ATTR const int8_t QUADRATURE[16] = {0, -1, 1, 0, 1, 0, 0, -1, -1, 0, 0, 1, 0, 1, -1, 0};
portMUX_TYPE encMux = portMUX_INITIALIZER_UNLOCKED;
volatile int32_t encCount = 0;
volatile uint8_t prevAB = 0;
volatile int8_t encSign = 1;

void ARDUINO_ISR_ATTR encoderISR() {
  portENTER_CRITICAL_ISR(&encMux);
  const uint8_t ab = (digitalRead(ENC_A) << 1) | digitalRead(ENC_B);
  encCount = encCount + encSign * QUADRATURE[(prevAB << 2) | ab];
  prevAB = ab;
  portEXIT_CRITICAL_ISR(&encMux);
}

// ---------------------------------------------------------------- beam (shared)
volatile uint32_t beamEvents = 0, beamClearAtUs = 0;
volatile bool beamWasBlocked = false;

void ARDUINO_ISR_ATTR beamISR() {
  const uint32_t t = micros();
  const bool blocked = digitalRead(BEAM) == LOW;
  if (blocked && !beamWasBlocked) {
    if (t - beamClearAtUs >= kBeamMinClearUs) beamEvents = beamEvents + 1;
  } else if (!blocked && beamWasBlocked) {
    beamClearAtUs = t;
  }
  beamWasBlocked = blocked;
}

// ---------------------------------------------------------------- outputs
int8_t shownSel = -2;
uint16_t shownBits = 0xFFFF;

void writeShift(uint16_t bits) {
  if (bits == shownBits) return;
  shownBits = bits;
  digitalWrite(SR_LATCH, LOW);
  shiftOut(SR_DATA, SR_CLOCK, MSBFIRST, static_cast<uint8_t>(bits >> 8));  // second register
  shiftOut(SR_DATA, SR_CLOCK, MSBFIRST, static_cast<uint8_t>(bits & 0xFF));
  digitalWrite(SR_LATCH, HIGH);
}

void selectMux(int8_t sel) {
  if (sel == shownSel) return;
  shownSel = sel;
  const uint8_t ch = sel < 0 ? 7 : static_cast<uint8_t>(sel);  // channel 7 is unused
  digitalWrite(MUX_S0, ch & 1);
  digitalWrite(MUX_S1, (ch >> 1) & 1);
  digitalWrite(MUX_S2, (ch >> 2) & 1);
  delayMicroseconds(2);  // 74HC4051 switching time at 3.3 V is well under this
  portENTER_CRITICAL(&encMux);
  prevAB = (digitalRead(ENC_A) << 1) | digitalRead(ENC_B);  // no false step on switching
  encSign = (sel >= 0 && kEncoderInvert[sel]) ? -1 : 1;
  portEXIT_CRITICAL(&encMux);
}

void applyMotor(const mb::Outputs& o) {
  selectMux(o.selected);
  if (!o.motorEnable || o.selected < 0) {
    ledcWrite(kPwmChannel, 0);
    writeShift(0);                     // every channel in TB6612 stop
    digitalWrite(MOTOR_STBY, LOW);
    return;
  }
  const int k = o.selected;
  uint16_t bits = 0;
  uint32_t pwm = 0;
  if (o.brake) {  // short brake: IN1 = IN2 = HIGH, PWM high
    bits = static_cast<uint16_t>(3u << (2 * k));
    pwm = kPwmMax;
  } else {
    const float d = kMotorInvert[k] ? -o.duty : o.duty;
    bits = static_cast<uint16_t>((d >= 0 ? 1u : 2u) << (2 * k));
    pwm = static_cast<uint32_t>(fabsf(d) * kPwmMax + 0.5f);
  }
  writeShift(bits);
  ledcWrite(kPwmChannel, pwm);
  digitalWrite(MOTOR_STBY, HIGH);
}

// ---------------------------------------------------------------- link
void sendFrame(uint8_t type, uint8_t seq, const uint8_t* p, uint8_t n) {
  uint8_t buf[boardlink::kMaxFrame];
  const size_t len = boardlink::encode(type, seq, p, n, buf);
  Serial1.write(buf, len);
}

void sendStatus() {
  const uint8_t p[4] = {static_cast<uint8_t>(bank.state()), static_cast<uint8_t>(bank.active() < 0 ? 0xFF : bank.active()),
                        bank.homedMask(), static_cast<uint8_t>(bank.fault())};
  sendFrame(boardlink::kStatus, txSeq++, p, 4);
}

void handleFrame(const boardlink::Frame& f) {
  uint8_t accepted = 1;
  switch (f.type) {
    case boardlink::kPing:
      sendStatus();
      return;
    case boardlink::kHome:
    case boardlink::kDispense: {
      const mb::Command c = f.type == boardlink::kHome ? mb::Command::Home : mb::Command::Dispense;
      const mb::Outcome o = f.len >= 1 ? bank.command(c, f.payload[0], in) : mb::Outcome::BadModule;
      accepted = o == mb::Outcome::None;
      if (accepted) cmdSeq = f.seq;
      const uint8_t p[2] = {accepted, static_cast<uint8_t>(o)};
      sendFrame(boardlink::kAck, f.seq, p, 2);
      return;
    }
    case boardlink::kAbort:
      bank.abort(in);
      break;
    case boardlink::kClearFault:
      bank.clearFault();
      break;
    default:
      accepted = 0;
      break;
  }
  sendFrame(boardlink::kAck, f.seq, &accepted, 1);
}

void pollLink() {
  while (Serial1.available()) {
    if (parser.feed(static_cast<uint8_t>(Serial1.read()))) handleFrame(parser.frame());
  }
}

// ---------------------------------------------------------------- USB bring-up console
char line[32];
uint8_t lineLen = 0;

void printStatus() {
  Serial.printf("state %s module %d homed 0x%02X fault %s | enc %ld beam %lu home 0x%02X\n",
                mb::bankStateName(bank.state()), bank.active(), bank.homedMask(), mb::outcomeName(bank.fault()),
                static_cast<long>(in.encoder), static_cast<unsigned long>(in.beamEvents), in.homeMask);
}

void runCommand(const char* s) {
  int k = -1;
  if ((s[0] == 'h' || s[0] == 'd') && sscanf(s + 1, "%d", &k) == 1) {
    const mb::Outcome o = bank.command(s[0] == 'h' ? mb::Command::Home : mb::Command::Dispense, k, in);
    Serial.printf("%s %d: %s\n", s[0] == 'h' ? "home" : "dispense", k,
                  o == mb::Outcome::None ? "started" : mb::outcomeName(o));
  } else if (s[0] == 'a') {
    bank.abort(in);
  } else if (s[0] == 'c') {
    bank.clearFault();
  } else if (s[0] == 's') {
    printStatus();
  } else {
    Serial.println("Commands: h <0-5> home, d <0-5> dispense, a abort, c clear fault, s status");
  }
}

void pollConsole() {
  while (Serial.available()) {
    const char c = static_cast<char>(Serial.read());
    if (c == '\n' || c == '\r') {
      if (lineLen) {
        line[lineLen] = '\0';
        runCommand(line);
        lineLen = 0;
      }
    } else if (lineLen < sizeof line - 1) {
      line[lineLen++] = c;
    }
  }
}
}  // namespace

void setup() {
  // Drivers off before anything else: STBY low, every IN line low, PWM 0.
  pinMode(MOTOR_STBY, OUTPUT);
  digitalWrite(MOTOR_STBY, LOW);
  pinMode(SR_DATA, OUTPUT);
  pinMode(SR_CLOCK, OUTPUT);
  pinMode(SR_LATCH, OUTPUT);
  writeShift(0);
  ledcSetup(kPwmChannel, kPwmHz, kPwmBits);
  ledcAttachPin(MOTOR_PWM, kPwmChannel);
  ledcWrite(kPwmChannel, 0);

  Serial.begin(115200);
  Serial1.begin(kLinkBaud, SERIAL_8N1, LINK_RX, LINK_TX);

  pinMode(MUX_S0, OUTPUT);
  pinMode(MUX_S1, OUTPUT);
  pinMode(MUX_S2, OUTPUT);
  pinMode(ENC_A, INPUT);  // input-only pins; the encoder boards pull up
  pinMode(ENC_B, INPUT);
  pinMode(BEAM, INPUT);   // EXTERNAL 10k pull-up
  for (uint8_t p : HOME) pinMode(p, INPUT_PULLUP);
  selectMux(-1);
  attachInterrupt(digitalPinToInterrupt(ENC_A), encoderISR, CHANGE);
  attachInterrupt(digitalPinToInterrupt(ENC_B), encoderISR, CHANGE);
  beamWasBlocked = digitalRead(BEAM) == LOW;
  attachInterrupt(digitalPinToInterrupt(BEAM), beamISR, CHANGE);
  Serial.printf("Motion board: %s, six modules\n", MECH_NAME);
}

void loop() {
  pollConsole();
  pollLink();
  in.nowMs = millis();
  portENTER_CRITICAL(&encMux);
  in.encoder = encCount;
  portEXIT_CRITICAL(&encMux);
  in.beamEvents = beamEvents;
  in.beamBlocked = digitalRead(BEAM) == LOW;
  in.homeMask = 0;
  for (int k = 0; k < mb::kModules; ++k)
    if (digitalRead(HOME[k]) == LOW) in.homeMask |= static_cast<uint8_t>(1u << k);

  applyMotor(bank.update(in));

  if (bank.resultSeq() != lastResultSeq) {
    lastResultSeq = bank.resultSeq();
    const mb::Result& r = bank.result();
    const uint8_t p[5] = {r.module, static_cast<uint8_t>(r.outcome), r.beams, r.steps, r.jams};
    sendFrame(boardlink::kResult, cmdSeq, p, 5);
    Serial.printf("module %u: %s (beams %u, steps %u, jams %u)\n", r.module, mb::outcomeName(r.outcome), r.beams,
                  r.steps, r.jams);
  }
  if (bank.stateSeq() != lastStateSeq) {
    lastStateSeq = bank.stateSeq();
    sendStatus();
  }
}
