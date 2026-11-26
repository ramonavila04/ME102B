#pragma once
#include <stdint.h>
#include "Transport.h"

// MICRO-USB HUZZAH32 (screen board). Edit these values, then upload this sketch.
// To change a saved dispensing time, use the knob: View schedule > select entry >
// Edit. Add a dose sets the canister, days, hour, minute and quantity on screen.
// Each scheduled time uses local wall time from the DS3231. No upload is needed.
namespace DisplaySettings {
constexpr unsigned MINUTE_STEP = 1;           // 1 = any minute; 5 or 15 = coarser picker
// NUDGE_DEGREES, MAX_NUDGES and NUDGE_WAIT_MS are shared with the motor in Transport.h.
constexpr uint32_t WEIGHT_TIMEOUT_MS = 5000;  // maximum wait from stopped wheel for stable, conclusive data
constexpr uint32_t REMINDER_MS = 5 * 60000UL; // repeat the on-screen check/pickup reminder
constexpr uint32_t BATCH_START_WINDOW_MS = 2 * 60000UL; // latest next start in a same-minute group
constexpr uint32_t BUTTON_DEBOUNCE_MS = 30;
constexpr uint32_t SELECT_HOLD_MS = 1000;     // long Select acts as Back
constexpr uint32_t ACK_TIMEOUT_MS = 500;      // allow peer to acknowledge a new job
constexpr uint32_t NEXT_IDLE_TIMEOUT_MS = 5000; // allow peer to acknowledge a stop
constexpr uint32_t BENCH_POCKET_TIMEOUT_MS = 12000; // allows a slow 60-degree STEP plus settling
constexpr uint32_t BENCH_JOG_TIMEOUT_MS = 5000;     // one empty-wheel JOG15
constexpr uint32_t BENCH_EDGE_TIMEOUT_MS = 25000;   // 60-degree creep plus back-off and settling
constexpr uint32_t BENCH_ROCK_TIMEOUT_MS = 15000;   // the whole multi-stroke empty-wheel rock

struct PieceMass {
    float grams;          // measured mean for ONE item from this canister
    float variationGrams; // allowed deviation per item, based on samples
};
// Profiles check each weight increase and the cumulative batch. With {0,0},
// confirm each new count visually before releasing the next piece. With a measured
// profile, confirm the final count. Both values are in grams.
constexpr PieceMass EXPECTED_PIECE[6] = {
    {0, 0},  // canister 1
    {0, 0},  // canister 2
    {0, 0},  // canister 3
    {0, 0},  // canister 4
    {0, 0},  // canister 5
    {0, 0},  // canister 6
};

static_assert(MINUTE_STEP > 0 && MINUTE_STEP <= 60 && 60 % MINUTE_STEP == 0,
              "MINUTE_STEP must divide 60 evenly.");
static_assert(WEIGHT_TIMEOUT_MS > Link::NUDGE_WAIT_MS + 1000,
              "Allow extra time for a moving bowl to settle.");
static_assert(REMINDER_MS > 0 && REMINDER_MS <= 0x7fffffffUL, "Invalid reminder interval.");
}
