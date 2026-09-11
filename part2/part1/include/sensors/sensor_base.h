#ifndef SENSOR_BASE_H
#define SENSOR_BASE_H

#include <ArduinoJson.h>

class SensorBase {
public:
    virtual ~SensorBase() {}

    virtual bool init() = 0;
    virtual bool read(JsonObject& jsonDoc) = 0;
    virtual const char* getName() const = 0;
};

#endif
