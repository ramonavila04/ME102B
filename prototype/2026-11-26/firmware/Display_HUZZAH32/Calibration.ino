// Commissioning panel. The cover-edge tests use one inert dummy. Only MENU resumes schedules.
enum BenchAction {
  BENCH_IDLE, BENCH_STEP, BENCH_SPIN, BENCH_JOG, BENCH_ROCK, BENCH_ROCK2,
  BENCH_FIRST_ROCK, BENCH_WAIT_FOR_STEP, BENCH_SEQUENCE_STEP,
  BENCH_STEPROCK_HOLD, BENCH_WAIT_FOR_FINAL_ROCK, BENCH_FINAL_ROCK,
  BENCH_EDGE, BENCH_EDGE_RETRY, BENCH_WEIGH_BACKOFF, BENCH_WEIGH_FINISH,
  BENCH_EDGE_DRY, BENCH_EDGE_DRY_HOLD, BENCH_EDGE_DRY_RETRY
};
void benchStart(BenchAction action);
bool isRockAction(BenchAction action);
static BenchAction benchAction = BENCH_IDLE;
static bool benchAck = false;
static uint32_t benchStartedAt, benchLastAck, panelLastDraw;
static int benchChoice = -1;
static int32_t benchEncoder;
static float edgeBaseline, edgeMargin;
static bool edgeSawGain;
static char benchNote[48];
static char panelCache[7][52];

void setupNote(const char *text) {
  snprintf(benchNote, sizeof(benchNote), "%s", text);
  Serial.println(text);
}

void openCalibration() {
  HW::stop();
  inCalibration = true;
  calibrationDose = false;
  activeJob = false;
  state = ST_IDLE;
  benchAction = BENCH_IDLE;
  benchChoice = -1;
  benchEncoder = 0;
  panelLastDraw = millis() - 500;
  memset(panelCache, 0, sizeof(panelCache));
  snprintf(benchNote, sizeof(benchNote), "%s",
           pendingInspection ? "Inspect interrupted dose; USB DISPENSE" : "USB DISPENSE tests one C1 item");
  tft.fillScreen(COL_BG);
  drawTitle("Calibration");
  drawHint("Knob: choose   SELECT: run   BACK: stop   USB: HELP");
}

void benchStop(const char *message) {
  HW::stop();
  benchAction = BENCH_IDLE;
  setupNote(message);
}

bool isRockAction(BenchAction action) {
  return action == BENCH_ROCK || action == BENCH_ROCK2 || action == BENCH_FIRST_ROCK || action == BENCH_FINAL_ROCK;
}

bool isDryEdgeAction() {
  return benchAction == BENCH_EDGE_DRY || benchAction == BENCH_EDGE_DRY_HOLD ||
         benchAction == BENCH_EDGE_DRY_RETRY;
}

void benchStart(BenchAction action) {
  if (pendingInspection || !storageReady) {
    setupNote("Inspect pending job/storage via MENU");
    return;
  }
  if (benchAction != BENCH_IDLE) {
    setupNote("Motor busy; use STOP to cancel");
    return;
  }
  if (digitalRead(PIN_BACK) == LOW) {
    setupNote("Release BACK before a motor test");
    return;
  }
  bool started;
  if (action == BENCH_EDGE) {
    started = HW::startEdgeTest(edgeBaseline, edgeMargin);
    edgeSawGain = false;
    if (!started) {
      setupNote("Need idle C1 + stable tared empty bowl");
      return;
    }
  } else if (action == BENCH_EDGE_DRY)
    started = HW::startEdgeDry();
  else if (isRockAction(action))
    started = action == BENCH_ROCK2 ? HW::startBenchRock2() : HW::startBenchRock();
  else if (action == BENCH_JOG)
    started = HW::startBenchJog();
  else
    started = HW::startBench(action == BENCH_SPIN);
  if (!started) {
    setupNote("Busy or C1 unavailable; send STATUS");
    return;
  }
  benchAction = action;
  benchAck = false;
  benchStartedAt = millis();
  benchLastAck = benchStartedAt;
  if (action == BENCH_EDGE_DRY)
    setupNote("EDGEDRY: watch C1 at the cover edge");
  else if (action == BENCH_EDGE)
    setupNote("EDGETEST: creeping toward the cover");
  else if (action == BENCH_FIRST_ROCK)
    setupNote("STEPROCK: starting first rock");
  else if (action == BENCH_SEQUENCE_STEP)
    setupNote("STEPROCK: starting forward step");
  else if (action == BENCH_FINAL_ROCK)
    setupNote("STEPROCK: starting final rock");
  else if (action == BENCH_ROCK)
    setupNote("C1 jitter pattern requested");
  else if (action == BENCH_ROCK2)
    setupNote("ROCK2: 90 degrees back and return");
  else if (action == BENCH_JOG)
    setupNote("C1 one 15-degree jog requested");
  else
    setupNote(action == BENCH_SPIN ? "C1 spinning; BACK or STOP ends run" : "C1 forward step requested");
}

