/*
  Six-canister dispenser • micro-USB display controller (Adafruit ESP32 Feather).
  Start with DisplaySettings.h for user-adjustable timing and optional weight checks.
  This tab draws the pink menu, reads the two buttons/knob and stores RTC schedules.
  DispenseCycle.ino controls wheel requests, weight checks, count review and pickup.
  Hardware.cpp reads the clock, scale and encoders 4–6, and talks to the USB-C Feather.

  Normal cycle:
    1. A schedule or "Dispense now" requests a canister and quantity.
    2. C1 advances 60 degrees. If the settled scale shows no gain, the wheel
       backs up 15 degrees, returns, and the scale checks once more.
    3. The fixed bowl checks each drop. Count the visible items when prompted.
    4. Remove the items. A stable, empty bowl releases the next scheduled canister.
  Back stops a job for inspection. Interrupted or missed jobs are never replayed.
*/
#include <Arduino.h>
#if defined(ARDUINO_ARCH_ESP32) && !defined(ARDUINO_FEATHER_ESP32)
#error "For this display sketch, select Adafruit ESP32 Feather (original micro-USB HUZZAH32)."
#endif
#include <Adafruit_GFX.h>
#include <Adafruit_ILI9341.h>
#include <Preferences.h>
#include <time.h>
#include <math.h>
#include <stddef.h>
#include "Hardware.h"
#include "DisplaySettings.h"
using namespace DisplaySettings;

constexpr uint8_t TFT_CLK = 5, TFT_MOSI = 18, TFT_CS = 17, TFT_DC = 13;
constexpr uint8_t PIN_POT = 32, PIN_SELECT = 19, PIN_BACK = 26;
Adafruit_ILI9341 tft(TFT_CS, TFT_DC, TFT_MOSI, TFT_CLK, -1, -1);
Preferences prefs;
// ---------- Pink theme ----------
#define COLOR565(r, g, b) (uint16_t)((((r)&0xF8) << 8) | (((g)&0xFC) << 3) | ((b) >> 3))
const uint16_t COL_BG = COLOR565(255, 228, 238);
const uint16_t COL_TITLE = COLOR565(236, 72, 153);
const uint16_t COL_TEXT = COLOR565(110, 30, 75);
const uint16_t COL_HI = COLOR565(255, 105, 180);
const uint16_t COL_HI_TEXT = 0xFFFF;
const uint16_t COL_HINT = COLOR565(180, 100, 140);
const uint16_t COL_SOFT = COLOR565(255, 182, 213);
const uint16_t COL_WARN = COLOR565(200, 0, 70);

const int TITLE_H = 40;
const int ROW_H = 34;
const int LIST_BOTTOM = 218;

// Persistent schedule format. Legacy four-byte rows have NO known canister.
struct Dose {
  uint8_t days, hour, minute, qty, wheel;
};
static_assert(sizeof(Dose) == 5, "Unexpected schedule layout");
constexpr int MAX_DOSES = 12;
struct ScheduleStore {
  uint32_t magic;
  uint16_t version;
  uint8_t count, reserved;
  Dose entries[MAX_DOSES];
  uint32_t checksum;
};
constexpr uint32_t STORE_MAGIC = 0x50494C33UL;
constexpr uint16_t STORE_VERSION = 3;
Dose doses[MAX_DOSES]{};
int doseCount = 0;
Dose draft{};
int editIndex = -1, actionIndex = -1;
const uint8_t EVERY_DAY = 0x7F, WEEKDAYS = 0x1F, WEEKENDS = 0x60;
const char *DAY2[] = {"Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"};
const char DAY1[] = "MTWTFSS";
const char *WDAY[] = {"Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"};
const char *WDAY_LONG[] = {"Sunday",   "Monday", "Tuesday", "Wednesday",
                           "Thursday", "Friday", "Saturday"};
const char *MONTHS[] = {"Jan", "Feb", "Mar", "Apr", "May", "Jun",
                        "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"};

enum State { ST_IDLE, ST_SETTINGS, ST_DISPENSING, ST_CHECKING, ST_REVIEW, ST_WAITING, ST_ALARM };
enum Screen {
  SCR_MAIN,
  SCR_WHEEL,
  SCR_DAYS,
  SCR_HOUR,
  SCR_MINUTE,
  SCR_QTY,
  SCR_CONFIRM,
  SCR_VIEW,
  SCR_DOSE,
  SCR_DELETE,
  SCR_CLEAR,
  SCR_MESSAGE,
  SCR_MANUAL_WHEEL,
  SCR_MANUAL_QTY,
  SCR_MANUAL_CONFIRM,
  SCR_TARE
};
enum BtnEvent { BTN_NONE, BTN_SHORT, BTN_LONG };
struct Button {
  uint8_t pin;
  bool stable = HIGH, lastRead = HIGH, armed = false, holdFired = false;
  uint32_t changed = 0, pressedAt = 0;
};
Button selBtn{PIN_SELECT}, backBtn{PIN_BACK};
State state = ST_IDLE;
Screen screen = SCR_MAIN;
uint32_t stateStartMs = 0, messageUntil = 0, lastKnobMs = 0;
bool messageToIdle = false;
int sel = -1, listCount = 0, listTop = 0, listY = 48, rowsVisible = 5, pickN = 0;
char listBuf[MAX_DOSES + 1][28];
int8_t rowCheck[MAX_DOSES + 1];
uint8_t manualWheel = 1, manualQty = 1, activeWheel = 0, requestedQty = 0;
uint8_t detectedDrops = 0, nudgeAttempt = 0;
uint32_t jobStartedMs = 0, reminderAt = 0;
uint32_t lastIdlePollMs = 0;
int lastIdleMinute = -1, lastSetupBits = -1;
bool activeJob = false, countConfirmed = false, storageReady = false, pendingInspection = false;
bool scheduleNotice = false, clockWentBackward = false;
float bowlBaseline = 0, pieceBaseline = 0, doseWeight = NAN, acceptedMargin = 0;
bool sawGainDuringWait = false;
uint64_t lastAttemptMinute = 0, lastObservedMinute = 0, lastTaken = 0;
char alarmMsg[32] = "";
Dose batch[MAX_DOSES]{};
uint8_t batchCount = 0, batchNext = 0;
uint32_t batchStartedMs = 0, batchWaitMs = 0;

