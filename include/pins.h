#pragma once
#include <Arduino.h>
// Original Adafruit HUZZAH32, NOT ESP32 Feather V2. GPIO numbers, not A labels.
namespace Pins {
constexpr uint8_t BEAM = 16;  // original HUZZAH32 RX; V2 RX is GPIO7
constexpr uint8_t HX_DATA = 36;
constexpr uint8_t HX_CLOCK = 4;
constexpr uint8_t BUTTON = 19;
constexpr uint8_t LED = 13;
constexpr uint8_t AIN1 = 27;
constexpr uint8_t AIN2 = 33;
constexpr uint8_t ENCODER_A = 34;
constexpr uint8_t ENCODER_B = 14;
constexpr uint8_t MOTOR_ENABLE = 32;
}
// Never silently assume the motor driver from the conflicting source/BOM.
#if defined(COMPONENT_MOTOR) && !defined(MOTOR_DRIVER_DRV8833) && !defined(MOTOR_DRIVER_TB6612)
#error "Select MOTOR_DRIVER_DRV8833 or MOTOR_DRIVER_TB6612 after checking docs/hardware.md"
#endif
#if defined(MOTOR_DRIVER_DRV8833) && defined(MOTOR_DRIVER_TB6612)
#error "Select exactly one motor driver"
#endif