// Called by the serial service after normalization. Scale and clock commands stay in Hardware.cpp.
bool handleSetupCommand(const char *line) {
  if (!strcmp(line, "HELP")) {
    Serial.println("SETUP opens calibration from idle. MENU resumes normal schedules.");
    Serial.println("In calibration, DISPENSE tests one C1 item with the scale. Select confirms its count.");
    Serial.printf("EDGEDRY: supervised motor/encoder test only. With drive off, position one inert dummy about "
                  "10 degrees before the cover edge. Watch C1 creep at %u deg/s toward +%u degrees. "
                  "On a slowdown it backs off %u degrees, settles for %u ms, waits %lu ms and tries once more. "
                  "Inspect the pocket and outlet yourself. STOP or BACK cancels.\n",
                  unsigned(Link::EDGE_CREEP_DEG_PER_SEC), unsigned(Link::EDGE_FORWARD_DEGREES),
                  unsigned(Link::EDGE_BACKOFF_DEGREES), unsigned(Link::EDGE_QUIET_MS), (unsigned long)Link::NUDGE_WAIT_MS);
    Serial.printf("EDGETEST: tare the empty fixed bowl. With drive off, set one inert dummy in a pocket "
                  "about 10 degrees before the cover edge. C1 creeps at %u deg/s to +%u degrees from that mark. "
                  "On a slowdown it backs off %u degrees, settles for %u ms, then checks the scale for at least %lu ms. "
                  "One retry only after a stable empty bowl; STOP cancels.\n",
                  unsigned(Link::EDGE_CREEP_DEG_PER_SEC), unsigned(Link::EDGE_FORWARD_DEGREES),
                  unsigned(Link::EDGE_BACKOFF_DEGREES), unsigned(Link::EDGE_QUIET_MS), (unsigned long)Link::NUDGE_WAIT_MS);
    Serial.printf("STEPROCK: empty wheel C1, ROCK once, step forward %u degrees, wait %lu ms after the step settles, then ROCK once. No scale needed.\n",
                  unsigned(Link::STEP_DEGREES), (unsigned long)Link::NUDGE_WAIT_MS);
    Serial.printf("Empty wheel C1: ROCK sweeps back 180 degrees and returns with short reversals (%u degrees total). Targets from the start (degrees):",
                  Link::benchRockTravelDegrees());
    for (int target : Link::BENCH_ROCK_TARGETS) Serial.printf(" %d", target);
    Serial.printf(".\nJOG15 (forward 15 degrees), STEP (forward %u degrees), SPIN (continuous), STOP.\n",
                  unsigned(Link::STEP_DEGREES));
    Serial.printf("ROCK2: empty wheel C1. Sweep back 90 degrees and return with short reversals (%u degrees total). "
                  "Full drive in cruise, slowing at each endpoint. STOP cancels.\n",
                  Link::benchRockTravelDegrees(Link::ROCK2));
    return false;
  }
  if (!strcmp(line, "SETUP")) {
    if (!inCalibration && state == ST_IDLE && !batchCount && !activeJob)
      openCalibration();
    Serial.println(inCalibration ? "Calibration: schedules paused." : "Finish the current operation first.");
    return true;
  }
  if (!strcmp(line, "STOP")) {
    if (inCalibration && (!calibrationDose || state == ST_IDLE)) {
      calibrationDose = false;
      benchStop("STOP requested. Check C1 idle.");
    } else if (activeJob || batchCount)
      enterAlarm("STOPPED / INSPECT");
    else
      HW::stop();
    return true;
  }
  if (!strcmp(line, "DISPENSE")) {
    if (!inCalibration) {
      Serial.println("Enter SETUP from idle for a one-item C1 scale test.");
    } else if (calibrationDose || state != ST_IDLE || activeJob || batchCount ||
               benchAction != BENCH_IDLE || HW::scaleSampling()) {
      Serial.println("Busy. Finish the current test, pickup, or inspection.");
    } else {
      calibrationDose = true;
      Serial.println(pendingInspection ? "Inspection required before another dose." :
                                         "One C1 item requested. Schedules remain paused.");
    }
    return true;
  }
  if (calibrationDose && state != ST_ALARM &&
      (!strcmp(line, "TARE") || !strncmp(line, "CAL ", 4) || !strcmp(line, "VERIFY"))) {
    Serial.println("Finish or stop the dispense test before changing the scale.");
    return true;
  }
  BenchAction action = BENCH_IDLE;
  if (!strcmp(line, "STEP")) action = BENCH_STEP;
  else if (!strcmp(line, "STEPROCK")) action = BENCH_FIRST_ROCK;
  else if (!strcmp(line, "SPIN")) action = BENCH_SPIN;
  else if (!strcmp(line, "JOG15")) action = BENCH_JOG;
  else if (!strcmp(line, "ROCK")) action = BENCH_ROCK;
  else if (!strcmp(line, "ROCK2")) action = BENCH_ROCK2;
  else if (!strcmp(line, "EDGETEST")) action = BENCH_EDGE;
  else if (!strcmp(line, "EDGEDRY")) action = BENCH_EDGE_DRY;
  if (action != BENCH_IDLE) {
    if (calibrationDose)
      Serial.println("Finish the current dispense test or inspection first.");
    else if (inCalibration)
      benchStart(action);
    else
      Serial.println("Enter SETUP from idle for a bench test.");
    return true;
  }
  if (strcmp(line, "MENU"))
    return false;
  if (!inCalibration) {
    Serial.println("Already in normal operation.");
    return true;
  }
  if (calibrationDose) {
    Serial.println("Finish the current dispense test or inspection before MENU.");
    return true;
  }
  if (benchAction != BENCH_IDLE || HW::scaleSampling() || !HW::linkReady()) {
    setupNote("MENU waits for idle motor and scale");
    return true;
  }
  // The current minute belongs to commissioning, even when it has a saved schedule.
  struct tm t {};
  if (HW::clockNow(t))
    lastObservedMinute = minuteKey(t);
  inCalibration = false;
  Serial.println("Calibration closed. Normal schedules resume.");
  if (!storageReady)
    enterAlarm("STORAGE ERROR");
  else if (pendingInspection)
    enterAlarm("RESTART / INSPECT");
  else
    enterSettings();
  return true;
}

