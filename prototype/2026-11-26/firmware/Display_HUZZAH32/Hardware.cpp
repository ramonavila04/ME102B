// The micro-USB HUZZAH32 reads the controls, scale, RTC and encoders 4–6.
// Its UART peer on the USB-C Feather V2 owns all six motor bridges.
#include "Hardware.h"
#include "DisplaySettings.h"
#include <Preferences.h>
#include <RTClib.h>
#include <Wire.h>
#include <esp_system.h>
#include <sys/time.h>
#include <math.h>
#include <ctype.h>

bool handleSetupCommand(const char *line);

namespace HW {
static DRAM_ATTR const uint8_t ENCODERS[3][2] = {{34, 14}, {27, 16}, {33, 25}};
constexpr uint8_t UART_RX = 39, UART_TX = 15, HX_DATA = 36, HX_CLOCK = 4;
constexpr uint32_t STATUS_TIMEOUT_MS = 280, UI_TIMEOUT_MS = 2500;
static portMUX_TYPE linkMux = portMUX_INITIALIZER_UNLOCKED, encMux = portMUX_INITIALIZER_UNLOCKED;
static portMUX_TYPE hxMux = portMUX_INITIALIZER_UNLOCKED;
static Link::Control request{};
static uint8_t currentPiece = 0; // display loop only; retries retain their job ID
static Link::Status remote{};
Link::Status status{}; // main-loop snapshot
struct Reading {
  int32_t raw;
  uint32_t at;
};
static QueueHandle_t sampleQueue = nullptr;
static bool nextRaw(int32_t &raw);
static void refreshInputs();
static void refreshLink();
static bool edgeDryRun = false; // Main-loop owner; both commissioning modes use the same motor command.
static bool havePeer = false, trip = false, haveTask = false;
static uint32_t heardAt = 0, uiAt = 0, snapshotAt = 0;
static uint32_t startedAt = 0, currentReplyAt = 0;
static bool acknowledged = false;
static bool snapshotValid = false;
static uint32_t encoderRaw[3]{};
static uint8_t lastAB[3]{};
static DRAM_ATTR const int8_t directionTable[16] = {0,  -1, 1, 0, 1, 0, 0,  -1,
                                                    -1, 0,  0, 1, 0, 1, -1, 0};

static bool usesOrdinal(uint8_t command) {
  return command == Link::NUDGE || Link::isBenchRock(command) || command == Link::JOG ||
         command == Link::EDGE;
}
static bool running() {
  return request.command == 1 || request.command == 3 || usesOrdinal(request.command);
}

// A latched DONE from attempt N-1 can arrive while N is being requested.
// Identify the actual motion by its job, ordinal and phase before using that reply.
static bool nudgeReply(const Link::Status &msg, uint8_t attempt) {
  return msg.phase == 4 || (msg.phase == 1 && msg.indexed + 1 == attempt) ||
         (msg.phase == 3 && msg.indexed == attempt);
}

static bool attemptReply(const Link::Status &msg, uint8_t command, uint8_t attempt) {
  // An unobstructed first EDGE pass can finish without any back-off or retry.
  if (command == Link::EDGE && msg.phase == 3 && msg.indexed == Link::EDGE_FINISHED)
    return true;
  return nudgeReply(msg, attempt);
}

// EXTERNAL INTERRUPT. Keep A/B transitions even while the display is redrawing.
static void ARDUINO_ISR_ATTR encoderEdge(void *arg) {
  const size_t i = reinterpret_cast<size_t>(arg);
  portENTER_CRITICAL_ISR(&encMux);
  uint8_t ab = (digitalRead(ENCODERS[i][0]) << 1) | digitalRead(ENCODERS[i][1]);
  encoderRaw[i] += directionTable[(lastAB[i] << 2) | ab];
  lastAB[i] = ab;
  portEXIT_CRITICAL_ISR(&encMux);
}

// Called by the display loop before accepting a job. Unwired encoder pins can float,
// so enable each pair only after the motor board first advertises that wheel.
static void enableInstalledEncoders(uint8_t configuredMask) {
  static uint8_t attachedMask = 0;
  for (size_t i = 0; i < 3; i++) {
    const uint8_t wheelBit = 1U << (i + 3); // remote encoders are on wheels 4, 5 and 6
    if (!(configuredMask & wheelBit) || (attachedMask & wheelBit))
      continue;
    for (uint8_t pin : ENCODERS[i])
      pinMode(pin, INPUT);
    lastAB[i] = (digitalRead(ENCODERS[i][0]) << 1) | digitalRead(ENCODERS[i][1]);
    for (uint8_t pin : ENCODERS[i])
      attachInterruptArg(pin, encoderEdge, reinterpret_cast<void *>(i), CHANGE);
    attachedMask |= wheelBit;
  }
}

// SERVICE. The wire protocol continues to run through slow TFT redraws.
// If the UI stops servicing its loop or the motor board disappears, cancel the job.
static void transportTask(void *) {
  uint32_t lastSent = 0;
  for (;;) {
    uint32_t now = millis();
    Link::Status msg{};
    while (Link::receive(Serial2, msg)) {
      portENTER_CRITICAL(&linkMux);
      if (running() && !msg.session)
        trip = true;
      const bool previousEdgePass = request.command == Link::EDGE && request.qty == 2 &&
          msg.job == request.job && !msg.fault &&
          ((msg.phase == 1 && msg.indexed == 0) || (msg.phase == 3 && msg.indexed == Link::EDGE_BACKED_OFF));
      if (msg.session == request.session && msg.phase <= 4 && msg.configuredMask <= 0x3f && !previousEdgePass) {
        remote = msg;
        heardAt = now;
        havePeer = true;
        if (running() && msg.job == request.job) {
          bool expected = request.command == 3 ? msg.phase == 2 : (msg.phase == 1 || msg.phase == 3);
          if (usesOrdinal(request.command))
            expected = attemptReply(msg, request.command, request.qty);
          if (expected || msg.phase == 4) {
            acknowledged = true;
            currentReplyAt = now;
          } else if (acknowledged) {
            trip = true;
          }
        }
      }
      portEXIT_CRITICAL(&linkMux);
    }
    if (now - lastSent >= 20) {
      lastSent = now;
      portENTER_CRITICAL(&linkMux);
      now = millis(); // uiAt and startedAt can change on the other core.
      if (running() &&
          (!havePeer || now - heardAt > STATUS_TIMEOUT_MS || now - uiAt > UI_TIMEOUT_MS ||
           (!acknowledged && now - startedAt >= DisplaySettings::ACK_TIMEOUT_MS) ||
           (acknowledged && now - currentReplyAt > STATUS_TIMEOUT_MS)))
        trip = true;
      Link::Control out = request;
      if (trip)
        out.command = 0;
      portEXIT_CRITICAL(&linkMux);
      portENTER_CRITICAL(&encMux);
      for (int i = 0; i < 3; i++)
        out.encoder[i] = int32_t(encoderRaw[i]);
      portEXIT_CRITICAL(&encMux);
      Link::send(Serial2, out);
    }
    // Sample while the TFT is busy. An old weight never acquires a new timestamp.
    Reading r{};
    if (sampleQueue && nextRaw(r.raw)) {
      r.at = millis();
      if (xQueueSend(sampleQueue, &r, 0) != pdTRUE) {
        Reading oldest;
        xQueueReceive(sampleQueue, &oldest, 0);
        xQueueSend(sampleQueue, &r, 0);
      }
    }
    vTaskDelay(pdMS_TO_TICKS(2));
  }
}
bool linkAlive() {
  return haveTask && snapshotValid && millis() - snapshotAt < STATUS_TIMEOUT_MS;
}
bool jobFresh() {
  return linkAlive() && status.job == request.job && status.session == request.session &&
         (!usesOrdinal(request.command) || attemptReply(status, request.command, request.qty));
}
bool linkReady() {
  return !running() && jobFresh() && status.phase == 0 && !status.fault;
}
bool wheelConfigured(uint8_t wheel) {
  return wheel >= 1 && wheel <= 6 && (status.configuredMask & (1U << (wheel - 1)));
}
static bool sendJob(uint8_t command, uint8_t wheel, uint8_t qty, bool newJob = true) {
  portENTER_CRITICAL(&linkMux);
  if (newJob && ++request.job == 0) { // start a fresh handshake before wrapping a job sequence
    request.session = esp_random() | 1U;
    havePeer = false;
    snapshotValid = false;
    portEXIT_CRITICAL(&linkMux);
    return false;
  }
  request.wheel = wheel;
  request.qty = qty;
  request.command = command;
  trip = false;
  acknowledged = false;
  startedAt = uiAt = millis();
  portEXIT_CRITICAL(&linkMux);
  return true;
}
bool nudge(uint8_t wheel, uint8_t piece, uint8_t attempt, float expectedBowlGrams) {
  refreshInputs(); // recheck weight and link after a possibly slow TFT redraw
  if (!piece || piece > 6 || !attempt || attempt > Link::maxAttempts(wheel) || !wheelConfigured(wheel))
    return false;
  float grams, margin;
  if (!isfinite(expectedBowlGrams) || !stableWeight(grams) || !weightMargin(margin) ||
      fabsf(grams - expectedBowlGrams) > margin)
    return false;

  if (piece == 1 && attempt == 1) {
    if (!linkReady() || fabsf(grams) > margin)
      return false;
  } else {
    if (request.command != Link::NUDGE || request.wheel != wheel ||
        !jobFresh() || status.phase != 3 || status.fault)
      return false;
    if (attempt == 1) {
      if (piece != currentPiece + 1)
        return false;
    } else if (piece != currentPiece || attempt != request.qty + 1) {
      return false;
    }
  }
  if (!sendJob(Link::NUDGE, wheel, attempt, attempt == 1))
    return false;
  currentPiece = piece;
  return true;
}
static bool startEmptyWheelBenchJob(uint8_t command) {
  refreshInputs();
  if (scaleSampling() || !linkReady() || !wheelConfigured(1))
    return false;
  return sendJob(command, 1, command == 3 ? 0 : 1);
}
bool startBench(bool spin) {
  return startEmptyWheelBenchJob(spin ? 3 : 1);
}
// Calibration only. Dedicated 15-degree diagnostic, independent of the dispense angle.
bool startBenchJog() {
  return startEmptyWheelBenchJob(Link::JOG);
}
bool startBenchRock() {
  return startEmptyWheelBenchJob(Link::ROCK);
}
bool startBenchRock2() {
  return startEmptyWheelBenchJob(Link::ROCK2);
}
bool startEdgeTest(float &emptyGrams, float &margin) {
  refreshInputs();
  if (!linkReady() || !wheelConfigured(1) || !weightMargin(margin) || !stableWeight(emptyGrams) ||
      fabsf(emptyGrams) > margin)
    return false;
  edgeDryRun = false;
  return sendJob(Link::EDGE, 1, 1);
}

static bool edgeBackedOff() {
  return request.command == Link::EDGE && request.wheel == 1 && request.qty == 1 &&
         jobFresh() && status.phase == 3 && status.indexed == Link::EDGE_BACKED_OFF &&
         !status.fault && wheelConfigured(1);
}

bool retryEdgeTest(float emptyGrams, uint32_t settledAt) {
  refreshInputs();
  float grams, margin;
  if (edgeDryRun || !edgeBackedOff() || !weightMargin(margin) || !stableWeightSince(settledAt, grams) ||
      !sampleSince(settledAt + Link::NUDGE_WAIT_MS) || fabsf(grams) > margin || fabsf(grams - emptyGrams) > margin)
    return false;
  return sendJob(Link::EDGE, 1, 2, false);
}
bool startEdgeDry() {
  refreshLink();
  if (!linkReady() || !wheelConfigured(1) || !sendJob(Link::EDGE, 1, 1))
    return false;
  edgeDryRun = true;
  return true;
}
bool retryEdgeDry(uint32_t stoppedAt) {
  refreshLink();
  const uint32_t dwell = millis() - stoppedAt;
  if (!edgeDryRun || !edgeBackedOff() || dwell < Link::NUDGE_WAIT_MS ||
      dwell >= Link::NUDGE_WAIT_MS + DisplaySettings::ACK_TIMEOUT_MS)
    return false;
  return sendJob(Link::EDGE, 1, 2, false);
}
void stop() {
  edgeDryRun = false;
  portENTER_CRITICAL(&linkMux);
  request.command = 0;
  currentPiece = 0;
  trip = false;
  portEXIT_CRITICAL(&linkMux);
}

// SERVICE. Read the actual local wall clock, including oscillator-loss flag and
// transaction result. No guessed calendar time is used for scheduling.
static bool rtcValid = false;
static uint32_t rtcEpoch = 0, rtcAt = 0, rtcLastPoll = 0;
static uint8_t bcd(uint8_t n) {
  return (n / 10) * 16 + n % 10;
}
static int dec(uint8_t v) {
  return ((v >> 4) > 9 || (v & 15) > 9) ? -1 : (v >> 4) * 10 + (v & 15);
}
static bool rtcRead(uint8_t reg, uint8_t *dest, uint8_t n) {
  Wire.beginTransmission(0x68);
  Wire.write(reg);
  if (Wire.endTransmission(false) != 0 || Wire.requestFrom(uint8_t(0x68), n) != n)
    return false;
  for (int i = 0; i < n; i++)
    dest[i] = Wire.read();
  return true;
}
static bool rtcWrite(uint8_t reg, const uint8_t *data, size_t n) {
  Wire.beginTransmission(0x68);
  Wire.write(reg);
  Wire.write(data, n);
  return Wire.endTransmission() == 0;
}
static void readClock() {
  uint8_t data[7], flags;
  rtcValid = false;
  if (!rtcRead(0, data, 7) || !rtcRead(15, &flags, 1) || (flags & 0x80) || (data[5] & 0x80))
    return;
  int sec = dec(data[0] & 127), minu = dec(data[1] & 127);
  int hour = dec(data[2] & 0x3f);
  if (data[2] & 0x40) {
    int h12 = dec(data[2] & 0x1f);
    if (h12 < 1 || h12 > 12)
      return;
    hour = h12 % 12 + ((data[2] & 0x20) ? 12 : 0);
  }
  int day = dec(data[4] & 63), month = dec(data[5] & 31), year = dec(data[6]);
  if (year < 0 || month < 1 || month > 12 || day < 1 || day > 31 || hour < 0 || hour > 23 ||
      minu < 0 || minu > 59 || sec < 0 || sec > 59)
    return;
  DateTime d(2000 + year, month, day, hour, minu, sec);
  if (!d.isValid())
    return;
  uint32_t epoch = d.unixtime();
  time_t system = time(nullptr);
  if (llabs(int64_t(epoch) - int64_t(system)) > 1) {
    timeval tv = {static_cast<time_t>(epoch), 0};
    settimeofday(&tv, nullptr);
  }
  rtcEpoch = epoch;
  rtcAt = millis();
  rtcValid = true;
}
bool clockNow(struct tm &t) {
  if (!rtcValid || millis() - rtcAt > 2500)
    return false;
  time_t epoch = rtcEpoch + (millis() - rtcAt) / 1000;
  return gmtime_r(&epoch, &t) != nullptr;
}
static bool setClock(const char *arg) {
  int yr, mo, dy, hr, mi, se, n = 0;
  if (sscanf(arg, "%d-%d-%d %d:%d:%d%n", &yr, &mo, &dy, &hr, &mi, &se, &n) != 6 || arg[n] ||
      yr < 2000 || yr > 2099 || mo < 1 || mo > 12 || dy < 1 || dy > 31 || hr < 0 || hr > 23 ||
      mi < 0 || mi > 59 || se < 0 || se > 59)
    return false;
  DateTime d(yr, mo, dy, hr, mi, se);
  if (!d.isValid())
    return false;
  uint8_t flags;
  if (!rtcRead(15, &flags, 1))
    return false;
  uint8_t b[] = {bcd(se), bcd(mi), bcd(hr),       uint8_t(d.dayOfTheWeek() + 1),
                 bcd(dy), bcd(mo), bcd(yr - 2000)};
  flags &= 0x7f;
  if (!rtcWrite(0, b, sizeof(b)) || !rtcWrite(15, &flags, 1))
    return false;
  readClock();
  return rtcValid && rtcEpoch >= d.unixtime() && rtcEpoch - d.unixtime() <= 1;
}

// SERVICE. One conversion at a time; never wait for an unplugged HX711.
// Channel A, gain 128. Keep each clock high interval below the power-down limit.
static bool nextRaw(int32_t &raw) {
  if (digitalRead(HX_DATA))
    return false;
  uint32_t bits = 0;
  portENTER_CRITICAL(&hxMux);
  for (int i = 0; i < 24; i++) {
    digitalWrite(HX_CLOCK, HIGH);
    delayMicroseconds(1);
    bits = (bits << 1) | digitalRead(HX_DATA);
    digitalWrite(HX_CLOCK, LOW);
    delayMicroseconds(1);
  }
  digitalWrite(HX_CLOCK, HIGH);
  delayMicroseconds(1);
  digitalWrite(HX_CLOCK, LOW);
  delayMicroseconds(1);
  bool busy = digitalRead(HX_DATA); // 25th pulse returns DOUT high until next conversion
  portEXIT_CRITICAL(&hxMux);
  raw = (bits & 0x800000) ? int32_t(bits | 0xff000000UL) : int32_t(bits);
  return busy && labs(raw) < 8388500;
}
struct ScaleSettings {
  float countsPerGram, margin;
};
static Preferences calibration;
static ScaleSettings cfg{};
static constexpr size_t WINDOW = 8, BATCH = 16;
static int32_t history[WINDOW]{};
static uint32_t sampleTimes[WINDOW]{};
static size_t histN = 0, pos = 0;
static uint32_t sampleAt = 0, batchAt = 0;
static bool tared = false;
static double zero = 0, emptySpan = 0;
enum class Operation { None, Tare, Cal, Verify };
static Operation op = Operation::None;
bool scaleSampling() {
  return op != Operation::None;
}
static bool motionActive() {
  return running() || (linkAlive() && (status.phase == 1 || status.phase == 2));
}
static int32_t samples[BATCH]{};
static size_t batchN = 0;
static bool discard = false;
static float refMass = 0;
static void stats(const int32_t *a, size_t n, double &mean, double &span) {
  int32_t lo = a[0], hi = a[0];
  int64_t sum = 0;
  for (size_t i = 0; i < n; i++) {
    sum += a[i];
    lo = min(lo, a[i]);
    hi = max(hi, a[i]);
  }
  mean = double(sum) / n;
  span = double(hi) - lo;
}
static bool calibrated() {
  return isfinite(cfg.countsPerGram) && fabs(cfg.countsPerGram) > 1;
}
bool weightMargin(float &g) {
  if (!tared || !calibrated() || !isfinite(cfg.margin) || cfg.margin <= 0 ||
      emptySpan / fabs(cfg.countsPerGram) * 3 > cfg.margin + 0.0001)
    return false;
  g = cfg.margin;
  return true;
}
bool scaleReady() {
  float m;
  return op == Operation::None && weightMargin(m) && histN == WINDOW && millis() - sampleAt < 500;
}
bool stableWeight(float &g) {
  if (!scaleReady())
    return false;
  double mean, span;
  stats(history, WINDOW, mean, span);
  if (span / fabs(cfg.countsPerGram) > cfg.margin)
    return false;
  g = (mean - zero) / cfg.countsPerGram;
  return isfinite(g);
}
// Oldest timestamp first once the circular buffer is full. Unsigned subtraction
// also works if the eight-sample window crosses millis() rollover.
bool stableWeightSince(uint32_t since, float &grams) {
  return stableWeight(grams) && millis() - sampleTimes[pos] <= millis() - since;
}
// The first conversion at or after the dwell deadline must reach the decision loop.
bool sampleSince(uint32_t since) {
  return histN && int32_t(sampleAt - since) >= 0;
}
static void saveCal() {
  if (calibration.putBytes("scale", &cfg, sizeof(cfg)) != sizeof(cfg))
    Serial.println("Scale settings could not be saved");
}
static void completeBatch() {
  double mean, span;
  stats(samples, BATCH, mean, span);
  if (op == Operation::Tare) {
    zero = mean;
    emptySpan = span;
    tared = true;
    Serial.println("Empty bowl zero recorded.");
  } else if (op == Operation::Cal) {
    const double delta = mean - zero;
    if (fabs(delta) < max(32., 12. * max(emptySpan, span)))
      Serial.println("CAL failed: weak or unstable reference; repeat with known mass.");
    else {
      cfg.countsPerGram = delta / refMass;
      cfg.margin = 0;
      saveCal();
      Serial.printf("Calibrated %.2f counts/g. Remove reference and run VERIFY with the lightest "
                    "test piece.\n",
                    cfg.countsPerGram);
    }
  } else if (op == Operation::Verify) {
    const float margin = max(0.015, 3. * max(emptySpan, span) / fabs(cfg.countsPerGram));
    const float measured = (mean - zero) / cfg.countsPerGram;
    if (measured <= 4 * margin)
      Serial.printf(
          "VERIFY failed: test piece %.3f g, noise margin %.3f g. Check mounting and repeat.\n",
          measured, margin);
    else {
      cfg.margin = margin;
      saveCal();
      Serial.printf("Verified tested mass %.3f g; margin %.3f g. Remove test piece before use.\n",
                    measured, margin);
    }
  }
  op = Operation::None;
  histN = 0;
  pos = 0;
}
static void readScale() {
  if (op != Operation::None && millis() - batchAt > 7000) {
    op = Operation::None;
    Serial.println("Scale acquisition timed out; check DAT, CLK and both supplies.");
  }
  Reading r;
  while (sampleQueue && xQueueReceive(sampleQueue, &r, 0) == pdTRUE) {
    if (r.at - sampleAt > 500) {
      histN = 0;
      pos = 0;
      if (op != Operation::None) {
        batchN = 0;
        discard = true;
      }
    }
    sampleAt = r.at;
    history[pos] = r.raw;
    sampleTimes[pos] = r.at;
    pos = (pos + 1) % WINDOW;
    if (histN < WINDOW)
      ++histN;
    if (op == Operation::None || int32_t(r.at - batchAt) < 0)
      continue;
    if (discard) {
      discard = false;
      continue;
    }
    samples[batchN++] = r.raw;
    if (batchN == BATCH)
      completeBatch();
  }
}
static void acquire(Operation wanted) {
  op = wanted;
  batchN = 0;
  discard = true;
  batchAt = millis();
  Serial.println("Sampling; keep the bowl still.");
}
bool tareEmpty() {
  if (motionActive() || scaleSampling())
    return false;
  tared = false;
  acquire(Operation::Tare);
  return true;
}
static void diagnostics() {
  float g;
  tm t{};
  Serial.printf("Link=%s phase=%u fault=%u indexed=%u configuredMask=0x%02X RTC=%s tare=%s "
                "sensor=%s counts/g=%.2f margin=%.3f g",
                linkAlive() ? "online" : "offline", status.phase, status.fault, status.indexed,
                status.configuredMask, clockNow(t) ? "set" : "unset", tared ? "yes" : "needed",
                (histN && millis() - sampleAt < 500) ? "online" : "waiting", cfg.countsPerGram,
                cfg.margin);
  if (clockNow(t))
    Serial.printf(" local=%04d-%02d-%02d %02d:%02d:%02d", t.tm_year + 1900, t.tm_mon + 1, t.tm_mday,
                  t.tm_hour, t.tm_min, t.tm_sec);
  if (jobFresh())
    Serial.printf(" job=%lu rawEncoder=%ld", (unsigned long)status.job, (long)status.encoder);
  if (histN && millis() - sampleAt < 500)
    Serial.printf(" rawHX=%ld", (long)history[(pos + WINDOW - 1) % WINDOW]);
  if (stableWeight(g))
    Serial.printf(" bowl=%.3f g", g);
  else if (tared && calibrated() && histN == WINDOW && millis() - sampleAt < 500) {
    double mean, span;
    stats(history, WINDOW, mean, span);
    Serial.printf(" bowlEstimate=%.3f g (stability unverified)", (mean - zero) / cfg.countsPerGram);
  }
  Serial.printf(" linkVersion=%u", unsigned(Link::VERSION));
  if (request.command == Link::NUDGE)
    Serial.printf(" piece=%u attempt=%u/%u", currentPiece, request.qty, Link::maxAttempts(request.wheel));
  else if (request.command == Link::JOG)
    Serial.print(" bench=JOG15");
  else if (request.command == Link::ROCK)
    Serial.print(" bench=ROCK");
  else if (request.command == Link::ROCK2)
    Serial.print(" bench=ROCK2");
  else if (request.command == Link::EDGE)
    Serial.printf(" bench=%s pass=%u", edgeDryRun ? "EDGEDRY" : "EDGETEST", unsigned(request.qty));
  Serial.println();
}
static void serviceCommand(char *line) {
  for (char *p = line; *p; ++p)
    *p = toupper(static_cast<unsigned char>(*p));
  if (::handleSetupCommand(line))
    return;
  if (!strcmp(line, "HELP")) {
    Serial.println("TIME YYYY-MM-DD HH:MM:SS | TARE (empty bowl) | CAL <known grams> | VERIFY "
                   "(smallest inert test piece) | STATUS");
    return;
  }
  if (!strcmp(line, "STATUS")) {
    diagnostics();
    return;
  }
  if (motionActive() || scaleSampling()) {
    Serial.println("Busy. Finish/abort the job or wait for sampling.");
    return;
  }
  if (!strcmp(line, "TARE")) {
    tareEmpty();
    return;
  }
  if (!strncmp(line, "TIME ", 5)) {
    Serial.println(setClock(line + 5) ? "Clock set and read back."
                                      : "Clock set failed; check date and RTC.");
    return;
  }
  if (!strncmp(line, "CAL ", 4) && tared) {
    char *end = nullptr;
    float g = strtof(line + 4, &end);
    if (*end == 0 && isfinite(g) && g >= 0.1 && g <= 100) {
      cfg.countsPerGram = 0;
      cfg.margin = 0;
      saveCal();
      refMass = g;
      acquire(Operation::Cal);
      return;
    }
  }
  if (!strcmp(line, "VERIFY") && tared && calibrated()) {
    cfg.margin = 0;
    saveCal();
    acquire(Operation::Verify);
    return;
  }
  Serial.println("Unrecognized or out of sequence. Send HELP.");
}
static void readSerial() {
  static char line[72];
  static size_t used = 0;
  static bool overflow = false;
  for (int i = 0; i < 80 && Serial.available(); i++) {
    char ch = Serial.read();
    if (ch == '\r' || ch == '\n') {
      if (used && !overflow) {
        line[used] = 0;
        serviceCommand(line);
      }
      used = 0;
      overflow = false;
    } else if (used + 1 < sizeof(line))
      line[used++] = ch;
    else
      overflow = true;
  }
}

void begin() {
  pinMode(HX_CLOCK, OUTPUT);
  digitalWrite(HX_CLOCK, LOW);
  pinMode(HX_DATA, INPUT);
  analogRead(32); // initialize ADC before enabling encoder IRQs
  Wire.begin(23, 22, 100000); // Original HUZZAH32 SDA and SCL header pins.
  Wire.setTimeOut(20);
  setenv("TZ", "UTC0", 1);
  tzset(); // DS3231 holds the local wall time entered by the user
  if (calibration.begin("p6hardware", false) && calibration.getBytesLength("scale") == sizeof(cfg))
    calibration.getBytes("scale", &cfg, sizeof(cfg));
  Serial2.begin(115200, SERIAL_8N1, UART_RX, UART_TX);
  request.session = esp_random() | 1U;
  uiAt = millis();
  sampleQueue = xQueueCreate(96, sizeof(Reading));
  haveTask = sampleQueue && xTaskCreatePinnedToCore(transportTask, "motion-link", 4096, nullptr, 2,
                                                    nullptr, 0) == pdPASS;
  readClock();
  rtcLastPoll = millis();
  Serial.printf("Scale-guided link v%u ready. Send HELP for clock, scale calibration and status.\n",
                unsigned(Link::VERSION));
}
static void refreshLink() {
  uint32_t now = millis();
  portENTER_CRITICAL(&linkMux);
  uiAt = now;
  status = remote;
  snapshotAt = heardAt;
  snapshotValid = havePeer;
  if (trip && running()) {
    status.session = request.session;
    status.job = request.job;
    status.phase = 4;
    status.fault = 4;
  }
  portEXIT_CRITICAL(&linkMux);
  enableInstalledEncoders(status.configuredMask);
}
static void refreshInputs() {
  refreshLink();
  readScale();
}
void poll() {
  refreshInputs();
  readSerial();
  const uint32_t now = millis();
  if (now - rtcLastPoll >= 1000) {
    rtcLastPoll = now;
    readClock();
  }
}
} // namespace HW