// Explicit declarations also document the event-checker/service boundary.
void enterIdle();
void enterSettings();
void enterScreen(Screen s);
void enterAlarm(const char *msg);
void startDispense(uint8_t wheel, uint8_t qty);
void printSchedule();
bool inCalibration = true;
bool calibrationDose = false; // ST_IDLE means queued; all dose states still use the usual handlers.
void openCalibration();
void benchStop(const char *message);
void calibrationLoop(BtnEvent e);
bool handleSetupCommand(const char *line);
bool saveSchedule(const Dose *data, int count);
bool validDose(const Dose &d, bool allowUnassigned);
bool overlapsSchedule(const Dose &d, int ignore);

// INPUT ACQUISITION: debounce physical momentary contacts; no startup press event.
BtnEvent updateButton(Button &b, bool immediate = false) {
  const bool raw = digitalRead(b.pin);
  const uint32_t now = millis();
  if (raw != b.lastRead) {
    b.changed = now;
    b.lastRead = raw;
  }
  if (now - b.changed < BUTTON_DEBOUNCE_MS)
    return BTN_NONE;
  if (!b.armed) {
    b.stable = raw;
    if (raw == HIGH)
      b.armed = true;
    return BTN_NONE;
  }
  BtnEvent e = BTN_NONE;
  if (raw != b.stable) {
    b.stable = raw;
    if (raw == LOW) {
      b.pressedAt = now;
      b.holdFired = false;
      if (immediate)
        e = BTN_LONG;
    } else if (!immediate && !b.holdFired)
      e = BTN_SHORT;
  }
  if (!immediate && b.stable == LOW && !b.holdFired && now - b.pressedAt >= SELECT_HOLD_MS) {
    b.holdFired = true;
    e = BTN_LONG;
  }
  return e;
}
bool isPicker(Screen s) {
  return s == SCR_HOUR || s == SCR_MINUTE || s == SCR_QTY || s == SCR_WHEEL ||
         s == SCR_MANUAL_WHEEL || s == SCR_MANUAL_QTY;
}
void formatTime(uint8_t h, uint8_t m, char *out) {
  const int h12 = h % 12 ? h % 12 : 12;
  sprintf(out, "%d:%02d %s", h12, m, h < 12 ? "AM" : "PM");
}
void daysText(uint8_t m, char *out) {
  if (m == EVERY_DAY) {
    strcpy(out, "Every day");
    return;
  }
  if (m == WEEKDAYS) {
    strcpy(out, "Weekdays");
    return;
  }
  if (m == WEEKENDS) {
    strcpy(out, "Weekends");
    return;
  }
  out[0] = 0;
  for (int i = 0; i < 7; i++)
    if (m & (1 << i)) {
      if (out[0])
        strcat(out, " ");
      strcat(out, DAY2[i]);
    }
}
void daysPattern(uint8_t m, char *out) {
  for (int i = 0; i < 7; i++)
    out[i] = (m & (1 << i)) ? DAY1[i] : '-';
  out[7] = 0;
}
void doseLine(const Dose &d, char *out) {
  char t[12], p[8];
  formatTime(d.hour, d.minute, t);
  daysPattern(d.days, p);
  snprintf(out, 28, "C%c %s %s x%u", d.wheel ? char('0' + d.wheel) : '?', p, t, d.qty);
}
// PURE CHECKERS: schedule validity and overlapping days/minutes.
bool validDose(const Dose &d, bool allowUnassigned) {
  return d.days && !(d.days & 0x80) && d.hour < 24 && d.minute < 60 && d.qty >= 1 && d.qty <= 6 &&
         d.wheel <= 6 && (allowUnassigned || d.wheel >= 1);
}
bool overlapsSchedule(const Dose &d, int ignore) {
  for (int i = 0; i < doseCount; i++)
    if (i != ignore && doses[i].wheel && d.wheel == doses[i].wheel && (d.days & doses[i].days) &&
        d.hour == doses[i].hour && d.minute == doses[i].minute)
      return true;
  return false;
}
uint32_t storeChecksum(const ScheduleStore &s) {
  const uint8_t *p = reinterpret_cast<const uint8_t *>(&s);
  uint32_t h = 2166136261UL;
  for (size_t i = 0; i < offsetof(ScheduleStore, checksum); i++) {
    h ^= p[i];
    h *= 16777619UL;
  }
  return h;
}
// SERVICE: persist one versioned blob, then replace RAM only after successful write.
bool saveSchedule(const Dose *data, int count) {
  if (!storageReady || count < 0 || count > MAX_DOSES)
    return false;
  ScheduleStore s{};
  s.magic = STORE_MAGIC;
  s.version = STORE_VERSION;
  s.count = count;
  for (int i = 0; i < count; i++) {
    if (!validDose(data[i], true))
      return false;
    s.entries[i] = data[i];
  }
  for (int i = 1; i < count; i++) {
    Dose d = s.entries[i];
    int j = i - 1;
    while (j >= 0 && s.entries[j].hour * 60 + s.entries[j].minute > d.hour * 60 + d.minute) {
      s.entries[j + 1] = s.entries[j];
      j--;
    }
    s.entries[j + 1] = d;
  }
  s.checksum = storeChecksum(s);
  if (prefs.putBytes("store3", &s, sizeof(s)) != sizeof(s))
    return false;
  memcpy(doses, s.entries, sizeof(doses));
  doseCount = count;
  return true;
}
// SERVICE: legacy rows become C? and cannot trigger until deliberately edited.
void loadSchedule() {
  lastAttemptMinute = prefs.getULong64("lastMin", 0);
  lastTaken = prefs.getULong64("clearedAt", 0);
  pendingInspection = prefs.getBool("pending", false);
  scheduleNotice = prefs.getBool("missed", false);
  if (prefs.getBool("batch", false)) {
    // A snapshot queue is deliberately not replayed after a restart.
    pendingInspection = true;
    scheduleNotice = true;
    if (prefs.putBool("pending", true) != 1 || prefs.putBool("missed", true) != 1 ||
        prefs.putBool("batch", false) != 1)
      storageReady = false;
    Serial.println(
        "RESTART: interrupted dose group discarded; inspect bowl and review missing doses.");
  }
  const size_t bytes = prefs.getBytesLength("store3");
  if (bytes) {
    ScheduleStore s{};
    if (bytes != sizeof(s) || prefs.getBytes("store3", &s, sizeof(s)) != sizeof(s) ||
        s.magic != STORE_MAGIC || s.version != STORE_VERSION || s.count > MAX_DOSES ||
        s.checksum != storeChecksum(s)) {
      storageReady = false;
      return;
    }
    for (int i = 0; i < s.count; i++)
      if (!validDose(s.entries[i], true)) {
        storageReady = false;
        return;
      }
    memcpy(doses, s.entries, sizeof(doses));
    doseCount = s.count;
    // Even structurally valid data must not bypass the overlap policy.
    for (int i = 0; i < doseCount; i++)
      if (doses[i].wheel && overlapsSchedule(doses[i], i)) {
        storageReady = false;
        return;
      }
    return;
  }
  const int oldCount = prefs.getUChar("count", 0);
  const size_t oldBytes = prefs.getBytesLength("doses");
  if (oldCount < 0 || oldCount > MAX_DOSES) {
    storageReady = false;
    return;
  }
  if (oldCount) {
    uint8_t old[MAX_DOSES * 4]{};
    if (oldBytes != size_t(oldCount * 4) || prefs.getBytes("doses", old, sizeof(old)) != oldBytes) {
      storageReady = false;
      return;
    }
    for (int i = 0; i < oldCount; i++) {
      Dose d{old[i * 4], old[i * 4 + 1], old[i * 4 + 2], old[i * 4 + 3], 0};
      if (!validDose(d, true)) {
        storageReady = false;
        return;
      }
      doses[doseCount++] = d;
    }
    Serial.println("MIGRATION: legacy schedules are UNASSIGNED; edit each to choose its canister.");
    if (!saveSchedule(doses, doseCount))
      storageReady = false;
  }
}
void printSchedule() {
  Serial.printf("Schedule: %d entries; C? entries are disabled.\n", doseCount);
  char line[28];
  for (int i = 0; i < doseCount; i++) {
    doseLine(doses[i], line);
    Serial.println(line);
  }
}
uint64_t minuteKey(struct tm t) {
  const time_t now = mktime(&t);
  return now > 0 ? uint64_t(now) / 60ULL : 0;
}
// SERVICE: visible persistent missed-dose alert. No automatic replacement dose.
void markMissed(const char *why) {
  scheduleNotice = true;
  if (prefs.putBool("missed", true) != 1)
    storageReady = false;
  Serial.printf("SCHEDULE MISSED / inspect: %s. No automatic retry.\n", why);
}
// ---------- Drawing basics ----------
void drawHeart(int x, int y, int r, uint16_t c) {
  tft.fillCircle(x - r, y, r, c);
  tft.fillCircle(x + r, y, r, c);
  tft.fillTriangle(x - 2 * r, y + r / 3, x + 2 * r, y + r / 3, x, y + 2 * r + r / 2, c);
}

