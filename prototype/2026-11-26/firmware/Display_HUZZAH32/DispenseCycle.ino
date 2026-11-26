// ======================================================================
// DISPENSE, WEIGH, REVIEW, PICK UP
// ======================================================================
void drawNudgePanel() {
  tft.fillScreen(COL_BG);
  drawTitle("Dispensing");
  centerText("Keep bowl in place", 191, 1, COL_HINT);
  drawHint("BACK: stop and inspect");
}

// SERVICE S02: request one attempt. The motor reports DONE after the entire
// move settles, including both legs of a rock. Then this board checks the bowl.
void beginNudge(uint8_t attempt) {
  const uint8_t piece = detectedDrops + 1;
  if (!activeJob || state == ST_REVIEW)
    drawNudgePanel();
  jobStartedMs = millis();
  if (!HW::nudge(activeWheel, piece, attempt, pieceBaseline)) {
    enterAlarm("NUDGE REJECTED");
    return;
  }
  state = ST_DISPENSING;
  activeJob = true;
  nudgeAttempt = attempt;
  char line[36];
  tft.fillRect(0, 57, 320, 90, COL_BG);
  snprintf(line, sizeof(line), "C%u   Item %u of %u", activeWheel, piece, requestedQty);
  centerText(line, 61, 2, COL_TEXT);
  const bool rock = activeWheel == 1 && attempt == Link::ROCK_NUDGE_ORDINAL;
  const unsigned limit = Link::maxAttempts(activeWheel);
  snprintf(line, sizeof(line), "%s %u of %u", rock ? "Rock" : "Move", attempt, limit);
  centerText(line, 104, 3, COL_TITLE);
  if (rock) {
    Serial.printf("C1 item %u/%u: attempt %u/%u. No measurable gain; rock back %u degrees "
                  "and return to the same position, then weigh.\n",
                  piece, requestedQty, attempt, limit, unsigned(Link::ROCK_DEGREES));
  } else {
    Serial.printf("C%u item %u/%u: nudge %u/%u, target %u degrees forward of this item's start.\n",
                  activeWheel, piece, requestedQty, attempt, limit, Link::forwardTargetDegrees(activeWheel, attempt));
  }
}

