// Integrated pill-dispenser firmware: thin Arduino adapter around
// lib/dispenser_core (state machine, motion control, verification, schedule).
// Non-blocking: loop() never waits; the display is redrawn a few characters
// per pass so motor control keeps its 5 ms period.
//
// Hardware and pins: include/pins.h, docs/wiring.md. Mechanism constants:
// include/mechanism.h (generated). Serial 115200, type '?' for commands.
#include <Adafruit_GFX.h>
#include <Adafruit_ILI9341.h>
#include <Arduino.h>
#include <HX711.h>
#include <Preferences.h>
#include <RTClib.h>
#include <SPI.h>
#include <Wire.h>
#include <math.h>

#include "dispenser.h"
#include "mechanism.h"
#include "pins.h"
#ifdef DISPENSER_SIM_MOTOR
#include "sim_motor.h"
#endif

namespace {

// ---- Polarity: fix in software if the motor or encoder runs backwards
// (the firmware faults with ENCODER DIRECTION if they disagree).
constexpr bool kMotorInvert = false;
constexpr bool kEncoderInvert = false;

constexpr uint8_t kPwmChannel = 0;
constexpr uint8_t kPwmBits = 10;
constexpr uint32_t kPwmHz = 20000;  // TB6612 allows up to 100 kHz; 20 kHz is inaudible
constexpr uint32_t kPwmMax = (1u << kPwmBits) - 1;
constexpr uint8_t kBuzzerChannel = 2;
constexpr uint32_t kBuzzerHz = 2700;
constexpr uint32_t kBeamMinClearUs = 300;  // shorter beam re-clears are merged (glitch filter)
constexpr uint32_t kScaleStaleMs = 1000;   // HX711 silent this long = not present

Adafruit_ILI9341 tft(Pins::TFT_CS, Pins::TFT_DC, Pins::TFT_RST);
RTC_DS3231 rtc;
HX711 scale;
Preferences prefs;
dc::Dispenser disp;
dc::Inputs in;

// ---------------------------------------------------------------- encoder
DRAM_ATTR const int8_t QUADRATURE[16] = {0, -1, 1, 0, 1, 0, 0, -1, -1, 0, 0, 1, 0, 1, -1, 0};
portMUX_TYPE encoderMux = portMUX_INITIALIZER_UNLOCKED;
volatile int32_t encoderCount = 0;
volatile uint32_t encoderInvalid = 0;
volatile uint8_t previousAB = 0;

void ARDUINO_ISR_ATTR encoderISR() {
  portENTER_CRITICAL_ISR(&encoderMux);
  const uint8_t ab = (digitalRead(Pins::ENCODER_A) << 1) | digitalRead(Pins::ENCODER_B);
  if ((previousAB ^ ab) == 3) encoderInvalid = encoderInvalid + 1;
  encoderCount = encoderCount + QUADRATURE[(previousAB << 2) | ab];
  previousAB = ab;
  portEXIT_CRITICAL_ISR(&encoderMux);
}

// ---------------------------------------------------------------- beam
volatile uint32_t beamEvents = 0;
volatile uint32_t beamClearAtUs = 0;
volatile bool beamWasBlocked = false;

void ARDUINO_ISR_ATTR beamISR() {
  const uint32_t t = micros();
  const bool blocked = digitalRead(Pins::BEAM) == LOW;
  if (blocked && !beamWasBlocked) {
    if (t - beamClearAtUs >= kBeamMinClearUs) beamEvents = beamEvents + 1;
  } else if (!blocked && beamWasBlocked) {
    beamClearAtUs = t;
  }
  beamWasBlocked = blocked;
}

// ---------------------------------------------------------------- scale
float countsPerGram = 0.0f;  // 0 = not calibrated (NVS "cpg")
long zeroRaw = 0;            // NVS "zero" (only for displayed grams; verification uses deltas)
constexpr int kRawAvg = 8;
long rawRing[kRawAvg];
int rawN = 0, rawI = 0;
uint32_t lastScaleMs = 0;

long rawMean() {
  long long s = 0;
  for (int i = 0; i < rawN; ++i) s += rawRing[i];
  return rawN ? static_cast<long>(s / rawN) : 0;
}

void pollScale(uint32_t now) {
  if (!scale.is_ready()) {  // non-blocking: only read when a conversion is waiting
    if (now - lastScaleMs > kScaleStaleMs) in.scaleOk = false;
    return;
  }
  const long raw = scale.read();
  lastScaleMs = now;
  const bool saturated = raw == 8388607L || raw == -8388608L;
  if (!saturated) {
    rawRing[rawI] = raw;
    rawI = (rawI + 1) % kRawAvg;
    if (rawN < kRawAvg) ++rawN;
  }
  in.scaleOk = !saturated && countsPerGram != 0.0f;
  in.scaleGrams = in.scaleOk ? (raw - zeroRaw) / countsPerGram : 0.0f;
  ++in.scaleSeq;
}

// ---------------------------------------------------------------- RTC
bool rtcFound = false, rtcLostPower = true;
uint32_t lastRtcMs = 0;

void pollRtc(uint32_t now) {
  if (!rtcFound || now - lastRtcMs < 200) return;
  lastRtcMs = now;
  in.unixLocal = rtc.now().unixtime();
  in.clockValid = !rtcLostPower;
}

// ---------------------------------------------------------------- outputs
void applyMotor(const dc::Outputs& o) {
  if (!o.motorEnable) {
    ledcWrite(kPwmChannel, 0);
    digitalWrite(Pins::AIN1, LOW);
    digitalWrite(Pins::AIN2, LOW);
    digitalWrite(Pins::MOTOR_ENABLE, LOW);  // STBY low: outputs high-impedance
    return;
  }
  if (o.brake) {  // TB6612 short brake: IN1 = IN2 = HIGH
    digitalWrite(Pins::AIN1, HIGH);
    digitalWrite(Pins::AIN2, HIGH);
    ledcWrite(kPwmChannel, kPwmMax);
  } else {
    const float d = kMotorInvert ? -o.duty : o.duty;
    digitalWrite(Pins::AIN1, d >= 0 ? HIGH : LOW);
    digitalWrite(Pins::AIN2, d >= 0 ? LOW : HIGH);
    ledcWrite(kPwmChannel, static_cast<uint32_t>(fabsf(d) * kPwmMax + 0.5f));
  }
  digitalWrite(Pins::MOTOR_ENABLE, HIGH);
}

bool buzzerOn = false;
void applyIndicators(const dc::Outputs& o) {
  if (o.buzzer != buzzerOn) {
    buzzerOn = o.buzzer;
    ledcWrite(kBuzzerChannel, buzzerOn ? 128 : 0);
  }
  digitalWrite(Pins::LED, o.led ? HIGH : LOW);
}

void persist(const dc::Outputs& o) {
  if (o.saveSchedule) {
    const dc::Schedule& s = disp.schedule();
    prefs.putShort("d0", s.minuteOfDay[0]);
    prefs.putShort("d1", s.minuteOfDay[1]);
    prefs.putShort("d2", s.minuteOfDay[2]);
    Serial.println("NVS: schedule saved");
  }
  if (o.saveLastDose) prefs.putULong("last", disp.lastDoseUnix());
  if (o.setClock && rtcFound) {
    rtc.adjust(DateTime(o.clockUnix));
    rtcLostPower = false;
    lastRtcMs = 0;
    Serial.println("RTC: time set");
  }
}

// ---------------------------------------------------------------- display
// Character-level diff renderer: at most kCharsPerPass glyphs per loop pass.
class Screen {
 public:
  void begin() {
    tft.begin();
    tft.setRotation(1);  // landscape 320 x 240
    tft.fillScreen(ILI9341_BLACK);
    tft.drawFastHLine(0, 38, 320, ILI9341_DARKGREY);
    tft.drawFastHLine(0, 206, 320, ILI9341_DARKGREY);
    memset(shown_, 0, sizeof shown_);
    memset(want_, ' ', sizeof want_);
  }
  void setView(const dc::View& v, dc::State s) {
    const uint16_t c = s == dc::State::Fault ? ILI9341_RED
                       : (s == dc::State::WaitPickup || s == dc::State::Reminder) ? ILI9341_GREEN
                                                                                   : ILI9341_CYAN;
    if (c != titleColor_) {
      titleColor_ = c;
      memset(shown_[0], 0, kCols);  // force title redraw in the new colour
    }
    put(0, v.title);
    for (int i = 0; i < dc::kViewLines; ++i) put(1 + i, v.line[i]);
    put(kRows - 1, v.footer);
  }
  void service() {
    int budget = kCharsPerPass;
    for (int r = 0; r < kRows && budget > 0; ++r) {
      const int cols = r == 0 ? kTitleCols : kCols;
      for (int c = 0; c < cols && budget > 0; ++c) {
        if (want_[r][c] == shown_[r][c]) continue;
        const bool title = r == 0;
        const int size = title ? 3 : 2;
        const int x = 4 + c * 6 * size;
        const int y = title ? 8 : (r == kRows - 1 ? 216 : 50 + (r - 1) * 36);
        const uint16_t fg = title ? titleColor_ : (r == kRows - 1 ? ILI9341_LIGHTGREY : ILI9341_WHITE);
        tft.drawChar(x, y, want_[r][c], fg, ILI9341_BLACK, size);
        shown_[r][c] = want_[r][c];
        --budget;
      }
    }
  }

