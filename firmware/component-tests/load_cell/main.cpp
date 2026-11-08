#include "pins.h"
/*
 TAL221 100 g + SparkFun HX711 + Adafruit Feather ESP32 V2 / HUZZAH32.
 Standalone USB-powered test: disconnect the old regulator, motor and other
 modules first. HX711 VCC and VDD -> 3V; GND -> GND; DAT -> GPIO36/A4;
 SCK -> GPIO4/A5. Add 10k between DAT and 3V (GPIO36 has no internal pull-up).
 Cell: red E+, black E-, green A+, white A-.

 Dependency: bogde HX711 Arduino Library 0.7.5 (MIT), pinned in platformio.ini.
 PlatformIO installs the dependency automatically.
 Serial Monitor: 115200 baud. Send t with the installed cup EMPTY.
 Then add exactly KNOWN_MASS_G grams, let it settle, and send c.
 Remove the reference mass before testing. Repeat t and c after each reset.
 While waiting, calibration instructions repeat every five seconds.
 Tare excludes the cup from the reading, not from the 100 g load limit.
*/

#include <Arduino.h>
#include <HX711.h>
#include <math.h>

constexpr uint8_t HX_DATA = Pins::HX_DATA;  // Feather A4
constexpr uint8_t HX_CLOCK = Pins::HX_CLOCK;  // Feather A5
constexpr double KNOWN_MASS_G = 10.0;  // EDIT to match your reference mass
constexpr double FULL_THRESHOLD_G = 2.0;
constexpr bool PRINT_WEIGHT = true;   // false: print only Full / Not full

HX711 scale;
double zeroRaw = 0.0;
double countsPerGram = 0.0;
bool tared = false;
bool calibrated = false;
unsigned long lastPromptMs = 0;

void printWaitingInstructions() {
 if (!tared) {
   Serial.println("Waiting: empty the installed cup, type t, then press Enter.");
 } else {
   Serial.print("Waiting: add a known ");
   Serial.print(KNOWN_MASS_G, 3);
   Serial.println(" g mass, let it settle, type c, then press Enter.");
 }
 lastPromptMs = millis();
}

// Average fresh conversions, checking readiness before EVERY read.
// A timeout or saturated ADC is an error, never a valid weight.
bool readMean(double &mean, uint8_t samples, bool discardPending = false) {
 // While waiting for a command, HX711 may retain a reading from before
 // the reference mass was placed. Discard it before tare/calibration.
 if (discardPending) {
   if (!scale.wait_ready_timeout(1000)) return false;
   scale.read();
 }
 int64_t sum = 0;
 for (uint8_t i = 0; i < samples; ++i) {
   if (!scale.wait_ready_timeout(1000)) return false;
   const long raw = scale.read();
   if (raw == 8388607L || raw == -8388608L) return false;
   sum += raw;
 }
 mean = static_cast<double>(sum) / samples;
 return true;
}

void setup() {
 Serial.begin(115200);
 delay(2000);
 Serial.println("\nLoad-cell test V2: Full only when weight > 2.0 g.");
 scale.begin(HX_DATA, HX_CLOCK);
 printWaitingInstructions();
}

void loop() {
 if (Serial.available()) {
   const char command = Serial.read();
   if (command == 't' || command == 'T') {
     calibrated = false;
     tared = false;
     Serial.println("Taring: keep the EMPTY cup still...");
     tared = readMean(zeroRaw, 20, true);
     Serial.println(tared ? "Zero set. Add the reference mass, then send c."
                          : "Sensor error: check HX711 wiring and mounting.");
     lastPromptMs = millis();
   } else if (command == 'c' || command == 'C') {
     calibrated = false;
     if (!tared) {
       Serial.println("First empty the cup and send t.");
     } else {
       double loadedRaw;
       Serial.println("Calibrating: keep the reference mass still...");
       if (!isfinite(KNOWN_MASS_G) || KNOWN_MASS_G <= 0.0 ||
           KNOWN_MASS_G > 100.0 || !readMean(loadedRaw, 20, true)) {
         Serial.println("Calibration failed: check sensor and reference mass.");
       } else {
         countsPerGram = (loadedRaw - zeroRaw) / KNOWN_MASS_G;
         calibrated = isfinite(countsPerGram) && countsPerGram != 0.0;
         // A negative factor is valid when load-cell polarity is reversed.
         Serial.println(calibrated
             ? "Calibrated. Remove reference mass; ready to test."
             : "No load change detected. Check mounting and reference mass.");
       }
     }
     lastPromptMs = millis();
   }
 }

 if (!calibrated) {
   if (millis() - lastPromptMs >= 5000UL) {
     printWaitingInstructions();
   }
   delay(10);
   return;  // Do not label uncalibrated raw counts as grams.
 }

 double raw;
 if (!readMean(raw, 5)) {
   Serial.println("Sensor error: no valid weight. Check HX711 connections.");
   delay(250);
   return;
 }

 const double grams = (raw - zeroRaw) / countsPerGram;
 if (PRINT_WEIGHT) {
   Serial.print(grams, 3);
   Serial.print(" g | ");
 }
 Serial.println(grams > FULL_THRESHOLD_G ? "Full" : "Not full");
 delay(100);
}
