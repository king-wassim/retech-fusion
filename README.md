<div align="center">

# ⚡ Re·Tech Fusion

### End-to-End IoT Energy Monitoring & Anomaly Detection Platform

*Hackathon project — INSAT, University of Carthage*

[![PlatformIO](https://img.shields.io/badge/PlatformIO-ESP32-orange?logo=platformio)](https://platformio.org/)
[![Python](https://img.shields.io/badge/Python-3.11%2B-blue?logo=python)](https://python.org)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.39-red?logo=streamlit)](https://streamlit.io)
[![MQTT](https://img.shields.io/badge/MQTT-Mosquitto-660066?logo=mqtt)](https://mosquitto.org)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker)](https://docker.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

</div>

---

## Table of Contents

- [Overview](#overview)
- [System Architecture](#system-architecture)
- [Part 1 — ESP32 Firmware](#part-1--esp32-firmware)
- [Part 2 — Data Pipeline & Dashboard](#part-2--data-pipeline--dashboard)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [Project Structure](#project-structure)
- [Tech Stack](#tech-stack)
- [Data Flow](#data-flow)

---

## Overview

**Re·Tech Fusion** is a full-stack IoT + data engineering platform built around energy monitoring in industrial and smart-building contexts.

It solves a real-world problem: energy data arrives in a dozen incompatible formats — Excel billing reports, scanned PDF invoices, WhatsApp photos of meter readings, and live sensor streams from embedded hardware. This project ingests all of them, normalizes everything to kWh, computes CO₂ emissions, detects anomalies, and exposes the result through a live, dark-themed Streamlit dashboard.

The system has two tightly coupled parts:

| Part | Description |
|------|-------------|
| **Part 1** | ESP32 firmware (C++ / Arduino / PlatformIO) that reads a DHT22 (temperature + humidity) and a flame sensor, then publishes structured JSON to an MQTT broker every 5 seconds — with an offline ring-buffer to replay readings after reconnection. |
| **Part 2** | Python data pipeline + Streamlit dashboard that ingests heterogeneous sources (Excel, PDF, images, live MQTT), normalizes units, computes CO₂ emissions, runs anomaly detection, and visualizes everything in real time. |

---

## System Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                          HARDWARE LAYER                              │
│                                                                      │
│   ┌──────────────────────────────────────┐                          │
│   │         ESP32 DevKit V1              │                          │
│   │  ┌─────────────┐  ┌──────────────┐  │                          │
│   │  │   DHT22     │  │ Flame Sensor │  │                          │
│   │  │ Temp + Hum  │  │ Digital+ADC  │  │                          │
│   │  └──────┬──────┘  └──────┬───────┘  │                          │
│   │         └────────┬───────┘          │                          │
│   │           SensorManager             │                          │
│   │           MessageBuffer (ring)      │                          │
│   └──────────────────┬─────────────────┘                          │
│                  WiFi / MQTT                                         │
└──────────────────────┼───────────────────────────────────────────────┘
                        │ JSON payload (topic: esp32/sensors)
                        ▼
┌──────────────────────────────────────────────────────────────────────┐
│                     MOSQUITTO MQTT BROKER                            │
└──────────────────────┬───────────────────────────────────────────────┘
                        │
          ┌─────────────┴──────────────────┐
          ▼                                ▼
┌──────────────────┐          ┌────────────────────────────────────────┐
│  MQTT Listener   │          │        DATA PIPELINE  (main.py)        │
│  (background     │          │                                        │
│   thread)        │          │  1. Extract  → Excel / PDF / Images    │
│                  │          │  2. Normalize → kWh                    │
│  Enrichment:     │          │  3. Delta     → per-period values      │
│  • anomaly flags │          │  4. CO₂       → kg per source          │
│  • z-score       │          │  5. Anomalies → IsolationForest + σ    │
│  • CO₂ window    │          │  6. Save      → energy_consolidated.csv│
│                  │          └────────────────────┬───────────────────┘
│  → live_sensors  │                               │
│  → live_enriched │◄──────────────────────────────┘
└─────────┬────────┘
          │
          ▼
┌──────────────────────────────────────────────────────────────────────┐
│              STREAMLIT DASHBOARD  (src/dashboard/app.py)             │
│                                                                      │
│   ┌─────────────────┐  ┌──────────────────┐  ┌──────────────────┐  │
│   │  Energy Charts  │  │  CO₂ Emissions   │  │  Live IoT Feed   │  │
│   │  (Plotly)       │  │  (Plotly)        │  │  auto-refresh 2s │  │
│   └─────────────────┘  └──────────────────┘  └──────────────────┘  │
│                     http://localhost:8501                            │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Part 1 — ESP32 Firmware

### Hardware

| Component | Pin | Notes |
|-----------|-----|-------|
| ESP32 DoIt DevKit V1 | — | Main MCU |
| DHT22 | GPIO 4 | Temperature (°C) + Humidity (%) |
| Flame Sensor (digital) | GPIO 5 | `1` = flame detected |
| Flame Sensor (analog) | GPIO 34 | 12-bit ADC, raw 0–4095 |

### Features

- **Plugin sensor architecture** — `SensorBase` abstract class; adding a new sensor means creating one header + one `.cpp`, registering it in `setup()`. Nothing else changes.
- **Structured JSON payload** — each sensor writes its data as a nested object with `value` + `unit` fields into a shared `JsonDocument`.
- **Offline ring-buffer** — up to 20 readings are queued in a circular FIFO when WiFi or MQTT is down; they are replayed in order (with original timestamps) as soon as the connection is restored.
- **Event-driven WiFi monitoring** — uses `WiFi.onEvent()` instead of polling `WiFi.status()` for instant disconnect detection (especially when APs disappear without sending a DEAUTH frame).
- **Aggressive keepalive** — MQTT keepalive set to 4 s, socket timeout to 2 s, so dead brokers are detected within one keepalive cycle instead of minutes.
- **Data validation** — range and NaN checks on every reading; out-of-range values are dropped and logged before publishing.

### MQTT Payload Schema

```json
{
  "timestamp": 123456,
  "device_id": "ESP32_SENSOR_DEVICE",
  "sensors": {
    "temperature": { "value": 24.5, "unit": "C" },
    "humidity":    { "value": 58.2, "unit": "%" },
    "flame_digital": { "value": 0,    "unit": "bool" },
    "flame_analog":  { "value": 3891, "unit": "raw" }
  }
}
```

### Build & Flash

```bash
# Prerequisites: PlatformIO Core or VS Code PlatformIO extension

cd part1

pio run                    # compile only
pio run --target upload    # compile + flash (COM5 by default)
pio device monitor         # serial monitor @ 115200 baud
```

> **Note:** edit `include/config.h` to set your WiFi credentials, MQTT broker IP, and pin assignments before flashing.

---

## Part 2 — Data Pipeline & Dashboard

### Pipeline Steps

| Step | Module | What it does |
|------|--------|--------------|
| **Extract Excel** | `src/extraction/extract_excel.py` | Parses BILAN TOTAL sheets from `.xlsx` reports |
| **Extract PDF** | `src/extraction/extract_pdf.py` | Text + table extraction from PDF invoices (pdfplumber) |
| **Extract Images** | `src/extraction/extract_image.py` | OCR on scanned meter photos (Tesseract / Gemini Vision) |
| **Normalize → kWh** | `src/normalization/normalize.py` | Unit-aware conversion; non-energy rows (°C, A, V) are preserved untouched |
| **Delta conversion** | `src/emissions/co2.py` | Cumulative meter indices → per-period consumption (odometer logic) |
| **CO₂ emissions** | `src/emissions/co2.py` | Source-aware factors: grid electricity (0.468 kg/kWh), natural gas (0.202 kg/kWh), reactive energy (0 kg/kWh) |
| **Anomaly detection** | `src/anomalies/detect.py` | Per-measure grouping; IsolationForest + Z-score + jump detection |
| **MQTT listener** | `src/iot/mqtt_listener.py` | Subscribes to broker, enriches payloads with anomaly flags + CO₂ window estimate, writes JSON Lines |
| **Dashboard** | `src/dashboard/app.py` | Streamlit app; auto-refreshes every 2 s for the live IoT tab |

### Key Design Decisions

**Per-measure anomaly detection.** Mixing kWh, °C, and A into a single statistical model produces meaningless results. Every detector runs inside a `measure`-level group.

**Quantity-type aware normalization.** Only rows tagged as `energy` are converted to kWh. Temperatures, currents, and voltages keep their native units — they feed the dashboard but are never silently summed with energy values.

**Cumulative → delta conversion.** Meter readings are cumulative indices (like a car odometer). CO₂ is always computed on the per-period delta, never on the raw index.

**Source-aware CO₂ factors.** Tunisian grid electricity (0.468 kg/kWh) ≠ natural gas (0.202 kg/kWh) ≠ reactive energy (0 kg/kWh, no direct CO₂).

---

## Quick Start

### Option A — Docker (recommended, zero dependencies)

```bash
cd part2
docker compose up --build
```

This starts four containers:
1. **mosquitto** — MQTT broker on port 1883
2. **pipeline** — runs `python main.py` once, builds the consolidated CSV
3. **esp-simulator** — publishes simulated sensor data to MQTT
4. **dashboard** — Streamlit on [http://localhost:8501](http://localhost:8501)

### Option B — Local Python

```bash
cd part2

# 1. Create & activate virtual environment
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux/macOS

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env
# edit .env: set MQTT_BROKER, CO2_FACTOR_KG_PER_KWH, GEMINI_API_KEY (optional)

# 4. Run the pipeline
python main.py

# 5. Launch the dashboard
streamlit run src/dashboard/app.py
```

Open [http://localhost:8501](http://localhost:8501).

### Firmware Setup (Part 1)

```bash
cd part1

# Edit WiFi + MQTT settings
# include/config.h → WIFI_SSID, WIFI_PASSWORD, MQTT_SERVER

pio run --target upload
pio device monitor
```

---

## Configuration

Copy `part2/.env.example` to `part2/.env` and adjust:

```env
# Data paths
RAW_DATA_DIR=./data/raw
PROCESSED_DATA_DIR=./data/processed

# CO₂ factors
CO2_FACTOR_KG_PER_KWH=0.468          # Tunisia grid average
GAS_PCI_KWH_PER_NM3=10.562           # 9.082 thermie/Nm³ × 1.163 kWh/thermie

# MQTT broker
MQTT_BROKER=localhost
MQTT_PORT=1883
MQTT_TOPICS=esp32/sensors,retech/energy/sensors

# OCR backend
TESSERACT_CMD=/usr/bin/tesseract
GEMINI_API_KEY=<your-key>             # optional — enables AI-powered OCR
GEMINI_MODEL=gemini-2.0-flash
```

---

## Project Structure

```
NRTF/
├── part1/                          # ESP32 firmware (PlatformIO)
│   ├── platformio.ini              # Board config, library dependencies
│   ├── include/
│   │   ├── config.h                # WiFi, MQTT, pins, timing (edit before flash)
│   │   ├── sensor_manager.h
│   │   ├── message_buffer.h
│   │   └── sensors/
│   │       ├── sensor_base.h       # Abstract sensor interface
│   │       ├── dht22_sensor.h
│   │       └── flame_sensor.h
│   └── src/
│       ├── main.cpp                # Setup + loop, WiFi/MQTT management
│       ├── sensor_manager.cpp
│       ├── message_buffer.cpp      # Ring-buffer for offline replay
│       └── sensors/
│           ├── dht22_sensor.cpp
│           └── flame_sensor.cpp
│
└── part2/                          # Python pipeline + dashboard
    ├── main.py                     # Pipeline orchestrator
    ├── requirements.txt
    ├── Dockerfile
    ├── docker-compose.yml          # 4-service stack
    ├── .env.example
    ├── data/
    │   ├── raw/                    # Input: xlsx, pdf, images
    │   ├── processed/              # Output: energy_consolidated.csv
    │   └── iot/                    # Live sensor logs (JSON Lines)
    └── src/
        ├── extraction/             # Excel / PDF / Image extractors
        ├── normalization/          # Unit conversion to kWh
        ├── emissions/              # CO₂ computation + delta conversion
        ├── anomalies/              # IsolationForest + Z-score + jump detector
        ├── iot/                    # MQTT listener + ESP32 simulator
        ├── dashboard/              # Streamlit app (app.py)
        └── utils/                  # Config loader, helpers
```

---

## Tech Stack

### Part 1 — Embedded Firmware

| Tool / Library | Version | Role |
|----------------|---------|------|
| [PlatformIO](https://platformio.org/) | latest | Build system, dependency manager |
| Arduino framework | espressif32 | HAL for ESP32 |
| [PubSubClient](https://github.com/knolleary/pubsubclient) | 2.8.0 | MQTT client |
| [ArduinoJson](https://arduinojson.org/) | 7.0.4 | JSON serialization |
| [DHT sensor library](https://github.com/adafruit/DHT-sensor-library) | 1.4.4 | DHT22 driver |
| [Adafruit Unified Sensor](https://github.com/adafruit/Adafruit_Sensor) | 1.1.14 | Sensor abstraction layer |
| C++11 | — | `std::vector`, smart design patterns |

### Part 2 — Python Pipeline & Dashboard

| Tool / Library | Version | Role |
|----------------|---------|------|
| [Python](https://python.org) | 3.11+ | Runtime |
| [pandas](https://pandas.pydata.org/) | 2.2.2 | Tabular data manipulation |
| [NumPy](https://numpy.org/) | 1.26.4 | Numerical operations |
| [scikit-learn](https://scikit-learn.org/) | 1.5.2 | IsolationForest anomaly detection |
| [SciPy](https://scipy.org/) | 1.14.1 | Z-score statistical tests |
| [pdfplumber](https://github.com/jsvine/pdfplumber) | 0.11.4 | PDF text + table extraction |
| [pytesseract](https://github.com/madmaze/pytesseract) | 0.3.13 | OCR on scanned images |
| [OpenCV](https://opencv.org/) | 4.10.0 | Image preprocessing for OCR |
| [Pillow](https://pillow.readthedocs.io/) | 10.4.0 | Image I/O |
| [google-generativeai](https://ai.google.dev/) | ≥0.8.0 | Gemini Vision OCR (optional) |
| [paho-mqtt](https://www.eclipse.org/paho/) | 2.1.0 | MQTT subscriber |
| [Streamlit](https://streamlit.io/) | 1.39.0 | Interactive dashboard |
| [Plotly](https://plotly.com/python/) | 5.24.1 | Interactive charts |
| [streamlit-autorefresh](https://github.com/kmcgrady/streamlit-autorefresh) | 1.0.1 | 2-second live refresh |
| [openpyxl](https://openpyxl.readthedocs.io/) | 3.1.5 | Excel `.xlsx` reader/writer |
| [loguru](https://loguru.readthedocs.io/) | 0.7.2 | Structured logging |
| [pydantic](https://docs.pydantic.dev/) | 2.9.2 | Data validation |
| [python-dotenv](https://github.com/theskumar/python-dotenv) | 1.0.1 | `.env` config loading |

### Infrastructure

| Tool | Role |
|------|------|
| [Eclipse Mosquitto 2](https://mosquitto.org/) | MQTT broker |
| [Docker + Compose](https://docker.com) | Containerized deployment |

---

## Data Flow

```
Raw sources                   Pipeline                        Outputs
─────────────────────────────────────────────────────────────────────────────
Excel reports (.xlsx)  ──┐
PDF invoices (.pdf)    ──┤──► extract ──► normalize ──► delta ──► CO₂  ──► energy_consolidated.csv
Scanned images (.jpeg) ──┘                                  └──► anomaly ──► is_anomaly, reason

ESP32 (live)           ──► MQTT ──► mqtt_listener ──► live_enriched.json ──┐
ESP32 simulator        ──► MQTT ──────────────────────────────────────────┘
                                                                            │
                                                                            ▼
                                                              Streamlit dashboard
                                                              ├── Energy over time
                                                              ├── CO₂ breakdown
                                                              ├── Anomaly timeline
                                                              └── Live IoT feed (2s refresh)
```

---

## License

Hackathon project — INSAT, University of Carthage. Free to use and modify.
