#include "../../include/sensors/flame_sensor.h"
#include "../../include/config.h"
#include <Arduino.h>

FlameSensor::FlameSensor(int dPin, int aPin)
    : digitalPin(dPin), analogPin(aPin), lastDigital(0), lastAnalog(0) {}

FlameSensor::~FlameSensor() {}

bool FlameSensor::init() {
    Serial.println("[FlameSensor] Initializing...");
    pinMode(digitalPin, INPUT);
    delay(100);
    Serial.println("[FlameSensor] Initialization successful");
    return true;
}

bool FlameSensor::read(JsonObject& jsonDoc) {
    int digital = digitalRead(digitalPin);
    int analog = analogRead(analogPin);

    if (analog < FLAME_ANALOG_MIN || analog > FLAME_ANALOG_MAX) {
        Serial.printf("[FlameSensor] Error: Analog value out of range: %d\n", analog);
        return false;
    }

    lastDigital = digital;
    lastAnalog = analog;

    JsonObject digitalObj = jsonDoc["flame_digital"].to<JsonObject>();
    digitalObj["value"] = digital;
    digitalObj["unit"] = "bool";

    JsonObject analogObj = jsonDoc["flame_analog"].to<JsonObject>();
    analogObj["value"] = analog;
    analogObj["unit"] = "raw";

    return true;
}