void enterChecking() {
  state = ST_CHECKING;
  stateStartMs = millis(); // first matched DONE, after the motor's own coast/settling check
  sawGainDuringWait = false;
  tft.fillRect(0, 97, 320, 48, COL_BG);
  centerText("Waiting for drop", 104, 2, COL_TEXT);
  Serial.printf("Wheel stopped. Watching bowl for at least %lu ms.\n", (unsigned long)Link::NUDGE_WAIT_MS);
}
// SERVICE S03: enforce empty-bowl, calibrated scale, validated noise and fresh link.
void startDispense(uint8_t wheel, uint8_t qty) {
  // New preflight faults should never display a previous job's progress.
  detectedDrops = 0;
  nudgeAttempt = 0;
  float empty = 0, margin = 0;
  if (wheel < 1 || wheel > 6 || qty < 1 || qty > 6) {
    enterAlarm("INVALID DOSE");
    return;
  }
  if (pendingInspection) {
    enterAlarm("INSPECT BOWL");
    return;
  }
  if (!storageReady) {
    enterAlarm("STORAGE ERROR");
    return;
  }
  if (!HW::linkReady() || !HW::linkAlive()) {
    enterAlarm("LINK NOT READY");
    return;
  }
  if (!HW::scaleReady() || !HW::weightMargin(margin) || !isfinite(margin) || margin <= 0) {
    enterAlarm("SCALE SETUP");
    return;
  }
  if (!HW::stableWeight(empty) || !isfinite(empty)) {
    enterAlarm("WEIGHT UNSTABLE");
    return;
  }
  if (fabsf(empty) > margin) {
    enterAlarm("BOWL NOT EMPTY");
    return;
  }
  if (!HW::wheelConfigured(wheel)) {
    enterAlarm("WHEEL NOT SET UP");
    return;
  }
  const PieceMass profile = EXPECTED_PIECE[wheel - 1];
  if (!isfinite(profile.grams) || !isfinite(profile.variationGrams) || profile.grams < 0 ||
      profile.variationGrams < 0 || (profile.grams == 0 && profile.variationGrams != 0) ||
      (profile.grams > 0 && profile.variationGrams >= profile.grams)) {
    enterAlarm("BAD MASS SETTINGS");
    return;
  }
  if (prefs.putBool("pending", true) != 1) {
    enterAlarm("STORAGE ERROR");
    return;
  }
  pendingInspection = true;
  activeWheel = wheel;
  requestedQty = qty;
  bowlBaseline = empty;
  pieceBaseline = empty;
  acceptedMargin = margin;
  countConfirmed = false;
  doseWeight = NAN;
  beginNudge(1);
}
// EVENT CHECKER E02: current-job acknowledgement, communication and hardware faults.
// The controller must stay stopped at the matched nudge throughout weighing, review and pickup.
const char *motionFaultName(uint8_t fault) {
  switch (fault) {
  case 1:
    return "JAM";
  case 2:
    return "WHEEL NOT SET UP";
  case 4:
    return "LINK LOST";
  case 5:
    return "EXCESS WHEEL TRAVEL";
  case 6:
    return "STOPPED / INSPECT";
  case 7:
    return "ENCODER FAULT";
  case 8:
    return "MOTION TIMEOUT";
  default:
    return "CONTROLLER FAULT";
  }
}
bool checkActiveJob() {
  if (!activeJob) {
    enterAlarm("JOB LOST");
    return false;
  }
  if (!HW::linkAlive()) {
    enterAlarm("LINK LOST");
    return false;
  }
  if (!HW::scaleReady()) {
    enterAlarm("SCALE FAULT");
    return false;
  }
  if (!HW::jobFresh()) {
    if (millis() - jobStartedMs >= ACK_TIMEOUT_MS)
      enterAlarm("NO START ACK");
    return false;
  }
  if (HW::status.fault || HW::status.phase == 4) {
    Serial.printf("CONTROLLER fault=%u count=%u target=%u\n", unsigned(HW::status.fault),
                  unsigned(HW::status.indexed), requestedQty);
    enterAlarm(motionFaultName(HW::status.fault));
    return false;
  }
  // jobFresh matches the current nudge, including its ordinal; it excludes a
  // previous DONE that is still in flight just after the next target was sent.
  const bool moving = HW::status.phase == 1 && HW::status.indexed + 1 == nudgeAttempt;
  const bool settled = HW::status.phase == 3 && HW::status.indexed == nudgeAttempt;
  if (!(settled || (state == ST_DISPENSING && moving))) {
    enterAlarm("UNEXPECTED MOTION");
    return false;
  }
  return true;
}
void dispensingLoop(BtnEvent e) {
  if (e == BTN_LONG) {
    enterAlarm("STOPPED / INSPECT");
    return;
  }
  if (!checkActiveJob())
    return;
  if (HW::status.phase == 3)
    enterChecking();
}
// SERVICE: show the independent weight measurement and ask for a physical count.
void enterReview(float grams) {
  state = ST_REVIEW;
  stateStartMs = millis();
  reminderAt = millis() + REMINDER_MS;
  doseWeight = grams;
  tft.fillScreen(COL_BG);
  drawTitle("Count the items");
  char line[44];
  snprintf(line, sizeof(line), "C%u: expect %u item%s", activeWheel, detectedDrops,
           detectedDrops == 1 ? "" : "s");
  centerText(line, 68, 2, COL_TEXT);
  snprintf(line, sizeof(line), "Bowl gained %.3f g", doseWeight);
  centerText(line, 106, 2, COL_HINT);
  centerText(detectedDrops < requestedQty ? "Count and leave in bowl" : "Count before removing", 148, 2, COL_TEXT);
  drawHint("SELECT: count matches     BACK: wrong count");
  Serial.printf("REVIEW: expect %u visible item(s), measured %.3f g total.\n",
                detectedDrops, doseWeight);
}

// EVENT CHECKER: apply a configured mass profile to one piece or a cumulative batch.
bool massFitsBatch(PieceMass profile, unsigned quantity, float grams, float noiseMargin) {
  if (profile.grams == 0)
    return true;
  float expected = quantity * profile.grams;
  float tolerance = quantity * profile.variationGrams + noiseMargin;
  return fabsf(grams - expected) <= tolerance;
}