// A stopped EDGE pass retains its job during the post-backoff hold.
void checkEdgeFeedback(uint32_t now) {
  const bool dry = isDryEdgeAction();
  const bool weighing = benchAction == BENCH_WEIGH_BACKOFF || benchAction == BENCH_WEIGH_FINISH;
  if (digitalRead(PIN_BACK) == LOW) {
    benchStop("Edge test stopped; inspect wheel and outlet");
    return;
  }
  if (HW::jobFresh() && (HW::status.fault || HW::status.phase == 4)) {
    char text[48];
    snprintf(text, sizeof(text), "%s: %s; inspect C1", dry ? "EDGEDRY" : "EDGETEST", motionFaultName(HW::status.fault));
    benchStop(text);
    return;
  }
  if (!HW::wheelConfigured(1) || (!dry && !HW::scaleReady())) {
    benchStop(dry ? "EDGEDRY: check C1 and link" : "EDGETEST: check scale/wheel; inspect");
    return;
  }
  const uint32_t elapsed = now - benchStartedAt;
  if (benchAction == BENCH_EDGE_DRY_HOLD) {
    if (!HW::jobFresh() || HW::status.phase != 3 || HW::status.indexed != Link::EDGE_BACKED_OFF ||
        elapsed >= Link::NUDGE_WAIT_MS + ACK_TIMEOUT_MS) {
      benchStop("EDGEDRY: interrupted during pause; inspect");
    } else if (elapsed >= Link::NUDGE_WAIT_MS) {
      if (!HW::retryEdgeDry(benchStartedAt)) {
        benchStop("EDGEDRY: retry cancelled; inspect C1");
        return;
      }
      benchAction = BENCH_EDGE_DRY_RETRY;
      benchStartedAt = benchLastAck = now;
      benchAck = false;
      setupNote("EDGEDRY: one slow retry");
    }
    return;
  }
  float grams;
  if (!weighing) {
    // Remember a possible drop even if its weight subsequently disappears.
    if (!dry && HW::stableWeightSince(benchStartedAt, grams) && grams - edgeBaseline > edgeMargin)
      edgeSawGain = true;
    if (HW::jobFresh()) {
      const auto &s = HW::status;
      benchEncoder = s.encoder;
      if (s.phase == 3) {
        const bool firstPass = benchAction == BENCH_EDGE || benchAction == BENCH_EDGE_DRY;
        const bool backedOff = firstPass && s.indexed == Link::EDGE_BACKED_OFF;
        if (!backedOff && s.indexed != Link::EDGE_FINISHED) {
          benchStop("Unexpected edge stop; inspect C1");
          return;
        }
        benchStartedAt = now;
        if (dry) {
          if (backedOff) {
            benchAction = BENCH_EDGE_DRY_HOLD;
            setupNote("EDGEDRY: backed off; holding for retry");
          } else {
            benchStop("EDGEDRY complete; inspect pocket and outlet");
          }
        } else {
          benchAction = backedOff ? BENCH_WEIGH_BACKOFF : BENCH_WEIGH_FINISH;
          setupNote(backedOff ? "Backed off; checking bowl before retry" : "Travel complete; checking bowl");
        }
        return;
      }
      if (s.phase == 1) {
        benchAck = true;
        benchLastAck = now;
      } else if (benchAck || s.phase != 0) {
        benchStop("Unexpected motor state; inspect C1");
        return;
      }
    }
    if ((!benchAck && elapsed >= ACK_TIMEOUT_MS) || (benchAck && now - benchLastAck >= 300) ||
        elapsed >= BENCH_EDGE_TIMEOUT_MS)
      benchStop("Edge test timeout; inspect C1");
    return;
  }
  const uint8_t expected = benchAction == BENCH_WEIGH_BACKOFF ? Link::EDGE_BACKED_OFF : Link::EDGE_FINISHED;
  if (!HW::jobFresh() || HW::status.phase != 3 || HW::status.indexed != expected ||
      elapsed >= WEIGHT_TIMEOUT_MS) {
    benchStop("EDGETEST: no reliable drop check; inspect");
    return;
  }
  if (!HW::stableWeightSince(benchStartedAt, grams) || !isfinite(grams))
    return;
  const float gain = grams - edgeBaseline;
  if (gain < -edgeMargin) {
    benchStop("EDGETEST: bowl moved; inspect");
    return;
  }
  if (gain > edgeMargin)
    edgeSawGain = true;
  if (elapsed < Link::NUDGE_WAIT_MS || !HW::sampleSince(benchStartedAt + Link::NUDGE_WAIT_MS))
    return;
  if (gain > 3 * edgeMargin) {
    Serial.printf("EDGETEST stable gain %.3f g; visually confirm the dummy.\n", gain);
    benchStop("EDGETEST: DROP detected; check bowl");
  } else if (edgeSawGain || fabsf(grams) > edgeMargin) {
    benchStop("EDGETEST: uncertain weight; inspect");
  } else if (benchAction == BENCH_WEIGH_FINISH) {
    benchStop("EDGETEST: NO DROP; inspect pocket/outlet");
  } else if (HW::retryEdgeTest(edgeBaseline, benchStartedAt)) {
    benchAction = BENCH_EDGE_RETRY;
    benchStartedAt = benchLastAck = now;
    benchAck = false;
    setupNote("EDGETEST: bowl empty; one slow retry");
  } else {
    benchStop("EDGETEST: retry check failed; inspect");
  }
}