void drawTitleColor(const char *title, uint16_t bar) {
  tft.fillRect(0, 0, 320, TITLE_H, bar);
  tft.setTextColor(COL_HI_TEXT);
  tft.setTextSize(2);
  tft.setCursor(12, 12);
  tft.print(title);
  drawHeart(298, 15, 5, COL_HI_TEXT);
}

void drawTitle(const char *title) {
  drawTitleColor(title, COL_TITLE);
}

void drawHintColor(const char *hint, uint16_t color) {
  tft.fillRect(0, 222, 320, 18, COL_BG);
  tft.setTextColor(color);
  tft.setTextSize(1);
  tft.setCursor(10, 228);
  tft.print(hint);
}

void drawHint(const char *hint) {
  drawHintColor(hint, COL_HINT);
}

// Prints text centered across the screen
void centerText(const char *s, int y, int size, uint16_t color) {
  while (size > 1 && (int)strlen(s) * 6 * size > 308)
    --size;
  tft.setTextSize(size);
  tft.setTextColor(color);
  tft.setCursor((320 - (int)strlen(s) * 6 * size) / 2, y);
  tft.print(s);
}

// IDLE AND SCHEDULING
int nextDose(const struct tm &t, int &daysAhead) {
  const int nowMin = t.tm_hour * 60 + t.tm_min;
  int best = -1, bestMins = 100000;
  for (int i = 0; i < doseCount; i++) {
    if (!doses[i].wheel)
      continue;
    for (int off = 0; off < 8; off++) {
      const int wday = (t.tm_wday + off) % 7;
      const uint8_t bit = 1 << ((wday + 6) % 7);
      if (!(doses[i].days & bit))
        continue;
      int mins = off * 1440 + doses[i].hour * 60 + doses[i].minute - nowMin;
      if (mins < 0)
        continue;
      // Already attempted this minute: show the next occurrence instead.
      if (mins == 0 && minuteKey(t) <= lastAttemptMinute)
        continue;
      if (mins < bestMins) {
        bestMins = mins;
        best = i;
        daysAhead = off;
      }
      break;
    }
  }
  return best;
}
int setupBits() {
  struct tm t {};
  float margin = 0;
  int bits = (!HW::linkReady() ? 1 : 0) | (!HW::scaleReady() || !HW::weightMargin(margin) ? 2 : 0) |
             (!HW::clockNow(t) ? 4 : 0);
  if (!storageReady)
    bits |= 8;
  for (int i = 0; i < doseCount; i++)
    if (!doses[i].wheel)
      bits |= 16;
  if (HW::linkReady() && HW::status.configuredMask == 0)
    bits |= 128;
  if (scheduleNotice)
    bits |= 32;
  if (clockWentBackward)
    bits |= 64;
  return bits;
}
void drawIdleBody() {
  struct tm t {};
  const bool clock = HW::clockNow(t);
  char buf[48], tt[12];
  tft.fillRect(0, TITLE_H, 320, 222 - TITLE_H, COL_BG);
  if (clock) {
    formatTime(t.tm_hour, t.tm_min, tt);
    centerText(tt, 56, 5, COL_TEXT);
    snprintf(buf, sizeof(buf), "%s, %s %d", WDAY_LONG[t.tm_wday], MONTHS[t.tm_mon], t.tm_mday);
    centerText(buf, 104, 2, COL_HINT);
    int ahead = 0, n = nextDose(t, ahead);
    if (n < 0)
      centerText("No active schedules", 140, 2, COL_TITLE);
    else {
      char when[12];
      formatTime(doses[n].hour, doses[n].minute, when);
      if (ahead == 0)
        snprintf(buf, sizeof(buf), "Next C%u: %s x%u", doses[n].wheel, when, doses[n].qty);
      else
        snprintf(buf, sizeof(buf), "C%u %s %s x%u", doses[n].wheel, WDAY[(t.tm_wday + ahead) % 7],
                 when, doses[n].qty);
      centerText(buf, 140, 2, COL_TITLE);
    }
  } else {
    centerText("Clock setup needed", 64, 2, COL_WARN);
    centerText("Schedules are paused", 104, 2, COL_HINT);
    centerText("USB: HELP / clock setup", 140, 1, COL_HINT);
  }
  if (lastTaken) {
    const time_t stamp = time_t(lastTaken);
    struct tm lt {};
    localtime_r(&stamp, &lt);
    formatTime(lt.tm_hour, lt.tm_min, tt);
    snprintf(buf, sizeof(buf), "Last cleared: %s %s", WDAY[lt.tm_wday], tt);
    centerText(buf, 176, 2, COL_HINT);
  }
  if (batchCount && batchNext < batchCount) {
    tft.fillRect(0, 136, 320, 64, COL_BG);
    snprintf(buf, sizeof(buf), "Next in group: C%u x%u", batch[batchNext].wheel,
             batch[batchNext].qty);
    centerText(buf, 140, 2, COL_TITLE);
    centerText("Empty bowl to continue", 176, 2, COL_HINT);
  }
  const int bits = setupBits();
  lastSetupBits = bits;
  const char *status = "Ready: empty bowl before each dose";
  if (bits & 8)
    status = "Storage error: no dispensing";
  else if (bits & 1)
    status = "Motor link setup needed";
  else if (bits & 2)
    status = "USB: HELP / scale setup needed";
  else if (bits & 128)
    status = "Set up wheels in motor settings";
  else if (bits & 64)
    status = "Clock moved back: inspect schedule";
  else if (bits & 32)
    status = "MISSED DOSE: review menu alert / USB log";
  else if (bits & 16)
    status = "C? schedules: edit to assign canister";
  centerText(status, 205, 1, bits ? COL_WARN : COL_HINT);
}
// SERVICE S01: return to idle only after a completed inspection/acknowledgement.
void enterIdle() {
  if (calibrationDose) {
    openCalibration();
    Serial.println("Returned to calibration. Schedules remain paused.");
    return;
  }
  HW::stop();
  activeJob = false;
  state = ST_IDLE;
  stateStartMs = millis();
  tft.fillScreen(COL_BG);
  drawTitle("Pill Dispenser");
  drawIdleBody();
  drawHint(batchCount ? "Empty bowl for next canister. BACK: cancel group"
                      : "SELECT: menu & settings   BACK: cancel");
  struct tm t {};
  lastIdleMinute = HW::clockNow(t) ? t.tm_min : -1;
  Serial.println("STATE 0: Idling");
}
// EVENT CHECKER E01 + SERVICE: consume due minute, snapshot a sequential group.
// Called in ALL states, so schedules arriving while busy become visible missed alerts.
void checkSchedule() {
  struct tm t {};
  if (!HW::clockNow(t))
    return;
  const uint64_t key = minuteKey(t);
  if (!key || key == lastObservedMinute)
    return;
  if (lastObservedMinute && key < lastObservedMinute) {
    clockWentBackward = true;
    markMissed("clock moved backward; past attempts will not be repeated");
  }
  if (lastObservedMinute && key > lastObservedMinute + 1)
    markMissed("clock gap: review doses during the missing interval");
  lastObservedMinute = key;
  if (key <= lastAttemptMinute)
    return;
  const uint8_t bit = 1 << ((t.tm_wday + 6) % 7);
  Dose due[MAX_DOSES]{};
  uint8_t dueCount = 0, wheels = 0;
  bool conflict = false;
  for (int i = 0; i < doseCount; i++)
    if (doses[i].wheel && (doses[i].days & bit) && doses[i].hour == t.tm_hour &&
        doses[i].minute == t.tm_min) {
      const uint8_t wheelBit = 1 << (doses[i].wheel - 1);
      if (wheels & wheelBit)
        conflict = true;
      wheels |= wheelBit;
      due[dueCount++] = doses[i];
    }
  if (!dueCount)
    return;
  const bool available =
      state == ST_IDLE && !pendingInspection && !batchCount && !clockWentBackward && !conflict;
  // Record an interruption marker BEFORE the minute highwater. A reset in the
  // two-write window therefore raises inspection instead of losing a group silently.
  if (!storageReady) {
    enterAlarm("STORAGE ERROR");
    return;
  }
  if (available) {
    if (prefs.putBool("batch", true) != 1) {
      storageReady = false;
      enterAlarm("STORAGE ERROR");
      return;
    }
  } else {
    markMissed(conflict ? "duplicate canister/time"
                        : (clockWentBackward ? "clock correction needs review"
                                             : "dispenser busy / inspection pending"));
  }
  if (!storageReady || prefs.putULong64("lastMin", key) != sizeof(uint64_t)) {
    storageReady = false;
    enterAlarm("STORAGE ERROR");
    return;
  }
  lastAttemptMinute = key; // Persist BEFORE start; never rerun this minute after reset.
  if (!available) {
    if (conflict)
      enterAlarm("SCHEDULE CONFLICT");
    return;
  }
  memcpy(batch, due, sizeof(batch));
  batchCount = dueCount;
  batchNext = 1;
  batchStartedMs = millis();
  Serial.printf("SCHEDULE group: %u canister(s), sequential jobs, %lu s start window.\n", dueCount,
                (unsigned long)(BATCH_START_WINDOW_MS / 1000));
  startDispense(batch[0].wheel, batch[0].qty);
}
// SERVICE: cancel only future members; the currently active job retains its inspection marker.
void discardRemainingBatch(const char *reason) {
  if (!batchCount)
    return;
  Serial.printf("GROUP stopped: %s; %u unstarted canister jobs require manual review.\n", reason,
                unsigned(batchCount - batchNext));
  markMissed(reason);
  batchCount = 0;
  batchNext = 0;
  if (prefs.putBool("batch", false) != 1)
    storageReady = false;
}
// EVENT CHECKER E05: start another canister only after clear/empty and peer STOP acknowledgement.
bool serviceQueuedBatch(BtnEvent e) {
  if (!batchCount)
    return false;
  if (e == BTN_LONG) {
    enterAlarm("GROUP CANCELLED");
    return true;
  }
  if (millis() - batchStartedMs >= BATCH_START_WINDOW_MS) {
    enterAlarm("GROUP EXPIRED");
    return true;
  }
  if (batchNext >= batchCount)
    return false;
  if (!HW::linkAlive()) {
    enterAlarm("LINK LOST");
    return true;
  }
  if (!HW::scaleReady()) {
    enterAlarm("SCALE FAULT");
    return true;
  }
  if (!HW::linkReady() || HW::status.phase != 0) {
    if (millis() - batchWaitMs >= NEXT_IDLE_TIMEOUT_MS)
      enterAlarm("STOP NOT CONFIRMED");
    return true;
  }
  float g = 0, margin = 0;
  if (!HW::weightMargin(margin) || !HW::stableWeight(g) || !isfinite(g) || fabsf(g) > margin)
    return true; // Visible prompt waits for a genuinely empty bowl; no use of acknowledgement as
                 // weight evidence.
  const Dose next = batch[batchNext++];
  startDispense(next.wheel, next.qty);
  return true;
}
void idleLoop(BtnEvent e) {
  if (serviceQueuedBatch(e))
    return;
  if (e == BTN_SHORT) {
    enterSettings();
    return;
  }
  if (millis() - lastIdlePollMs < 1000)
    return;
  lastIdlePollMs = millis();
  struct tm t {};
  const int minute = HW::clockNow(t) ? t.tm_min : -1;
  if (minute != lastIdleMinute || setupBits() != lastSetupBits) {
    lastIdleMinute = minute;
    drawIdleBody();
  }
}
int readKnobRaw() {
  long s = 0;
  for (int i = 0; i < 16; i++)
    s += analogRead(PIN_POT);
  return s / 16;
}