void checkingLoop(BtnEvent event) {
  if (event == BTN_LONG) {
    enterAlarm("STOPPED / INSPECT");
    return;
  }
  if (!checkActiveJob())
    return;
  const uint32_t elapsed = millis() - stateStartMs;
  if (elapsed >= WEIGHT_TIMEOUT_MS) {
    enterAlarm("NO STABLE DROP CHECK");
    return;
  }
  float weight;
  // Every sample in the stable window must be newer than the motor's DONE.
  if (!HW::stableWeightSince(stateStartMs, weight) || !isfinite(weight))
    return;
  const float delta = weight - pieceBaseline;
  if (delta < -acceptedMargin) {
    enterAlarm("BOWL MOVED");
    return;
  }
  if (delta > acceptedMargin)
    sawGainDuringWait = true;
  // Include the end of the observation interval even if polling and HX711
  // conversions run at different rates.
  if (elapsed < Link::NUDGE_WAIT_MS || !HW::sampleSince(stateStartMs + Link::NUDGE_WAIT_MS))
    return;
  if (delta <= acceptedMargin) {
    if (sawGainDuringWait)
      enterAlarm("BOWL CONTENTS CHANGED");
    else if (nudgeAttempt >= Link::maxAttempts(activeWheel))
      enterAlarm("NO DROP / CHECK PATH");
    else
      beginNudge(nudgeAttempt + 1);
    return;
  }
  // A marginal rise can be vibration or drift. Withhold the next motion while
  // the reading is uncertain. VERIFY requires the lightest test piece to
  // produce more than four times the calibrated margin in bench conditions.
  if (delta <= 3.0f * acceptedMargin)
    return;
  const PieceMass profile = EXPECTED_PIECE[activeWheel - 1];
  const float total = weight - bowlBaseline;
  if (!massFitsBatch(profile, 1, delta, acceptedMargin) ||
      !massFitsBatch(profile, detectedDrops + 1, total, acceptedMargin)) {
    Serial.printf("C%u: unexpected step gain %.3f g, cumulative %.3f g.\n", activeWheel, delta, total);
    enterAlarm("WEIGHT MISMATCH");
    return;
  }
  ++detectedDrops;
  pieceBaseline = weight;
  Serial.printf("Stable drop %u/%u, gain %.3f g.\n", detectedDrops, requestedQty, delta);
  if (detectedDrops == requestedQty || profile.grams == 0)
    enterReview(total);
  else
    beginNudge(1);
}

void reviewLoop(BtnEvent event) {
  if (event == BTN_LONG) {
    enterAlarm("COUNT / INSPECT");
    return;
  }
  if (!checkActiveJob())
    return;
  float grams;
  // Confirm only while the same positive load is still in the bowl. Picking up
  // early, or an extra late arrival, sends this batch to manual inspection.
  if (HW::stableWeight(grams) && isfinite(grams)) {
    float added = grams - bowlBaseline;
    if (added <= acceptedMargin || fabsf(added - doseWeight) > acceptedMargin) {
      enterAlarm("BOWL CONTENTS CHANGED");
      return;
    }
    if (event == BTN_SHORT) {
      if (detectedDrops < requestedQty) {
        // An unprofiled weight rise alone cannot distinguish one piece from two.
        // Only an operator-confirmed visible count releases the next item.
        beginNudge(1);
        return;
      }
      countConfirmed = true;
      state = ST_WAITING;
      stateStartMs = millis();
      reminderAt = millis() + REMINDER_MS;
      tft.fillScreen(COL_BG);
      drawTitle("Collect the items");
      centerText("Count confirmed", 78, 2, COL_TEXT);
      centerText("Empty the fixed bowl", 122, 2, COL_HINT);
      drawHint("Leave bowl installed. BACK: stop and inspect");
      Serial.println("Operator confirmed the visible quantity. Waiting for stable empty bowl.");
      return;
    }
  } else if (event == BTN_SHORT) {
    drawHint("Weight changing. Let it settle, then SELECT.");
  }
  if (int32_t(millis() - reminderAt) >= 0) {
    reminderAt = millis() + REMINDER_MS;
    drawTitleColor("Count the items", COL_WARN);
  }
}

