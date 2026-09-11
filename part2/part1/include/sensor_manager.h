#ifndef SENSOR_MANAGER_H
#define SENSOR_MANAGER_H

#include "sensors/sensor_base.h"
#include <ArduinoJson.h>
#include <vector>

class SensorManager {
private:
    std::vector<SensorBase*> sensors;

public:
    SensorManager();
    ~SensorManager();

    void addSensor(SensorBase* sensor);
    bool initAll();
    bool readAll(JsonDocument& jsonDoc);
    int getSensorCount() const { return sensors.size(); }
};

#endif
