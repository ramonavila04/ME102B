#include "pins.h"
/*
 UI panel bring-up test: TFT (ILI9341) + pot + Select/Back buttons + DS3231
 RTC + home switch + buzzer + status LED, on the ORIGINAL HUZZAH32.
 Motor driver must be unpowered or STBY held low (this test drives STBY LOW).
 Based on the team TFT sketch (docs/drive-import/potentiometer_code_to_screen.ino).
 Serial Monitor 115200. Commands: T YYYY-MM-DD HH:MM:SS sets the RTC.

 Pass: pot bar follows the knob end to end; SEL/BACK/HOME read 1 only while
 pressed; RTC seconds tick and survive a reset (and a power cycle with the
 CR1220 fitted); Select beeps the buzzer; the status LED blinks at 1 Hz.
*/
#include <Adafruit_GFX.h>
#include <Adafruit_ILI9341.h>
#include <Arduino.h>
#include <RTClib.h>
#include <SPI.h>
#include <Wire.h>

Adafruit_ILI9341 tft(Pins::TFT_CS, Pins::TFT_DC, Pins::TFT_RST);
RTC_DS3231 rtc;
bool rtcFound = false;
int lastBar = -1;
uint32_t lastDrawMs = 0, beepUntilMs = 0;
bool lastSel = false;
char line[48];
int lineLen = 0;

int readPot() {
  long sum = 0;
  for (int i = 0; i < 16; i++) sum += analogRead(Pins::POT);
  return sum / 16;
}

void setup() {
  pinMode(Pins::MOTOR_ENABLE, OUTPUT);
  digitalWrite(Pins::MOTOR_ENABLE, LOW);  // keep the motor driver in standby
  pinMode(Pins::BTN_SELECT, INPUT_PULLUP);
  pinMode(Pins::BTN_BACK, INPUT_PULLUP);
  pinMode(Pins::HOME_SWITCH, INPUT);  // external 10k pull-up
  pinMode(Pins::LED, OUTPUT);
  ledcSetup(2, 2700, 8);
  ledcAttachPin(Pins::BUZZER, 2);
  Serial.begin(115200);
  SPI.begin(Pins::TFT_SCK, -1, Pins::TFT_MOSI);  // no MISO: GPIO19 is the Back button
  tft.begin();
  tft.setRotation(1);
  tft.fillScreen(ILI9341_BLACK);
  tft.setTextColor(ILI9341_WHITE, ILI9341_BLACK);
  tft.setTextSize(3);
  tft.setCursor(10, 8);
  tft.print("UI panel test");
  tft.drawRect(18, 58, 284, 34, ILI9341_WHITE);
  Wire.begin(Pins::I2C_SDA, Pins::I2C_SCL);
  rtcFound = rtc.begin(&Wire);
  Serial.printf("\nUI panel test. RTC %s%s\n", rtcFound ? "found" : "NOT FOUND",
                rtcFound && rtc.lostPower() ? " (lost power: set with T YYYY-MM-DD HH:MM:SS)" : "");
}

void loop() {
  const uint32_t now = millis();
  while (Serial.available()) {
    const char c = Serial.read();
    if (c == '\n' || c == '\r') {
      line[lineLen] = '\0';
      int y, mo, d, h, mi, s;
      if (lineLen && sscanf(line, "T %d-%d-%d %d:%d:%d", &y, &mo, &d, &h, &mi, &s) == 6 && rtcFound) {
        rtc.adjust(DateTime(y, mo, d, h, mi, s));
        Serial.println("RTC set");
      }
      lineLen = 0;
    } else if (lineLen < 47) {
      line[lineLen++] = c;
    }
  }

  const bool sel = digitalRead(Pins::BTN_SELECT) == LOW;
  const bool back = digitalRead(Pins::BTN_BACK) == LOW;
  const bool home = digitalRead(Pins::HOME_SWITCH) == LOW;
  if (sel && !lastSel) beepUntilMs = now + 150;
  lastSel = sel;
  ledcWrite(2, now < beepUntilMs ? 128 : 0);
  digitalWrite(Pins::LED, (now % 1000) < 500 ? HIGH : LOW);

  if (now - lastDrawMs < 100) return;
  lastDrawMs = now;
  const int raw = readPot();
  const int bar = map(raw, 0, 4095, 0, 280);
  if (abs(bar - lastBar) > 1) {
    tft.fillRect(20, 60, bar, 30, ILI9341_GREEN);
    tft.fillRect(20 + bar, 60, 280 - bar, 30, ILI9341_BLACK);
    lastBar = bar;
  }
  tft.setTextSize(2);
  tft.setCursor(10, 110);
  tft.printf("POT %4d  (GPIO%d)   ", raw, Pins::POT);
  tft.setCursor(10, 140);
  tft.printf("SEL %d  BACK %d  HOME %d ", sel, back, home);
  tft.setCursor(10, 170);
  if (rtcFound) {
    const DateTime t = rtc.now();
    tft.printf("RTC %04d-%02d-%02d %02d:%02d:%02d", t.year(), t.month(), t.day(), t.hour(), t.minute(),
               t.second());
  } else {
    tft.print("RTC not found          ");
  }
  static uint32_t lastPrint = 0;
  if (now - lastPrint >= 1000) {
    lastPrint = now;
    Serial.printf("pot %d | sel %d back %d home %d | rtc %s\n", raw, sel, back, home,
                  rtcFound ? "ok" : "missing");
  }
}