 private:
  static constexpr int kRows = 2 + dc::kViewLines;
  static constexpr int kCols = 26;
  static constexpr int kTitleCols = 17;
  static constexpr int kCharsPerPass = 3;  // ~0.5 ms each at 24 MHz SPI
  void put(int r, const char* s) {
    const int cols = r == 0 ? kTitleCols : kCols;
    bool end = false;
    for (int c = 0; c < cols; ++c) {
      if (!end && s[c] == '\0') end = true;
      want_[r][c] = end ? ' ' : s[c];
    }
  }
  char shown_[kRows][kCols];
  char want_[kRows][kCols];
  uint16_t titleColor_ = 0;
};
Screen screen;

// ---------------------------------------------------------------- simulation build
#ifdef DISPENSER_SIM_MOTOR
dc::SimMotor sim;
uint32_t simLastUs = 0;
dc::Outputs lastOut;
void stepSim() {
  const uint32_t t = micros();
  const float dt = (t - simLastUs) / 1000.0f;
  simLastUs = t;
  sim.step(dt > 20.0f ? 20.0f : dt, lastOut.duty, lastOut.motorEnable, lastOut.brake);
  const double rev = dc::kCountsPerRev;
  double p = fmod(sim.pos, rev);
  if (p < 0) p += rev;
  in.homeRaw = p >= dc::degToCounts(61.0f) && p < dc::degToCounts(67.0f);  // simulated home switch
}
#endif

// ---------------------------------------------------------------- serial commands
char cmd[48];
int cmdLen = 0;

void printStatus() {
  portENTER_CRITICAL(&encoderMux);
  const int32_t enc = encoderCount;
  const uint32_t inv = encoderInvalid;
  portEXIT_CRITICAL(&encoderMux);
  char t[10];
  dc::formatClock(in.unixLocal, t, sizeof t);
  Serial.printf("state %s fault %s | enc %ld (invalid %lu) index %ld | beam %lu %s | home %d\n",
                dc::stateName(disp.state()), dc::faultName(disp.fault()), static_cast<long>(enc),
                static_cast<unsigned long>(inv), static_cast<long>(disp.indexPosition()),
                static_cast<unsigned long>(beamEvents), in.beamBlocked ? "BLOCKED" : "clear",
                in.homeRaw ? 1 : 0);
  Serial.printf("scale %s %.3f g (cpg %.1f) | clock %s %s | pot %d | mech %s\n",
                in.scaleOk ? "ok" : "n/a", in.scaleGrams, countsPerGram, t,
                in.clockValid ? "valid" : "NOT SET", in.potRaw, MECH_NAME);
  for (int i = 0; i < dc::kMaxDoses; ++i) {
    char d[8];
    dc::formatMinuteOfDay(disp.schedule().minuteOfDay[i], d, sizeof d);
    Serial.printf("dose %d: %s\n", i + 1, d);
  }
}

void handleCommand(char* c) {
  int y, mo, d, h, mi, s, slot;
  float g;
  if (!strcmp(c, "d")) {
    in.requestDispense = true;
  } else if (!strcmp(c, "a")) {
    in.requestAck = true;
  } else if (!strcmp(c, "h")) {
    disp.requestHoming();
  } else if (!strcmp(c, "s")) {
    printStatus();
  } else if (!strcmp(c, "t")) {
    zeroRaw = rawMean();
    prefs.putLong("zero", zeroRaw);
    Serial.printf("Scale zero = %ld (empty cup)\n", zeroRaw);
  } else if (sscanf(c, "c %f", &g) == 1 && g > 0.0f && g <= 100.0f) {
    const float cpg = (rawMean() - zeroRaw) / g;
    if (fabsf(cpg) < 1.0f) {
      Serial.println("Calibration failed: no load change. Tare (t) with empty cup first.");
    } else {
      countsPerGram = cpg;
      prefs.putFloat("cpg", countsPerGram);
      Serial.printf("Scale calibrated: %.1f counts/g\n", countsPerGram);
    }
  } else if (sscanf(c, "T %d-%d-%d %d:%d:%d", &y, &mo, &d, &h, &mi, &s) == 6) {
    if (rtcFound) {
      rtc.adjust(DateTime(y, mo, d, h, mi, s));
      rtcLostPower = false;
      lastRtcMs = 0;
      Serial.println("RTC set");
    } else {
      Serial.println("RTC not found");
    }
  } else if (sscanf(c, "D%d %d:%d", &slot, &h, &mi) == 3 && slot >= 1 && slot <= 3) {
    disp.setDose(slot - 1, static_cast<int16_t>(h * 60 + mi));
  } else if (sscanf(c, "D%d off", &slot) == 1 && slot >= 1 && slot <= 3 && strstr(c, "off")) {
    disp.setDose(slot - 1, dc::kDoseOff);
  } else {
    Serial.println(
        "Commands: d=dispense a=acknowledge h=re-home s=status t=tare c <grams>=calibrate\n"
        "          T YYYY-MM-DD HH:MM:SS = set RTC   D<1-3> HH:MM | D<1-3> off = dose time");
  }
}

void pollSerial() {
  while (Serial.available()) {
    const char ch = static_cast<char>(Serial.read());
    if (ch == '\r' || ch == '\n') {
      if (cmdLen) {
        cmd[cmdLen] = '\0';
        handleCommand(cmd);
        cmdLen = 0;
      }
    } else if (cmdLen < static_cast<int>(sizeof cmd) - 1) {
      cmd[cmdLen++] = ch;
    }
  }
}

uint32_t lastPotMs = 0;
float potFiltered = 0;
uint32_t lastViewSeq = 0, lastEventSeq = 0;

}  // namespace

