# Re·Tech Fusion — Energy Data Pipeline

> Hackathon project (INSAT). End-to-end pipeline that ingests heterogeneous
> energy data (Excel reports, PDF invoices, scanned images, IoT sensors),
> normalizes it to kWh, computes CO₂ emissions, detects anomalies, and
> exposes everything in an interactive dashboard.

---

## Quick start

### Option A — Docker (recommended)

```bash
docker compose up --build
```

Then open **http://localhost:8501** in your browser.

That's it. The first service runs the pipeline (extraction → normalization →
CO₂ → anomalies), the second serves the Streamlit dashboard.

The repository now also includes a standalone ESP32 firmware module in
`part1/` for publishing MQTT sensor data into the same pipeline.

```bash
cd part1
pio run
```

### Option B — Local Python

```bash
pip install -r requirements.txt
python main.py                          # build the consolidated CSV
streamlit run src/dashboard/app.py      # launch the dashboard
```

---

## Pipeline architecture

```
 data/raw/                                  src/
 ├── *.xlsx (BILAN TOTAL)  ───┐         ┌── extraction/
 ├── *.pdf (invoices)         ├──>      ├── normalization/   ──>  data/processed/
 ├── *.jpeg (scans)           │         ├── emissions/             energy_consolidated.csv
 └── (IoT sensors stream)  ───┘         ├── anomalies/                    │
                                        └── iot/                          │
                                                                          ▼
                                                              src/dashboard/app.py
                                                              (Streamlit + Plotly)
```

| Step              | Module                              | Output column(s)                  |
|-------------------|-------------------------------------|-----------------------------------|
| Extract Excel     | `src/extraction/extract_excel.py`   | source, timestamp, value, unit    |
| Extract PDF       | `src/extraction/extract_pdf.py`     | (skeleton — to be completed)      |
| Extract Images    | `src/extraction/extract_image.py`   | classified by document type       |
| Normalize → kWh   | `src/normalization/normalize.py`    | value_kwh, quantity_type          |
| Compute deltas    | `src/emissions/co2.py`              | delta_kwh                         |
| CO₂ emissions     | `src/emissions/co2.py`              | co2_kg, co2_source, co2_factor    |
| Detect anomalies  | `src/anomalies/detect.py`           | is_anomaly, anomaly_reason        |

---

## Key design decisions

**Per-measure detection, not global.** Mixing temperatures, voltages and kWh
into a single statistical model produces nonsense. The anomaly detector
groups by `measure` and runs each detector inside the group.

**`quantity_type` aware normalization.** Only rows tagged as `energy` are
converted to kWh. Temperatures, currents, percentages keep their native
units — they're preserved for the dashboard but never silently summed
with energy values.

**Cumulative → delta conversion.** Meter readings are cumulative indices
(like a car odometer). CO₂ is computed on the per-period delta, never on
the cumulative index — otherwise you'd get tons of CO₂ per minute.

**Source-aware CO₂ factors.** Natural gas (0.202 kg/kWh) is not the
same as Tunisian grid electricity (0.468 kg/kWh). Reactive energy
(kVARh) has a 0 factor — it doesn't directly produce CO₂.

---

## Configuration

Copy `.env.example` to `.env` and tune to your context:

```env
CO2_FACTOR_KG_PER_KWH=0.468       # Tunisia grid average
GAS_PCI_KWH_PER_NM3=10.562        # 9.082 thermie/Nm3 × 1.163 kWh/thermie
```

---

## Project layout

```
retech_fusion/
├── main.py                  # Pipeline orchestrator
├── requirements.txt
├── Dockerfile               # Single image, used by both services
├── docker-compose.yml       # Pipeline + dashboard services
├── .env.example
│
├── data/
│   ├── raw/                 # Input files (Excel / PDF / images)
│   ├── processed/           # Pipeline output (consolidated CSV)
│   └── iot/                 # IoT sensor logs
│
└── src/
    ├── extraction/          # One file per input format
    ├── normalization/       # Unit conversion to kWh
    ├── emissions/           # CO2 computation
    ├── anomalies/           # Z-score + IsolationForest + jump detection
    ├── iot/                 # MQTT / CSV log loader
    ├── dashboard/           # Streamlit app
    └── utils/               # Config loader
```

---

## License

Hackathon project. Free to use and modify.