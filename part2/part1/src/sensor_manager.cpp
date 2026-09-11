#include "../include/sensor_manager.h"
#include <Arduino.h>

SensorManager::SensorManager() {}

SensorManager::~SensorManager() {
    for (SensorBase* sensor : sensors) {
        delete sensor;
    }
    sensors.clear();
}

void SensorManager::addSensor(SensorBase* sensor) {
    if (sensor != nullptr) {
        sensors.push_back(sensor);
        Serial.printf("[SensorManager] Registered sensor: %s\n", sensor->getName());
    }
}

bool SensorManager::initAll() {
    Serial.printf("[SensorManager] Initializing %d sensor(s)...\n", sensors.size());

    bool allSuccess = true;
    for (SensorBase* sensor : sensors) {
        if (!sensor->init()) {
            Serial.printf("[SensorManager] Error initializing %s\n", sensor->getName());
            allSuccess = false;
        }
    }

    if (allSuccess) {
        Serial.println("[SensorManager] All sensors initialized successfully");
    }
    return allSuccess;
}

bool SensorManager::readAll(JsonDocument& jsonDoc) {
    jsonDoc.clear();
    jsonDoc["timestamp"] = millis();

    JsonObject sensorsObj = jsonDoc["sensors"].to<JsonObject>();
    bool allSuccess = true;

    for (SensorBase* sensor : sensors) {
        JsonObject sensorObj = sensorsObj.createNestedObject(sensor->getName());
        if (!sensor->read(sensorObj)) {
            Serial.printf("[SensorManager] Error reading from %s\n", sensor->getName());
            allSuccess = false;
        }
    }

    return allSuccess;
}