void checkBenchFeedback() {
  if (benchAction == BENCH_IDLE)
    return;
  const uint32_t now = millis();
  if (!HW::linkAlive()) {
    benchStop("C1 link lost; inspect wheel");
    return;
  }
  if (benchAction == BENCH_EDGE || benchAction == BENCH_EDGE_RETRY ||
      benchAction == BENCH_WEIGH_BACKOFF || benchAction == BENCH_WEIGH_FINISH || isDryEdgeAction()) {
    checkEdgeFeedback(now);
    return;
  }
  if (benchAction == BENCH_WAIT_FOR_STEP || benchAction == BENCH_STEPROCK_HOLD ||
      benchAction == BENCH_WAIT_FOR_FINAL_ROCK) {
    if (digitalRead(PIN_BACK) == LOW || !HW::jobFresh() || HW::status.fault || !HW::wheelConfigured(1)) {
      benchStop("STEPROCK cancelled; check C1");
      return;
    }
    const uint32_t elapsed = now - benchStartedAt;
    const bool motionDone = HW::status.phase == 3 && HW::status.indexed == 1;
    if (benchAction == BENCH_STEPROCK_HOLD) {
      // Keep the stopped step under its existing command watchdog throughout the dwell.
      if (!motionDone || elapsed > Link::NUDGE_WAIT_MS + ACK_TIMEOUT_MS) {
        benchStop("STEPROCK interrupted during pause");
      } else if (elapsed >= Link::NUDGE_WAIT_MS) {
        HW::stop();
        benchStartedAt = now;
        benchAction = BENCH_WAIT_FOR_FINAL_ROCK;
      }
    } else if (elapsed >= ACK_TIMEOUT_MS) {
      benchStop("STEPROCK cancelled; C1 idle timed out");
    } else if (HW::linkReady()) {
      const BenchAction next = benchAction == BENCH_WAIT_FOR_STEP ? BENCH_SEQUENCE_STEP : BENCH_FINAL_ROCK;
      benchAction = BENCH_IDLE;
      benchStart(next);
    } else if (!motionDone) {
      benchStop("STEPROCK cancelled; unexpected motor state");
    }
    return;
  }
  if (HW::jobFresh()) {
    const Link::Status &s = HW::status;
    if (s.fault || s.phase == 4) {
      char fault[46];
      snprintf(fault, sizeof(fault), "C1 fault %u: %s", s.fault, motionFaultName(s.fault));
      benchEncoder = s.encoder;
      benchStop(fault);
      return;
    }
    if (benchAction != BENCH_SPIN && s.phase == 3 && s.indexed == 1) {
      benchEncoder = s.encoder;
      if (benchAction == BENCH_FIRST_ROCK) {
        Serial.printf("STEPROCK: first rock settled at encoder %ld.\n", (long)benchEncoder);
        HW::stop();
        benchStartedAt = now;
        benchAction = BENCH_WAIT_FOR_STEP;
      } else if (benchAction == BENCH_SEQUENCE_STEP) {
        benchAction = BENCH_STEPROCK_HOLD;
        benchStartedAt = now;
        Serial.printf("STEPROCK: step settled at encoder %ld.\n", (long)benchEncoder);
        setupNote("STEPROCK: step done, waiting for rock");
      } else if (benchAction == BENCH_FINAL_ROCK) {
        Serial.printf("STEPROCK: final rock settled at encoder %ld.\n", (long)benchEncoder);
        benchStop("STEPROCK complete");
      } else if (benchAction == BENCH_ROCK || benchAction == BENCH_ROCK2) {
        const bool rock2 = benchAction == BENCH_ROCK2;
        Serial.printf("C1 %s done. Settled encoder %ld. Check that the wheel mark returned to its start.\n",
                      rock2 ? "ROCK2" : "ROCK", (long)benchEncoder);
        benchStop(rock2 ? "ROCK2 complete; check starting mark" : "Rock done; check starting mark");
      } else if (benchAction == BENCH_JOG) {
        Serial.printf("C1 JOG15 done (target 15 degrees), settled encoder %ld. Check the wheel mark.\n",
                      (long)benchEncoder);
        benchStop("Jog done; check mark at 15 degrees");
      } else {
        Serial.printf("C1 STEP complete, settled encoder %ld. Check for %u degrees forward.\n",
                      (long)benchEncoder, unsigned(Link::STEP_DEGREES));
        benchStop("Step complete; check wheel mark");
      }
      return;
    }
    if (s.phase == (benchAction == BENCH_SPIN ? 2 : 1)) {
      benchAck = true;
      benchLastAck = now;
      benchEncoder = s.encoder;
    } else if (benchAck || s.phase != 0) {
      benchStop("Unexpected motor state; inspect C1");
      return;
    }
  }
  if ((!benchAck && now - benchStartedAt >= ACK_TIMEOUT_MS) ||
      (benchAck && now - benchLastAck >= 300) ||
      ((benchAction == BENCH_STEP || benchAction == BENCH_SEQUENCE_STEP) && now - benchStartedAt >= BENCH_POCKET_TIMEOUT_MS) ||
      (benchAction == BENCH_JOG && now - benchStartedAt >= BENCH_JOG_TIMEOUT_MS) ||
      (isRockAction(benchAction) && now - benchStartedAt >= BENCH_ROCK_TIMEOUT_MS))
    benchStop("C1 timeout; inspect wheel and link");
}

