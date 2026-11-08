#include <Arduino.h>
#include "pins.h"
// Bring-up scaffold only. No scheduling or automatic dispensing yet.
void setup() {
  pinMode(Pins::MOTOR_ENABLE, OUTPUT);
  digitalWrite(Pins::MOTOR_ENABLE, LOW);
  pinMode(Pins::AIN1, OUTPUT);
  digitalWrite(Pins::AIN1, LOW);
  pinMode(Pins::AIN2, OUTPUT);
  digitalWrite(Pins::AIN2, LOW);
  Serial.begin(115200);
  Serial.println("Dispenser scaffold: motor disabled; run component tests separately.");
}
void loop() { delay(10); }
