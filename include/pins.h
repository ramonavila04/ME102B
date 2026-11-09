#pragma once
#include <Arduino.h>
// Single system pin map for the ORIGINAL Adafruit HUZZAH32 (product 3591),
// NOT the ESP32 Feather V2. GPIO numbers, not silk labels. See docs/wiring.md.
//
// Rules: GPIO6-11 are flash (not broken out). 34/36/39 are input-only with
// no internal pull-ups. Strapping pins: 12 (MTDI, must be LOW at reset for
// the 3.3 V flash), 15 (MTDO), 0 and 2 (not broken out). The pot uses ADC1
// (GPIO32) because ADC2 is unusable while WiFi is on. Every one of the 21
// header GPIOs is assigned; there are no spare pins.
namespace Pins {
// --- TFT (Adafruit 1770, ILI9341, SPI). Same wiring as the team TFT sketch.
constexpr uint8_t TFT_SCK = 5;
constexpr uint8_t TFT_MOSI = 18;
constexpr uint8_t TFT_CS = 17;   // TX silk
constexpr uint8_t TFT_DC = 13;   // also drives the on-board red LED (flickers with SPI, harmless)
constexpr int8_t TFT_RST = -1;   // not connected: display has its own RC reset; software reset used
// MISO (GPIO19) is NOT used by the display; it is the Back button.

// --- User inputs
constexpr uint8_t POT = 32;         // ADC1_CH4, 10k pot wiper; ends to 3V and GND
constexpr uint8_t BTN_SELECT = 15;  // momentary to GND, internal pull-up (strap: holding it at reset only mutes the ROM log)
constexpr uint8_t BTN_BACK = 19;    // momentary to GND, internal pull-up (MI silk)
constexpr uint8_t BUTTON = BTN_BACK;  // motor component test button

// --- Mechanism sensors
constexpr uint8_t HOME_SWITCH = 39;  // roller microswitch NO to GND; EXTERNAL 10k pull-up to 3V (A3, input-only)
constexpr uint8_t BEAM = 16;         // Adafruit 2167 receiver; external 10k pull-up; LOW = blocked (RX silk)
constexpr uint8_t ENCODER_A = 34;    // input-only; encoder board pull-ups (A2)
constexpr uint8_t ENCODER_B = 14;

// --- Load cell (SparkFun HX711)
constexpr uint8_t HX_DATA = 36;   // input-only; external 10k pull-up (A4)
constexpr uint8_t HX_CLOCK = 4;   // A5

// --- RTC (Adafruit 3013 DS3231, I2C address 0x68)
constexpr uint8_t I2C_SDA = 23;
constexpr uint8_t I2C_SCL = 22;

// --- Motor driver (Adafruit TB6612, channel A)
constexpr uint8_t AIN1 = 27;
constexpr uint8_t AIN2 = 33;
constexpr uint8_t PWMA = 21;          // LEDC PWM, 20 kHz
constexpr uint8_t MOTOR_ENABLE = 26;  // TB6612 STBY (or DRV8833 nSLEEP); EXTERNAL 10k pull-down (A0)

// --- Indicators
constexpr uint8_t BUZZER = 25;  // piezo via NPN transistor (A1)
constexpr uint8_t LED = 12;     // external status LED + 330R to GND (strap pin: the LED load keeps it LOW at reset)
}  // namespace Pins

// Never silently assume the motor driver from the conflicting source/BOM.
#if defined(COMPONENT_MOTOR) && !defined(MOTOR_DRIVER_DRV8833) && !defined(MOTOR_DRIVER_TB6612)
#error "Select MOTOR_DRIVER_DRV8833 or MOTOR_DRIVER_TB6612 after checking docs/hardware.md"
#endif
#if defined(MOTOR_DRIVER_DRV8833) && defined(MOTOR_DRIVER_TB6612)
#error "Select exactly one motor driver"
#endif