int knobIndex(int n, int current) {
  if (n <= 0)
    return -1;
  int raw = readKnobRaw();
  float zone = 4096.0 / n;
  int idx = constrain((int)(raw / zone), 0, n - 1);
  if (current >= 0 && current < n && idx != current) {
    float lo = current * zone - zone * 0.25;
    float hi = (current + 1) * zone + zone * 0.25;
    if (raw > lo && raw < hi)
      return current;
  }
  return idx;
}

void drawRow(int i, bool highlighted) {
  int row = i - listTop;
  if (i < 0 || row < 0 || row >= rowsVisible)
    return;
  int y = listY + row * ROW_H;
  tft.fillRect(0, y, 320, ROW_H - 2, COL_BG);
  if (highlighted)
    tft.fillRoundRect(6, y, 308, ROW_H - 4, 10, COL_HI);
  int tx = 18;
  if (rowCheck[i] >= 0) {
    int bx = 16, by = y + 5;
    uint16_t boxCol = highlighted ? COL_HI_TEXT : COL_TITLE;
    if (rowCheck[i]) {
      tft.fillRoundRect(bx, by, 20, 20, 5, boxCol);
      uint16_t tick = highlighted ? COL_HI : COL_HI_TEXT;
      tft.drawLine(bx + 4, by + 10, bx + 8, by + 15, tick);
      tft.drawLine(bx + 5, by + 10, bx + 9, by + 15, tick);
      tft.drawLine(bx + 8, by + 15, bx + 16, by + 5, tick);
      tft.drawLine(bx + 9, by + 15, bx + 17, by + 5, tick);
    } else {
      tft.drawRoundRect(bx, by, 20, 20, 5, boxCol);
      tft.drawRoundRect(bx + 1, by + 1, 18, 18, 4, boxCol);
    }
    tx = 46;
  }
  tft.setTextColor(highlighted ? COL_HI_TEXT : COL_TEXT);
  tft.setTextSize(2);
  tft.setCursor(tx, y + 8);
  tft.print(listBuf[i]);
}