// SERVICE S05: acknowledgement is NOT evidence of ingestion.
void acknowledgePickup(const char *how) {
  HW::stop();
  activeJob = false;
  if (batchCount && batchNext >= batchCount) {
    if (prefs.putBool("batch", false) != 1) {
      enterAlarm("STORAGE ERROR");
      return;
    }
    batchCount = 0;
    batchNext = 0;
  }
  if (prefs.putBool("pending", false) != 1) {
    enterAlarm("STORAGE ERROR");
    return;
  }
  pendingInspection = false;
  batchWaitMs = millis();
  struct tm t {};
  if (!calibrationDose && HW::clockNow(t)) {
    const time_t stamp = mktime(&t);
    if (stamp > 0) {
      lastTaken = uint64_t(stamp);
      prefs.putULong64("clearedAt", lastTaken);
    }
  }
  Serial.printf("PICKUP/ACK: %s. Not confirmation of ingestion.\n", how);
  enterIdle();
}
void waitingLoop(BtnEvent event) {
  if (event == BTN_LONG) {
    enterAlarm("STOPPED / INSPECT");
    return;
  }
  if (!checkActiveJob())
    return;
  float grams;
  if (countConfirmed && HW::stableWeight(grams) && isfinite(grams)) {
    const float added = grams - bowlBaseline;
    if (fabsf(added) <= acceptedMargin) {
      acknowledgePickup("operator counted items and fixed bowl returned to empty");
      return;
    }
    if (added < -acceptedMargin || added > doseWeight + acceptedMargin) {
      enterAlarm("CHECK BOWL CONTENTS");
      return;
    }
  }
  if (int32_t(millis() - reminderAt) >= 0) {
    reminderAt = millis() + REMINDER_MS;
    drawTitleColor("Empty the bowl", COL_WARN);
  }
}

// SERVICE S06: all abnormal exits stop first, retain inspection lock, never claim success.
void enterAlarm(const char *msg) {
  HW::stop();
  activeJob = false;
  state = ST_ALARM;
  stateStartMs = millis();
  if (batchCount) {
    pendingInspection = true;
    if (prefs.putBool("pending", true) != 1)
      storageReady = false;
    discardRemainingBatch(msg);
  }
  strlcpy(alarmMsg, msg, sizeof(alarmMsg));
  tft.fillScreen(COL_BG);
  drawTitleColor("Check dispenser", COL_WARN);
  tft.fillRoundRect(10, 60, 300, 62, 12, COL_WARN);
  centerText(alarmMsg, 82, 2, COL_HI_TEXT);
  centerText("Stop. Inspect bowl & path.", 150, 2, COL_TEXT);
  if (nudgeAttempt) {
    char line[36];
    snprintf(line, sizeof(line), "Weight rises: %u / %u", detectedDrops, requestedQty);
    centerText(line, 182, 2, COL_HINT);
  }
  drawHint(!HW::scaleReady() ? "Empty bowl. BACK: zero. SELECT: clear. USB: HELP"
                             : "Clear bowl/path, then SELECT. USB HELP for setup.");
  Serial.printf("STATE 6: ALARM %s. Clear/inspect; no automatic retry.\n", alarmMsg);
}
void alarmLoop(BtnEvent e) {
  if (e == BTN_LONG && !HW::scaleReady()) {
    if (HW::tareEmpty())
      drawHint("Keep empty bowl still; SELECT when zero is ready.");
    else
      drawHintColor("Scale calibration/setup needed; use USB HELP.", COL_WARN);
    return;
  }
  if (e != BTN_SHORT)
    return;
  float g = 0, margin = 0;
  if (!storageReady) {
    drawHintColor("Storage invalid. Resolve before dispensing.", COL_WARN);
    return;
  }
  if (pendingInspection) {
    if (!HW::linkReady() || !HW::linkAlive()) {
      drawHintColor("Waiting for stopped motor link. Retry SELECT.", COL_WARN);
      return;
    }
    if (!HW::scaleReady() || !HW::weightMargin(margin) || !HW::stableWeight(g) || !isfinite(g) ||
        fabsf(g) > margin) {
      drawHintColor("Empty bowl must be stable; USB HELP for scale.", COL_WARN);
      return;
    }
    if (prefs.putBool("pending", false) != 1) {
      drawHintColor("Storage write failed. Inspection still required.", COL_WARN);
      return;
    }
    pendingInspection = false;
  }
  // A backward clock cannot cause replay: lastAttemptMinute remains persisted.
  clockWentBackward = false;
  Serial.println("USER confirmed inspection / acknowledged fault. No automatic retry.");
  enterIdle();
}