void setup() {
  // Motor driver safe FIRST: STBY low (also held low by the external
  // pull-down during reset), direction inputs low, PWM 0.
  pinMode(Pins::MOTOR_ENABLE, OUTPUT);
  digitalWrite(Pins::MOTOR_ENABLE, LOW);
  pinMode(Pins::AIN1, OUTPUT);
  digitalWrite(Pins::AIN1, LOW);
  pinMode(Pins::AIN2, OUTPUT);
  digitalWrite(Pins::AIN2, LOW);
  ledcSetup(kPwmChannel, kPwmHz, kPwmBits);
  ledcAttachPin(Pins::PWMA, kPwmChannel);
  ledcWrite(kPwmChannel, 0);
  ledcSetup(kBuzzerChannel, kBuzzerHz, 8);
  ledcAttachPin(Pins::BUZZER, kBuzzerChannel);
  ledcWrite(kBuzzerChannel, 0);
  pinMode(Pins::LED, OUTPUT);
  digitalWrite(Pins::LED, LOW);

  Serial.begin(115200);
  Serial.printf("\nPill dispenser | mechanism %s | index %.1f deg @ %.1f rpm\n", MECH_NAME,
                MECH_INDEX_DEG, MECH_TARGET_RPM);
#ifdef DISPENSER_SIM_MOTOR
  Serial.println("*** SIMULATED MOTOR BUILD: encoder and home switch are simulated ***");
#endif

  pinMode(Pins::BTN_SELECT, INPUT_PULLUP);
  pinMode(Pins::BTN_BACK, INPUT_PULLUP);
  pinMode(Pins::HOME_SWITCH, INPUT);  // GPIO39: external 10k pull-up required
  pinMode(Pins::BEAM, INPUT_PULLUP);  // plus external 10k pull-up
  pinMode(Pins::ENCODER_A, INPUT);    // encoder board provides pull-ups
  pinMode(Pins::ENCODER_B, INPUT);
  analogReadResolution(12);
  potFiltered = analogRead(Pins::POT);

  SPI.begin(Pins::TFT_SCK, -1, Pins::TFT_MOSI);  // no MISO: GPIO19 is the Back button
  screen.begin();

  Wire.begin(Pins::I2C_SDA, Pins::I2C_SCL);
  rtcFound = rtc.begin(&Wire);
  rtcLostPower = !rtcFound || rtc.lostPower();
  Serial.printf("RTC: %s%s\n", rtcFound ? "DS3231 found" : "NOT FOUND",
                rtcFound && rtcLostPower ? " (lost power: set the clock)" : "");

  scale.begin(Pins::HX_DATA, Pins::HX_CLOCK);

  prefs.begin("dispenser", false);
  dc::Schedule sched;
  sched.minuteOfDay[0] = prefs.getShort("d0", dc::kDoseOff);
  sched.minuteOfDay[1] = prefs.getShort("d1", dc::kDoseOff);
  sched.minuteOfDay[2] = prefs.getShort("d2", dc::kDoseOff);
  countsPerGram = prefs.getFloat("cpg", 0.0f);
  zeroRaw = prefs.getLong("zero", 0);
  Serial.printf("Scale: %s\n", countsPerGram != 0.0f ? "calibrated" : "NOT calibrated (beam-only verification; use t / c)");
  disp.begin(sched, prefs.getULong("last", 0));

  previousAB = (digitalRead(Pins::ENCODER_A) << 1) | digitalRead(Pins::ENCODER_B);
  attachInterrupt(digitalPinToInterrupt(Pins::ENCODER_A), encoderISR, CHANGE);
  attachInterrupt(digitalPinToInterrupt(Pins::ENCODER_B), encoderISR, CHANGE);
  beamWasBlocked = digitalRead(Pins::BEAM) == LOW;
  attachInterrupt(digitalPinToInterrupt(Pins::BEAM), beamISR, CHANGE);
#ifdef DISPENSER_SIM_MOTOR
  simLastUs = micros();
#endif
  Serial.println("Type ? for commands.");
}