void drawCalibrationLine(int row, const char *text, int size, uint16_t color) {
  if (!strcmp(text, panelCache[row]))
    return;
  snprintf(panelCache[row], sizeof(panelCache[row]), "%s", text);
  const int y = 45 + row * 25;
  tft.fillRect(8, y, 306, 18, COL_BG);
  tft.setCursor(10, y);
  tft.setTextSize(size);
  tft.setTextColor(color);
  tft.print(text);
}

void calibrationLoop(BtnEvent e) {
  if (e == BTN_LONG)
    benchStop("STOP requested. Check C1 idle.");
  checkBenchFeedback();
  const uint32_t now = millis();
  if (e == BTN_NONE && now - panelLastDraw < 400)
    return;
  panelLastDraw = now;
  benchChoice = knobIndex(3, benchChoice);
  if (e == BTN_SHORT) {
    if (benchChoice == 0)
      benchStop("STOP requested. Check C1 idle.");
    else if (benchChoice == 1)
      benchStart(BENCH_STEP);
    else if (benchAction == BENCH_IDLE && HW::tareEmpty())
      setupNote("Taring empty tray; keep it still");
    else
      setupNote("Tare busy; wait and retry");
  }
  char line[52];
  drawCalibrationLine(0, "Schedules paused", 2, COL_HINT);
  struct tm t {};
  if (HW::clockNow(t))
    snprintf(line, sizeof(line), "RTC %02d:%02d:%02d", t.tm_hour, t.tm_min, t.tm_sec);
  else
    snprintf(line, sizeof(line), "RTC unset / USB TIME");
  drawCalibrationLine(1, line, 2, COL_TEXT);
  float grams;
  if (isDryEdgeAction())
    snprintf(line, sizeof(line), "Watch C1 pocket and outlet");
  else if (HW::stableWeight(grams))
    snprintf(line, sizeof(line), "Tray %.3f g", grams);
  else
    snprintf(line, sizeof(line), "Tray %s", HW::scaleSampling() ? "sampling..." : "awaiting stable/cal");
  drawCalibrationLine(2, line, 2, COL_TEXT);
  const char *motor = "offline";
  if (HW::linkAlive()) {
    switch (HW::status.phase) {
      case 0: motor = "idle"; break;
      case 1: motor = isRockAction(benchAction) ? "rocking" : "indexing"; break;
      case 2: motor = "spinning"; break;
      case 3: motor = "done"; break;
      default: motor = "fault"; break;
    }
  }
  snprintf(line, sizeof(line), "C1 %s   Enc %ld", motor, (long)benchEncoder);
  drawCalibrationLine(3, line, strlen(line) > 24 ? 1 : 2, COL_TEXT);
  drawCalibrationLine(4, benchNote, 1, COL_HINT);
  const char *choices[] = {"STOP motor", "STEP 60 degrees", "TARE empty tray"};
  drawCalibrationLine(5, choices[benchChoice], 2, COL_TITLE);
  drawCalibrationLine(6, "USB: EDGEDRY  EDGETEST  HELP  MENU", 1, COL_TEXT);
}
