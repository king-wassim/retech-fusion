#ifndef FLAME_SENSOR_H
#define FLAME_SENSOR_H

#include "sensor_base.h"

class FlameSensor : public SensorBase {
private:
    int digitalPin;
    int analogPin;
    int lastDigital;
    int lastAnalog;

public:
    FlameSensor(int dPin, int aPin);
    ~FlameSensor() override;

    bool init() override;
    bool read(JsonObject& jsonDoc) override;
    const char* getName() const override { return "FlameSensor"; }
};

#endif