void drawListAll() {
  tft.fillRect(0, listY, 320, rowsVisible * ROW_H, COL_BG);
  for (int i = listTop; i < listCount && i < listTop + rowsVisible; i++)
    drawRow(i, i == sel);
}

void moveListSelection(int newSel) {
  if (newSel == sel)
    return;
  int old = sel;
  sel = newSel;
  if (sel < listTop) {
    listTop = sel;
    drawListAll();
  } else if (sel >= listTop + rowsVisible) {
    listTop = sel - rowsVisible + 1;
    drawListAll();
  } else {
    drawRow(old, false);
    drawRow(sel, true);
  }
}

void setList(const char *const items[], int n) {
  listCount = n;
  for (int i = 0; i < n; i++) {
    strncpy(listBuf[i], items[i], 27);
    listBuf[i][27] = '\0';
    rowCheck[i] = -1;
  }
}

void setDayChecks() {
  rowCheck[0] = -1;
  rowCheck[1] = (draft.days == EVERY_DAY);
  rowCheck[2] = (draft.days == WEEKDAYS);
  rowCheck[3] = (draft.days == WEEKENDS);
  for (int i = 0; i < 7; i++)
    rowCheck[4 + i] = (draft.days >> i) & 1;
}

void pickerLabel(int i, char *out) {
  switch (screen) {
  case SCR_HOUR: {
    int h12 = i % 12;
    if (h12 == 0)
      h12 = 12;
    sprintf(out, "%d %s", h12, i < 12 ? "AM" : "PM");
    break;
  }
  case SCR_MINUTE:
    formatTime(draft.hour, i * MINUTE_STEP, out);
    break;
  case SCR_QTY:
    sprintf(out, "%d pill%s", i + 1, i == 0 ? "" : "s");
    break;
  case SCR_WHEEL:
  case SCR_MANUAL_WHEEL:
    sprintf(out, "Canister %d", i + 1);
    break;
  case SCR_MANUAL_QTY:
    sprintf(out, "%d pill%s", i + 1, i == 0 ? "" : "s");
    break;
  default:
    out[0] = '\0';
  }
}

