"""esp_simulator.py — Simulates an ESP32 publishing energy sensor data over MQTT.

Publishes a JSON payload to topic `retech/energy/sensors` every 5 seconds.
Values are gaussian noise around realistic means (calibrated against the
historical Excel dataset). A random anomaly is injected ~once per minute.

Run standalone:
    python src/iot/esp_simulator.py
Or in Docker (env var MQTT_BROKER set to `mosquitto`).
"""
from __future__ import annotations

import json
import os
import random
import time
from datetime import datetime, timezone

import paho.mqtt.client as mqtt
from loguru import logger

MQTT_BROKER = os.getenv("MQTT_BROKER", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", 1883))
MQTT_TOPIC = os.getenv("MQTT_PUB_TOPIC", "retech/energy/sensors")
DEVICE_ID = os.getenv("DEVICE_ID", "ESP32_001")
PUBLISH_INTERVAL = float(os.getenv("PUBLISH_INTERVAL", 5.0))
ANOMALY_EVERY_S = float(os.getenv("ANOMALY_EVERY_S", 60.0))

# Realistic baselines (from BILAN TOTAL cogeneration ranges)
BASELINES = {
    "temperature_c": (42.5, 2.0),
    "humidity_pct":  (65.0, 5.0),
    "power_kw":      (850.0, 35.0),
    "voltage_v":     (398.0, 1.5),
    "current_a":     (1250.0, 40.0),
    "gas_flow_nm3h": (120.0, 5.0),
    "co2_ppm":       (450.0, 20.0),
}


def _make_payload(energy_kwh: float, anomaly: bool) -> dict:
    p = {
        "device_id": DEVICE_ID,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    for k, (mu, sigma) in BASELINES.items():
        p[k] = round(random.gauss(mu, sigma), 2)
    p["energy_kwh"] = round(energy_kwh, 2)

    if anomaly:
        which = random.choice(list(BASELINES.keys()))
        spike_factor = random.choice([2.5, 3.0, 0.2, 0.0, -1.5])
        p[which] = round(BASELINES[which][0] * spike_factor, 2)
        p["_injected_anomaly"] = which
        logger.warning(f"Injected anomaly on {which} -> {p[which]}")
    return p


def main() -> None:
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                         client_id=f"sim-{DEVICE_ID}")
    logger.info(f"Connecting to MQTT broker {MQTT_BROKER}:{MQTT_PORT}")
    while True:
        try:
            client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
            break
        except OSError as e:
            logger.warning(f"Broker not ready ({e}); retrying in 2s")
            time.sleep(2)

    client.loop_start()
    logger.success(f"Publishing to '{MQTT_TOPIC}' every {PUBLISH_INTERVAL}s")

    energy_kwh = 12_000.0
    last_anomaly_t = time.time()

    try:
        while True:
            now = time.time()
            anomaly = (now - last_anomaly_t) >= ANOMALY_EVERY_S and random.random() < 0.5
            if anomaly:
                last_anomaly_t = now

            energy_kwh += random.uniform(0.8, 1.4)
            payload = _make_payload(energy_kwh, anomaly)
            client.publish(MQTT_TOPIC, json.dumps(payload), qos=0)
            logger.info(f"Published: power={payload['power_kw']}kW "
                        f"temp={payload['temperature_c']}°C "
                        f"energy={payload['energy_kwh']}kWh")
            time.sleep(PUBLISH_INTERVAL)
    except KeyboardInterrupt:
        logger.info("Simulator stopped")
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()
