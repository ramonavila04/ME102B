// Potentiometer -> color bar on the Adafruit 2.8" TFT (ILI9341)
// Board: Adafruit HUZZAH32 ESP32 Feather
// Wiring updated to match schematic Rev 1:
//   TFT: CLK -> SCK (5), MOSI -> MO (18), CS -> TX (17), D/C -> 13, MISO not connected
//   Pot: wiper -> GPIO 32 (W15), outer legs -> 3V and GND

#include <SPI.h>
#include <Adafruit_GFX.h>
#include <Adafruit_ILI9341.h>

#define TFT_CS   17
#define TFT_DC   13
#define TFT_RST  -1     // not connected
#define POT_PIN  32

Adafruit_ILI9341 tft = Adafruit_ILI9341(TFT_CS, TFT_DC, TFT_RST);

// Bar position and size (screen is 320 x 240 in landscape)
const int BAR_X = 20;
const int BAR_Y = 90;
const int BAR_W = 280;
const int BAR_H = 70;

int lastRaw = -100;     // forces a draw on the first loop

// Average several readings to smooth out ESP32 ADC noise
int readPot() {
  long sum = 0;
  for (int i = 0; i < 16; i++) sum += analogRead(POT_PIN);
  return sum / 16;
}

// Green at 0%, yellow at 50%, red at 100%
uint16_t barColor(int percent) {
  uint8_t r, g;
  if (percent < 50) {
    r = map(percent, 0, 50, 0, 255);
    g = 255;
  } else {
    r = 255;
    g = map(percent, 50, 100, 255, 0);
  }
  return tft.color565(r, g, 0);
}

void setup() {
  Serial.begin(9600);
  SPI.begin(5, -1, 18);           // SCK, no MISO (GPIO 19 is the button), MOSI
  tft.begin();
  tft.setRotation(1);             // landscape
  tft.fillScreen(ILI9341_BLACK);

  tft.setTextColor(ILI9341_WHITE);
  tft.setTextSize(3);
  tft.setCursor(20, 30);
  tft.print("Pot level");

  // Outline around the bar
  tft.drawRect(BAR_X - 2, BAR_Y - 2, BAR_W + 4, BAR_H + 4, ILI9341_WHITE);
}

void loop() {
  int raw = readPot();

  // Only redraw when the knob actually moved (prevents flicker from noise)
  if (abs(raw - lastRaw) < 20) return;
  lastRaw = raw;

  int percent = map(raw, 0, 4095, 0, 100);
  int fillW   = map(percent, 0, 100, 0, BAR_W);

  // Filled portion, then clear the remainder
  tft.fillRect(BAR_X, BAR_Y, fillW, BAR_H, barColor(percent));
  tft.fillRect(BAR_X + fillW, BAR_Y, BAR_W - fillW, BAR_H, ILI9341_BLACK);

  // Percentage readout (black background erases the old number)
  tft.setTextColor(ILI9341_WHITE, ILI9341_BLACK);
  tft.setTextSize(4);
  tft.setCursor(110, 185);
  tft.printf("%3d%%", percent);

  Serial.printf("Raw: %4d  Percent: %3d\n", raw, percent);
  delay(30);
}