void drawPickerValue() {
  char buf[16];
  pickerLabel(sel, buf);
  tft.fillRect(0, 95, 320, 50, COL_BG);
  centerText(buf, 104, 4, COL_TEXT);
  int x0 = 40, barW = 240, segW = barW / pickN;
  tft.fillRoundRect(x0, 165, barW, 10, 5, COL_SOFT);
  tft.fillRoundRect(x0 + sel * segW, 165, max(segW, 10), 10, 5, COL_TITLE);
}

void drawSummary(const Dose &d) {
  char days[24], t[12], line[32];
  daysText(d.days, days);
  formatTime(d.hour, d.minute, t);
  tft.setTextColor(COL_TITLE);
  tft.setTextSize(strlen(days) <= 14 ? 3 : 2);
  tft.setCursor(14, 52);
  tft.print(days);
  tft.setTextColor(COL_TEXT);
  tft.setTextSize(2);
  snprintf(line, sizeof(line), "C%c  %s  x%u", d.wheel ? char('0' + d.wheel) : '?', t, d.qty);
  tft.setCursor(14, 86);
  tft.print(line);
}

void showMessage(const char *msg, bool toIdle) {
  screen = SCR_MESSAGE;
  sel = -1;
  messageToIdle = toIdle;
  tft.fillScreen(COL_BG);
  drawHeart(160, 78, 14, COL_HI);
  centerText(msg, 130, 3, COL_TITLE);
  messageUntil = millis() + 1500;
}

void enterScreen(Screen s) {
  screen = s;
  sel = -1;
  listTop = 0;
  listY = 48;
  tft.fillScreen(COL_BG);

  switch (s) {
  case SCR_MAIN: {
    drawTitle("Menu");
    const char *items[] = {"Add a dose",     "View schedule",       "Clear schedule",
                           "Dispense now",   "Review missed alert", "Zero empty bowl",
                           "< Back to clock"};
    setList(items, 7);
    drawHint("Turn knob   SELECT: choose   BACK: return");
    break;
  }
  case SCR_WHEEL:
    drawTitle("Step 1 of 5: Canister");
    pickN = 6;
    break;
  case SCR_MANUAL_WHEEL:
    drawTitle("Dispense: canister");
    pickN = 6;
    break;
  case SCR_MANUAL_QTY:
    drawTitle("Dispense: quantity");
    pickN = 6;
    break;
  case SCR_MANUAL_CONFIRM: {
    drawTitle("Dispense now?");
    char summary[30];
    snprintf(summary, sizeof(summary), "Canister %u  x%u", manualWheel, manualQty);
    centerText(summary, 68, 2, COL_TEXT);
    listY = 112;
    const char *items[] = {"Dispense", "Cancel"};
    setList(items, 2);
    drawHint("Empty bowl required. BACK: cancel");
    break;
  }
  case SCR_TARE: {
    drawTitle("Zero empty bowl?");
    centerText("Remove all pills first", 66, 2, COL_TEXT);
    centerText("Keep the fixed bowl installed", 94, 1, COL_HINT);
    listY = 112;
    const char *items[] = {"Cancel", "Zero empty bowl"};
    setList(items, 2);
    drawHint("Only zero a known EMPTY bowl. BACK: cancel");
    break;
  }
  case SCR_DAYS: {
    drawTitle("Step 2 of 5: Days");
    const char *items[] = {"Next  >",   "Every day", "Weekdays", "Weekends", "Monday", "Tuesday",
                           "Wednesday", "Thursday",  "Friday",   "Saturday", "Sunday"};
    setList(items, 11);
    setDayChecks();
    drawHint("Press: tick a day    Then choose Next    BACK: return");
    break;
  }
  case SCR_HOUR:
    drawTitle("Step 3 of 5: Hour");
    pickN = 24;
    break;
  case SCR_MINUTE:
    drawTitle("Step 4 of 5: Minute");
    pickN = 60 / MINUTE_STEP;
    break;
  case SCR_QTY:
    drawTitle("Step 5 of 5: Pills");
    pickN = 6;
    break;

  case SCR_CONFIRM: {
    drawTitle(editIndex >= 0 ? "Save changes?" : "Save this dose?");
    drawSummary(draft);
    listY = 112;
    const char *items[] = {"Save", "Cancel"};
    setList(items, 2);
    drawHint("Press: choose     BACK: return");
    break;
  }
  case SCR_VIEW: {
    drawTitle("Your schedule");
    strcpy(listBuf[0], "< Back");
    rowCheck[0] = -1;
    for (int i = 0; i < doseCount; i++) {
      doseLine(doses[i], listBuf[i + 1]);
      rowCheck[i + 1] = -1;
    }
    listCount = doseCount + 1;
    drawHint(doseCount ? "Pick a dose to edit, copy or delete     BACK: return"
                       : "No doses yet     BACK: return");
    break;
  }
  case SCR_DOSE: {
    drawTitle("This dose");
    drawSummary(doses[actionIndex]);
    listY = 112;
    const char *items[] = {"Edit", "Duplicate", "Delete"};
    setList(items, 3);
    drawHint("Duplicate = copy it, then change days or time");
    break;
  }
  case SCR_DELETE: {
    drawTitle("Delete this dose?");
    drawSummary(doses[actionIndex]);
    listY = 112;
    const char *items[] = {"No, keep it", "Yes, delete"};
    setList(items, 2);
    drawHint("Press: choose     BACK: return");
    break;
  }
  case SCR_CLEAR: {
    drawTitle("Clear schedule?");
    char line[40];
    sprintf(line, "This deletes all %d doses.", doseCount);
    tft.setTextColor(COL_TEXT);
    tft.setTextSize(2);
    tft.setCursor(14, 70);
    tft.print(line);
    listY = 112;
    const char *items[] = {"No, keep them", "Yes, clear all"};
    setList(items, 2);
    drawHint("Press: choose     BACK: return");
    break;
  }
  default:
    break;
  }

  if (isPicker(s)) {
    centerText("Turn the knob", 62, 2, COL_HINT);
    drawHint("Press SELECT: next step     BACK: return");
  } else {
    rowsVisible = (LIST_BOTTOM - listY) / ROW_H;
    drawListAll();
  }
}

