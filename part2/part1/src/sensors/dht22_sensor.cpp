#include "../../include/sensors/dht22_sensor.h"
#include "../../include/config.h"
#include <Arduino.h>

DHT22Sensor::DHT22Sensor(int dhtPin)
    : dht(dhtPin, DHT22), pin(dhtPin), lastTemperature(0), lastHumidity(0) {}

DHT22Sensor::~DHT22Sensor() {}

bool DHT22Sensor::init() {
    Serial.println("[DHT22] Initializing...");
    dht.begin();
    delay(1000);

    float temp = dht.readTemperature();
    float hum = dht.readHumidity();
    if (isnan(temp) || isnan(hum)) {
        Serial.println("[DHT22] Warning: Initial read returned NaN");
        return false;
    }

    Serial.println("[DHT22] Initialization successful");
    return true;
}

bool DHT22Sensor::read(JsonObject& jsonDoc) {
    float temperature = dht.readTemperature();
    float humidity = dht.readHumidity();

    if (isnan(temperature) || isnan(humidity)) {
        Serial.println("[DHT22] Error: Invalid reading (NaN)");
        return false;
    }

    if (temperature < TEMP_MIN || temperature > TEMP_MAX) {
        Serial.printf("[DHT22] Warning: Temperature out of range: %.2f\n", temperature);
        return false;
    }

    if (humidity < HUMIDITY_MIN || humidity > HUMIDITY_MAX) {
        Serial.printf("[DHT22] Warning: Humidity out of range: %.2f\n", humidity);
        return false;
    }

    lastTemperature = temperature;
    lastHumidity = humidity;

    JsonObject tempObj = jsonDoc["temperature"].to<JsonObject>();
    tempObj["value"] = temperature;
    tempObj["unit"] = "C";

    JsonObject humObj = jsonDoc["humidity"].to<JsonObject>();
    humObj["value"] = humidity;
    humObj["unit"] = "%";

    return true;
}
