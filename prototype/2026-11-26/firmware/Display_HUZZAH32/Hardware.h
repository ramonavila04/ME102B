#pragma once
#include <Arduino.h>
#include <time.h>
#include "Transport.h"

namespace HW {
void begin();
void poll();
bool linkAlive();
bool linkReady();
bool jobFresh();
bool wheelConfigured(uint8_t wheel);
bool scaleReady();
bool scaleSampling();
bool tareEmpty();
bool stableWeight(float &grams);
bool stableWeightSince(uint32_t since, float &grams);
bool sampleSince(uint32_t since);
bool weightMargin(float &grams);
bool clockNow(struct tm &local);
bool nudge(uint8_t wheel, uint8_t piece, uint8_t attempt, float expectedBowlGrams);
bool startBench(bool spin);
bool startBenchJog();
bool startBenchRock();
bool startBenchRock2();
bool startEdgeTest(float &emptyGrams, float &margin);
bool retryEdgeTest(float emptyGrams, uint32_t settledAt);
bool startEdgeDry();
bool retryEdgeDry(uint32_t stoppedAt);
void stop();
extern Link::Status status;
} // namespace HW
