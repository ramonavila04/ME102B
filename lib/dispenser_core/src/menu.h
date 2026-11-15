// Input conditioning: switch debouncing and pot -> list index with hysteresis.
#pragma once
#include <stdint.h>

namespace dc {

// Time-based debouncer. The stable state changes only after the raw input has
// held a new value for `debounceMs`.
class Debouncer {
 public:
  explicit Debouncer(uint32_t debounceMs = 30) : ms_(debounceMs) {}
  void reset(bool level, uint32_t nowMs) {
    raw_ = stable_ = level;
    changedAt_ = nowMs;
  }
  // Returns true exactly once per stable false->true transition (a "press").
  bool update(uint32_t nowMs, bool raw) {
    if (raw != raw_) {
      raw_ = raw;
      changedAt_ = nowMs;
    }
    if (raw_ != stable_ && nowMs - changedAt_ >= ms_) {
      stable_ = raw_;
      return stable_;
    }
    return false;
  }
  bool stable() const { return stable_; }

 private:
  uint32_t ms_;
  bool raw_ = false, stable_ = false;
  uint32_t changedAt_ = 0;
};

// Maps a 0..adcMax reading onto `count` equal bins. The selection only moves
// to a neighbouring bin once the reading is `hysteresis` counts past the bin
// edge, so ADC noise at an edge cannot make the selection flicker.
class PotSelector {
 public:
  void reset(int count, int raw, int adcMax = 4095, int hysteresis = -1) {
    count_ = count < 1 ? 1 : count;
    adcMax_ = adcMax;
    const int width = (adcMax_ + 1) / count_;
    hyst_ = hysteresis >= 0 ? hysteresis : width / 4;
    if (hyst_ > width / 2) hyst_ = width / 2;
    index_ = rawBin(raw);
  }
  int update(int raw) {
    const int bin = rawBin(raw);
    if (bin == index_) return index_;
    const long lo = edge(index_) - hyst_;      // must go this far below the current bin
    const long hi = edge(index_ + 1) + hyst_;  // or this far above it
    if (raw < lo || raw >= hi) index_ = bin;
    return index_;
  }
  int index() const { return index_; }
  int count() const { return count_; }

 private:
  int rawBin(int raw) const {
    if (raw < 0) raw = 0;
    if (raw > adcMax_) raw = adcMax_;
    int b = static_cast<int>(static_cast<long>(raw) * count_ / (adcMax_ + 1));
    return b >= count_ ? count_ - 1 : b;
  }
  long edge(int i) const { return static_cast<long>(i) * (adcMax_ + 1) / count_; }
  int count_ = 1, adcMax_ = 4095, hyst_ = 0, index_ = 0;
};

}  // namespace dc