void enterSettings() {
  state = ST_SETTINGS;
  stateStartMs = millis();
  Serial.println("STATE 1: Setting schedule");
  enterScreen(SCR_MAIN);
}

void handleSelect() {
  if (sel < 0)
    return;
  switch (screen) {
  case SCR_MAIN:
    if (sel == 0) {
      if (doseCount >= MAX_DOSES) {
        showMessage("Schedule full", false);
        break;
      }
      draft = {0, 8, 0, 1, 0};
      editIndex = -1;
      enterScreen(SCR_WHEEL);
    } else if (sel == 1)
      enterScreen(SCR_VIEW);
    else if (sel == 2) {
      if (doseCount == 0)
        showMessage("Already empty", false);
      else
        enterScreen(SCR_CLEAR);
    } else if (sel == 3) {
      manualWheel = 1;
      manualQty = 1;
      enterScreen(SCR_MANUAL_WHEEL);
    } else if (sel == 4) {
      if (scheduleNotice) {
        Serial.println(
            "USER acknowledged missed-schedule alert; no replacement dose is automatic.");
        if (prefs.putBool("missed", false) == 1) {
          scheduleNotice = false;
          clockWentBackward = false;
          showMessage("Alert cleared", false);
        } else
          showMessage("Storage error", false);
      } else
        showMessage("No missed alert", false);
    } else if (sel == 5)
      enterScreen(SCR_TARE);
    else
      enterIdle();
    break;

  case SCR_WHEEL:
    draft.wheel = sel + 1;
    enterScreen(SCR_DAYS);
    break;
  case SCR_MANUAL_WHEEL:
    manualWheel = sel + 1;
    enterScreen(SCR_MANUAL_QTY);
    break;
  case SCR_MANUAL_QTY:
    manualQty = sel + 1;
    enterScreen(SCR_MANUAL_CONFIRM);
    break;
  case SCR_MANUAL_CONFIRM:
    if (sel == 0)
      startDispense(manualWheel, manualQty);
    else
      enterScreen(SCR_MAIN);
    break;
  case SCR_TARE:
    if (sel == 0)
      enterScreen(SCR_MAIN);
    else if (HW::tareEmpty())
      showMessage("Zero requested", false);
    else
      showMessage("Scale setup needed", false);
    break;
  case SCR_DAYS:
    if (sel == 0) {
      if (draft.days == 0)
        drawHintColor("Tick at least one day first!", COL_WARN);
      else
        enterScreen(SCR_HOUR);
      break;
    }
    if (sel == 1)
      draft.days = (draft.days == EVERY_DAY) ? 0 : EVERY_DAY;
    else if (sel == 2)
      draft.days = (draft.days == WEEKDAYS) ? 0 : WEEKDAYS;
    else if (sel == 3)
      draft.days = (draft.days == WEEKENDS) ? 0 : WEEKENDS;
    else
      draft.days ^= (1 << (sel - 4));
    setDayChecks();
    drawListAll();
    break;

  case SCR_HOUR:
    draft.hour = sel;
    enterScreen(SCR_MINUTE);
    break;
  case SCR_MINUTE:
    draft.minute = sel * MINUTE_STEP;
    enterScreen(SCR_QTY);
    break;
  case SCR_QTY:
    draft.qty = sel + 1;
    enterScreen(SCR_CONFIRM);
    break;

  case SCR_CONFIRM: // "Select pressed (last field) / save schedule"
    if (sel == 0) {
      if (!validDose(draft, false)) {
        drawHintColor("Assign a canister and at least one day.", COL_WARN);
        break;
      }
      if (overlapsSchedule(draft, editIndex)) {
        drawHintColor("Same canister/time exists. Change time/days.", COL_WARN);
        break;
      }
      const bool editing = editIndex >= 0;
      Dose revised[MAX_DOSES];
      memcpy(revised, doses, sizeof(doses));
      int n = doseCount;
      if (editing)
        revised[editIndex] = draft;
      else if (n < MAX_DOSES)
        revised[n++] = draft;
      else {
        showMessage("Schedule full", false);
        break;
      }
      if (!saveSchedule(revised, n)) {
        showMessage("Storage error", false);
        break;
      }
      editIndex = -1;
      printSchedule();
      showMessage(editing ? "Updated!" : "Saved!", true);
    } else {
      editIndex = -1;
      showMessage("Cancelled", true);
    }
    break;

  case SCR_VIEW:
    if (sel == 0)
      enterScreen(SCR_MAIN);
    else {
      actionIndex = sel - 1;
      enterScreen(SCR_DOSE);
    }
    break;

  case SCR_DOSE:
    if (sel == 0) {
      draft = doses[actionIndex];
      editIndex = actionIndex;
      enterScreen(SCR_WHEEL);
    } else if (sel == 1) {
      if (doseCount >= MAX_DOSES) {
        showMessage("Schedule full", false);
        break;
      }
      draft = doses[actionIndex];
      editIndex = -1;
      enterScreen(SCR_WHEEL);
    } else
      enterScreen(SCR_DELETE);
    break;

  case SCR_DELETE:
    if (sel == 1) {
      Dose revised[MAX_DOSES];
      memcpy(revised, doses, sizeof(doses));
      for (int i = actionIndex; i < doseCount - 1; i++)
        revised[i] = revised[i + 1];
      if (!saveSchedule(revised, doseCount - 1)) {
        showMessage("Storage error", false);
        break;
      }
      printSchedule();
      showMessage("Deleted", false);
    } else
      enterScreen(SCR_DOSE);
    break;

  case SCR_CLEAR:
    if (sel == 1) {
      if (saveSchedule(doses, 0)) {
        printSchedule();
        showMessage("Cleared", false);
      } else
        showMessage("Storage error", false);
    } else
      enterScreen(SCR_MAIN);
    break;

  default:
    break;
  }
}

