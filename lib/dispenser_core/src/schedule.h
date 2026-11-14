// Up to three daily dose times. Times are local wall-clock seconds
// ("unix-style" seconds since 2000/1970 read from the DS3231, which is set to
// local time; no time zone or DST handling).
#pragma once
#include <stdint.h>

namespace dc {

constexpr int kMaxDoses = 3;
constexpr int16_t kDoseOff = -1;

struct Schedule {
  int16_t minuteOfDay[kMaxDoses] = {kDoseOff, kDoseOff, kDoseOff};  // 0..1439 or kDoseOff

  bool enabled(int i) const { return minuteOfDay[i] >= 0 && minuteOfDay[i] < 1440; }
  int enabledCount() const;
  // First dose time strictly after `t`. False when no dose is enabled.
  bool nextAfter(uint32_t t, uint32_t& when, int& slot) const;
  // Dose time in (prevExclusive, nowInclusive]; reports the LATEST one if several.
  bool dueBetween(uint32_t prevExclusive, uint32_t nowInclusive, uint32_t& when, int& slot) const;
  // Clamp corrupted values (e.g. from NVS) to kDoseOff.
  void sanitize();
};

// "HH:MM" for a minute-of-day, "OFF" for kDoseOff. buf >= 6 chars.
void formatMinuteOfDay(int16_t minuteOfDay, char* buf, unsigned len);
// "HH:MM:SS" for a wall-clock time. buf >= 9 chars.
void formatClock(uint32_t t, char* buf, unsigned len);
// "3h05m" / "12m" / "45s". buf >= 8 chars.
void formatDuration(uint32_t seconds, char* buf, unsigned len);

}  // namespace dc
