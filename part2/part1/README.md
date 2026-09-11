# ESP32 IoT Sensor Device - Part 1

This folder contains the MQTT sender firmware used by the Re·Tech Fusion pipeline.

## What it does
- Connects the ESP32 to Wi-Fi
- Reads the DHT22 and flame sensors
- Publishes JSON payloads to MQTT topic `esp32/sensors`
- Buffers readings locally when MQTT is unavailable
- Flushes buffered messages after reconnection

## Build

Open this folder in PlatformIO, then run:

```bash
pio run
pio run --target upload
pio device monitor
```

## Configure

Edit [include/config.h](include/config.h) for your Wi-Fi credentials, broker IP, pins, and timing.