// "Back pressed / discard edits"
void handleBack() {
  switch (screen) {
  case SCR_MAIN:
    enterIdle();
    break;
  case SCR_HOUR:
    enterScreen(SCR_DAYS);
    break;
  case SCR_MINUTE:
    enterScreen(SCR_HOUR);
    break;
  case SCR_QTY:
    enterScreen(SCR_MINUTE);
    break;
  case SCR_CONFIRM:
    enterScreen(SCR_QTY);
    break;
  case SCR_DOSE:
    enterScreen(SCR_VIEW);
    break;
  case SCR_DELETE:
    enterScreen(SCR_DOSE);
    break;
  case SCR_DAYS:
    enterScreen(SCR_WHEEL);
    break;
  case SCR_WHEEL:
    editIndex = -1;
    enterScreen(SCR_MAIN);
    break;
  case SCR_MANUAL_WHEEL:
    enterScreen(SCR_MAIN);
    break;
  case SCR_MANUAL_QTY:
    enterScreen(SCR_MANUAL_WHEEL);
    break;
  case SCR_MANUAL_CONFIRM:
    enterScreen(SCR_MANUAL_QTY);
    break;
  default:
    enterScreen(SCR_MAIN);
    break;
  }
}

void settingsLoop(BtnEvent e) {
  if (screen == SCR_MESSAGE) {
    if (int32_t(millis() - messageUntil) >= 0) {
      if (messageToIdle)
        enterIdle();
      else
        enterScreen(SCR_MAIN);
    }
    return;
  }
  if (millis() - lastKnobMs < 30 && e == BTN_NONE)
    return;
  lastKnobMs = millis();
  int n = isPicker(screen) ? pickN : listCount;
  int k = knobIndex(n, sel);
  if (k != sel) {
    if (isPicker(screen)) {
      sel = k;
      drawPickerValue();
    } else
      moveListSelection(k);
  }
  if (e == BTN_SHORT)
    handleSelect();
  else if (e == BTN_LONG)
    handleBack();
}

// DispenseCycle.ino contains these state handlers.
void dispensingLoop(BtnEvent event);
void checkingLoop(BtnEvent event);
void reviewLoop(BtnEvent event);
void waitingLoop(BtnEvent event);
void alarmLoop(BtnEvent event);

// Initialize the original HUZZAH32 using the same printed display and control pin labels.
void setup() {
  Serial.begin(115200);
  delay(300);
  pinMode(PIN_SELECT, INPUT_PULLUP);
  pinMode(PIN_BACK, INPUT_PULLUP);
  selBtn.lastRead = selBtn.stable = digitalRead(PIN_SELECT);
  selBtn.changed = millis();
  backBtn.lastRead = backBtn.stable = digitalRead(PIN_BACK);
  backBtn.changed = millis();
  storageReady = prefs.begin("pills2", false);
  if (storageReady)
    loadSchedule();
  printSchedule();
  HW::begin();
  tft.begin();
  tft.setRotation(1);
  tft.setTextWrap(false);
  openCalibration();
  Serial.println("HUZZAH32 calibration ready. Schedules paused. Send HELP.");
}

// INPUT ACQUISITION + EVENT CHECKERS; SWITCH DISPATCHES SEVEN REAL STATES.
void loop() {
  HW::poll();
  BtnEvent e = updateButton(selBtn);
  if (updateButton(backBtn, true) == BTN_LONG)
    e = BTN_LONG;
  if (inCalibration && !calibrationDose) {
    calibrationLoop(e);
    delay(1);
    return;
  }
  if (calibrationDose && state == ST_IDLE) {
    // The serial reader only queues DISPENSE. Poll Back before the first motor request.
    if (e == BTN_LONG || digitalRead(PIN_BACK) == LOW) {
      calibrationDose = false;
      benchStop("Dispense cancelled before motion");
    } else {
      startDispense(1, 1);
    }
    delay(1);
    return;
  }
  const State before = state;
  if (!inCalibration)
    checkSchedule();
  if (state != before)
    e = BTN_NONE; // A pre-start key event never acknowledges a new alarm/job.
  switch (state) {
  case ST_IDLE:
    idleLoop(e);
    break;
  case ST_SETTINGS:
    settingsLoop(e);
    break;
  case ST_DISPENSING:
    dispensingLoop(e);
    break;
  case ST_REVIEW:
    reviewLoop(e);
    break;
  case ST_CHECKING:
    checkingLoop(e);
    break;
  case ST_WAITING:
    waitingLoop(e);
    break;
  case ST_ALARM:
    alarmLoop(e);
    break;
  }
  delay(1);
}