void loop() {
  const uint32_t now = millis();
  pollSerial();

  // ---- sensors -> inputs
  in.nowMs = now;
#ifdef DISPENSER_SIM_MOTOR
  stepSim();
  in.encoder = sim.count();
#else
  portENTER_CRITICAL(&encoderMux);
  const int32_t enc = encoderCount;
  portEXIT_CRITICAL(&encoderMux);
  in.encoder = kEncoderInvert ? -enc : enc;
  in.homeRaw = digitalRead(Pins::HOME_SWITCH) == LOW;
#endif
  in.beamEvents = beamEvents;
  in.beamBlocked = digitalRead(Pins::BEAM) == LOW;
  in.selectRaw = digitalRead(Pins::BTN_SELECT) == LOW;
  in.backRaw = digitalRead(Pins::BTN_BACK) == LOW;
  if (now - lastPotMs >= 10) {
    lastPotMs = now;
    potFiltered += (analogRead(Pins::POT) - potFiltered) * 0.25f;
    in.potRaw = static_cast<int>(potFiltered + 0.5f);
  }
  pollScale(now);
  pollRtc(now);

  // ---- logic
  const dc::Outputs out = disp.update(in);
  in.requestDispense = false;
  in.requestAck = false;
#ifdef DISPENSER_SIM_MOTOR
  lastOut = out;
#endif

  // ---- actuators
  applyMotor(out);
  applyIndicators(out);
  persist(out);

  if (disp.eventSeq() != lastEventSeq) {
    lastEventSeq = disp.eventSeq();
    Serial.printf("[%8lu] %s\n", static_cast<unsigned long>(now), disp.lastEvent());
  }
  if (disp.viewSeq() != lastViewSeq) {
    lastViewSeq = disp.viewSeq();
    screen.setView(disp.view(), disp.state());
  }
  screen.service();
}
