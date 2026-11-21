#pragma once
#include <Arduino.h>
// Pin map of the MOTION board: Adafruit ESP32 Feather V2 (product 5400, PlatformIO
// `adafruit_feather_esp32_v2`). GPIO numbers, not silk labels; checked against the board
// definition variants/adafruit_feather_esp32_v2/pins_arduino.h in espressif/arduino-esp32.
// See docs/electronics_v8.md for the wiring.
//
// Header GPIOs on this board: 4 5 7 8 12 13 14 15 19 20 21 22 25 26 27 32 33 34 36 39.
// 34/36/39 are input-only with no internal pull-ups. 12 and 15 are strapping pins (12 must
// not be pulled high at reset). 13 drives the red LED. GPIO2 switches NeoPixel/STEMMA power.
// Six modules share signals because only one moves at a time:
//   - one PWM line to all six TB6612 channels; each module's IN1/IN2 come from two 74HC595
//     shift registers (all other modules sit in TB6612 "stop", IN1 = IN2 = LOW);
//   - each module's encoder A/B goes through two 74HC4051 8:1 multiplexers (shared select);
//   - the six IR receivers (open collector) are wired-OR onto one input.
namespace MotionPins {
// --- Link to the main board (HUZZAH32), Serial1, crossed TX/RX, common ground
constexpr uint8_t LINK_RX = 7;   // RX silk
constexpr uint8_t LINK_TX = 8;   // TX silk

// --- Motor drivers: three Adafruit TB6612 breakouts (2 channels each = 6 motors)
constexpr uint8_t MOTOR_PWM = 26;   // A0 silk: to PWMA and PWMB of all three boards (LEDC, 20 kHz)
constexpr uint8_t MOTOR_STBY = 13;  // to STBY of all three boards (red LED on = drivers enabled)
constexpr uint8_t SR_DATA = 19;     // MO silk: 74HC595 SER (first register)
constexpr uint8_t SR_CLOCK = 5;     // SCK silk: 74HC595 SRCLK (both)
constexpr uint8_t SR_LATCH = 21;    // MI silk: 74HC595 RCLK (both)
// Shift-register bit 2k = module k IN1, bit 2k+1 = module k IN2 (k = 0..5); bits 12-15 spare.

// --- Encoders through the multiplexers (Pololu encoder boards have their own pull-ups)
constexpr uint8_t ENC_A = 34;   // A2 silk, input-only: common output of the "A" 74HC4051
constexpr uint8_t ENC_B = 39;   // A3 silk, input-only: common output of the "B" 74HC4051
constexpr uint8_t MUX_S0 = 25;  // A1 silk: select bit 0 (both multiplexers)
constexpr uint8_t MUX_S1 = 4;   // A5 silk: select bit 1
constexpr uint8_t MUX_S2 = 14;  // select bit 2 (channels 0-5 used)

// --- Beam-breaks: six Adafruit 2167 receivers wired-OR, EXTERNAL 10k pull-up to 3V
constexpr uint8_t BEAM = 36;  // A4 silk, input-only; LOW = some beam blocked

// --- Home switches, one per module, switch to GND, internal pull-up (LOW = actuated)
constexpr uint8_t HOME[6] = {32, 33, 27, 15, 22, 20};  // 22 = SDA silk, 20 = SCL silk
}  // namespace MotionPins
