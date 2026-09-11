#ifndef DHT22_SENSOR_H
#define DHT22_SENSOR_H

#include "sensor_base.h"
#include <DHT.h>

class DHT22Sensor : public SensorBase {
private:
    DHT dht;
    int pin;
    float lastTemperature;
    float lastHumidity;

public:
    explicit DHT22Sensor(int dhtPin);
    ~DHT22Sensor() override;

    bool init() override;
    bool read(JsonObject& jsonDoc) override;
    const char* getName() const override { return "DHT22"; }
};

#endif
