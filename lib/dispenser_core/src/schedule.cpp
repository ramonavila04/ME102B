#include "schedule.h"

#include <stdio.h>

namespace dc {

int Schedule::enabledCount() const {
  int n = 0;
  for (int i = 0; i < kMaxDoses; ++i) n += enabled(i) ? 1 : 0;
  return n;
}

bool Schedule::nextAfter(uint32_t t, uint32_t& when, int& slot) const {
  const uint32_t day = t / 86400UL;
  bool found = false;
  for (uint32_t d = 0; d < 2; ++d) {  // today, then tomorrow (rollover past midnight)
    for (int i = 0; i < kMaxDoses; ++i) {
      if (!enabled(i)) continue;
      const uint32_t cand = (day + d) * 86400UL + static_cast<uint32_t>(minuteOfDay[i]) * 60UL;
      if (cand > t && (!found || cand < when)) {
        when = cand;
        slot = i;
        found = true;
      }
    }
  }
  return found;
}

bool Schedule::dueBetween(uint32_t prev, uint32_t now, uint32_t& when, int& slot) const {
  if (now <= prev) return false;
  uint32_t t = prev, w = 0;
  int s = -1;
  bool any = false;
  // Walk forward; bounded because there are at most 3 doses per day.
  for (int guard = 0; guard < 3 * kMaxDoses + 3; ++guard) {
    if (!nextAfter(t, w, s) || w > now) break;
    when = w;
    slot = s;
    any = true;
    t = w;
  }
  return any;
}

void Schedule::sanitize() {
  for (int i = 0; i < kMaxDoses; ++i)
    if (!enabled(i)) minuteOfDay[i] = kDoseOff;
}

void formatMinuteOfDay(int16_t m, char* buf, unsigned len) {
  if (m < 0 || m >= 1440) {
    snprintf(buf, len, "OFF");
  } else {
    snprintf(buf, len, "%02d:%02d", m / 60, m % 60);
  }
}

void formatClock(uint32_t t, char* buf, unsigned len) {
  const uint32_t s = t % 86400UL;
  snprintf(buf, len, "%02u:%02u:%02u", static_cast<unsigned>(s / 3600),
           static_cast<unsigned>((s / 60) % 60), static_cast<unsigned>(s % 60));
}

void formatDuration(uint32_t sec, char* buf, unsigned len) {
  if (sec >= 3600) {
    snprintf(buf, len, "%uh%02um", static_cast<unsigned>(sec / 3600),
             static_cast<unsigned>((sec / 60) % 60));
  } else if (sec >= 60) {
    snprintf(buf, len, "%um", static_cast<unsigned>((sec + 59) / 60));
  } else {
    snprintf(buf, len, "%us", static_cast<unsigned>(sec));
  }
}

}  // namespace dc
