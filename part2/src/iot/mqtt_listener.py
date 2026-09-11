"""mqtt_listener.py — Subscribe to the MQTT broker, store + enrich messages.

Each incoming JSON payload is:
  - appended raw to data/iot/live_sensors.json (JSON Lines)
  - enriched with simple anomaly flags + CO2 estimate, then appended
    to data/iot/live_enriched.json

The listener can be run standalone (foreground) or started as a background
thread from the Streamlit dashboard via `start_listener_thread()`.
"""
from __future__ import annotations

import json
import os
import threading
import time
from collections import defaultdict, deque
from pathlib import Path
from typing import Optional
from datetime import datetime, timezone

import paho.mqtt.client as mqtt
from dotenv import load_dotenv
from loguru import logger

load_dotenv()

ROOT = Path(__file__).resolve().parents[2]
IOT_DIR = ROOT / "data" / "iot"
RAW_LOG = IOT_DIR / "live_sensors.json"
ENRICHED_LOG = IOT_DIR / "live_enriched.json"

MQTT_BROKER = os.getenv("MQTT_BROKER", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", 1883))
_DEFAULT_TOPICS = ("esp32/sensors", "retech/energy/sensors")


def _get_topics() -> list[str]:
    raw_topics = os.getenv("MQTT_TOPICS")
    if raw_topics:
        topics = [topic.strip() for topic in raw_topics.replace(";", ",").split(",")]
        return [topic for topic in topics if topic]

    topics = list(_DEFAULT_TOPICS)
    legacy_topic = os.getenv("MQTT_TOPIC")
    if legacy_topic and legacy_topic not in topics:
        topics.insert(0, legacy_topic)
    return topics


MQTT_TOPICS = _get_topics()

CO2_FACTOR_GRID = float(os.getenv("CO2_FACTOR_KG_PER_KWH", 0.468))

# Small per-metric rolling history for z-score anomaly detection
_HISTORY_LEN = 30
_history: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=_HISTORY_LEN))

# Thresholds (sensible defaults; tweak per use case)
_HARD_LIMITS = {
    "temperature_c": (-10, 120),
    "humidity_pct":  (0, 100),
    "power_kw":      (0, 5000),
    "voltage_v":     (200, 500),
    "current_a":     (0, 5000),
    "gas_flow_nm3h": (0, 1000),
    "co2_ppm":       (300, 5000),
}


def _flatten_payload(payload: dict) -> dict:
    flattened = dict(payload)
    sensors = payload.get("sensors")
    if isinstance(sensors, dict):
        for sensor_name, sensor_value in sensors.items():
            if isinstance(sensor_value, dict):
                if "value" in sensor_value:
                    flattened[sensor_name] = sensor_value["value"]
                    unit = sensor_value.get("unit")
                    if unit is not None:
                        flattened[f"{sensor_name}_unit"] = unit
                else:
                    flattened[sensor_name] = sensor_value
            else:
                flattened[sensor_name] = sensor_value
    return flattened


def _coerce_timestamp(payload: dict, received_at: str) -> tuple[str, Optional[int]]:
    timestamp = payload.get("timestamp")
    if isinstance(timestamp, str):
        try:
            parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"), None
        except ValueError:
            pass

    if isinstance(timestamp, (int, float)) and timestamp >= 10_000_000_000:
        parsed = datetime.fromtimestamp(float(timestamp) / 1000.0, tz=timezone.utc)
        return parsed.isoformat().replace("+00:00", "Z"), None

    device_uptime_ms = None
    if isinstance(timestamp, (int, float)):
        device_uptime_ms = int(timestamp)

    return received_at, device_uptime_ms


def _zscore(values: deque[float], v: float) -> float:
    n = len(values)
    if n < 5:
        return 0.0
    mean = sum(values) / n
    var = sum((x - mean) ** 2 for x in values) / n
    if var <= 1e-9:
        return 0.0
    return abs((v - mean) / (var ** 0.5))


def _enrich(payload: dict) -> dict:
    received_at = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    flattened = _flatten_payload(payload)
    enriched = dict(flattened)
    enriched["raw_payload"] = payload
    enriched["received_at"] = received_at
    enriched["timestamp"], device_uptime_ms = _coerce_timestamp(flattened, received_at)
    if device_uptime_ms is not None:
        enriched["device_uptime_ms"] = device_uptime_ms
    anomalies: list[str] = []
    for key, (lo, hi) in _HARD_LIMITS.items():
        if key not in payload:
            continue
        try:
            v = float(payload[key])
        except (TypeError, ValueError):
            continue
        if v < lo or v > hi:
            anomalies.append(f"{key}_out_of_range")
        z = _zscore(_history[key], v)
        if z > 3.0:
            anomalies.append(f"{key}_zscore={z:.1f}")
        _history[key].append(v)

    enriched["is_anomaly"] = bool(anomalies)
    enriched["anomaly_reasons"] = anomalies

    # Quick CO2 estimate over the publish window (5s default)
    power_kw = payload.get("power_kw")
    if isinstance(power_kw, (int, float)):
        kwh_in_window = float(power_kw) * (5.0 / 3600.0)
        enriched["window_kwh"] = round(kwh_in_window, 4)
        enriched["window_co2_kg"] = round(kwh_in_window * CO2_FACTOR_GRID, 4)
    return enriched


def _append_jsonl(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def _on_connect(client, userdata, flags, reason_code, properties=None):
    logger.success(f"Connected to MQTT (rc={reason_code}); subscribing {', '.join(MQTT_TOPICS)}")
    for topic in MQTT_TOPICS:
        client.subscribe(topic, qos=0)


def _on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        logger.warning(f"Bad payload: {e}")
        return

    raw_record = dict(payload)
    raw_record["mqtt_topic"] = msg.topic
    raw_record["received_at"] = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    _append_jsonl(RAW_LOG, raw_record)
    enriched = _enrich(payload)
    enriched["mqtt_topic"] = msg.topic
    _append_jsonl(ENRICHED_LOG, enriched)
    if enriched["is_anomaly"]:
        logger.warning(f"ANOMALY {enriched['anomaly_reasons']}")


def _build_client() -> mqtt.Client:
    c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="retech-listener")
    c.on_connect = _on_connect
    c.on_message = _on_message
    return c


def run_forever() -> None:
    client = _build_client()
    while True:
        try:
            client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
            break
        except OSError as e:
            logger.warning(f"Broker not ready ({e}); retrying in 2s")
            time.sleep(2)
    client.loop_forever()


_thread: Optional[threading.Thread] = None
_thread_lock = threading.Lock()


def start_listener_thread() -> None:
    """Start the listener in a daemon thread. Idempotent."""
    global _thread
    with _thread_lock:
        if _thread is not None and _thread.is_alive():
            return
        _thread = threading.Thread(target=run_forever, daemon=True,
                                   name="mqtt-listener")
        _thread.start()
        logger.info("MQTT listener thread started")


if __name__ == "__main__":
    run_forever()
