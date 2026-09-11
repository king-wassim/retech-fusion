"""app.py — Streamlit dashboard for the Re·Tech Fusion energy pipeline.

Run from the project root:
    streamlit run src/dashboard/app.py
"""
import json
import os
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# Streamlit page config must be the first Streamlit command
st.set_page_config(
    page_title="Re·Tech Fusion — Live Monitoring Hub",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

from streamlit_autorefresh import st_autorefresh

# ---------------------------------------------------------------------------
# Path setup so we can import from src.* whether run via streamlit run or python
# ---------------------------------------------------------------------------
import sys
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.utils.config import PROCESSED_DATA_DIR  # noqa: E402

# Boot the MQTT listener thread once per Streamlit process
try:
    from src.iot.mqtt_listener import start_listener_thread, ENRICHED_LOG, RAW_LOG
    start_listener_thread()
except Exception as _e:
    ENRICHED_LOG = Path(__file__).resolve().parents[2] / "data" / "iot" / "live_enriched.json"
    RAW_LOG = Path(__file__).resolve().parents[2] / "data" / "iot" / "live_sensors.json"

IOT_DIR = ENRICHED_LOG.parent

# Auto-refresh every 2 seconds for live updates
st_autorefresh(interval=2000, key="live_dashboard_refresh")

# Modern dark theme — inspired by high-tech monitoring dashboards
CSS = """
<style>
:root {
    --bg-deep:   #0a0e14;
    --bg-panel:  #11161f;
    --bg-card:   #161c27;
    --bg-card-2:  #1a2130;
    --border:    #1f2a3a;
    --text:      #e6edf3;
    --text-dim:  #7d8a9c;
    --accent-green: #00d4aa;
    --accent-amber: #ffb000;
    --accent-red:   #ff4757;
    --accent-cyan:  #00b8d4;
    --accent-purple: #9b59b6;
    --font-sans: 'Segoe UI Variable', 'Segoe UI', 'Inter', sans-serif;
    --font-mono: 'JetBrains Mono', 'SFMono-Regular', Consolas, monospace;
}

.stApp {
    background:
        radial-gradient(circle at top left, rgba(0, 212, 170, 0.12), transparent 28%),
        radial-gradient(circle at top right, rgba(0, 184, 212, 0.08), transparent 22%),
        linear-gradient(135deg, #090d13 0%, #0d121a 44%, #11161f 100%) fixed;
    color: var(--text);
    font-family: var(--font-sans);
}

header[data-testid="stHeader"] { background: transparent; }
.block-container { padding-top: 2rem; padding-bottom: 4rem; max-width: 1400px; }

/* Reduce the default chrome noise */
div[data-testid="stToolbar"] { visibility: hidden; height: 0; }
div[data-testid="stDecoration"] { display: none; }

/* Hero title */
.dashboard-title {
    font-family: var(--font-sans);
    font-weight: 700;
    font-size: 2.8rem;
    letter-spacing: -0.02em;
    color: var(--text);
    margin: 0.5rem 0;
}

.dashboard-title .highlight {
    color: var(--accent-cyan);
    background: linear-gradient(90deg, var(--accent-cyan), var(--accent-green));
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
}

.dashboard-subtitle {
    color: var(--accent-green);
    font-family: var(--font-mono);
    font-size: 0.8rem;
    letter-spacing: .15em;
    text-transform: uppercase;
    margin-bottom: 1.5rem;
}

.status-live {
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    color: var(--accent-green);
    font-weight: 600;
    font-size: 0.85rem;
    background: rgba(0, 212, 170, 0.08);
    border: 1px solid rgba(0, 212, 170, 0.22);
    border-radius: 999px;
    padding: 0.65rem 0.9rem;
}

.status-dot {
    width: 8px;
    height: 8px;
    background: var(--accent-green);
    border-radius: 50%;
    animation: pulse 2s infinite;
}

@keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.5; }
}

/* KPI cards grid */
.kpi-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
    gap: 1.2rem;
    margin-bottom: 2rem;
}

.kpi-card {
    background: linear-gradient(135deg, rgba(22, 28, 39, 0.96) 0%, rgba(26, 33, 48, 0.88) 100%);
    border: 1.5px solid var(--border);
    border-radius: 18px;
    padding: 1.5rem 1.45rem 1.35rem;
    position: relative;
    overflow: hidden;
    transition: all 0.3s ease;
    box-shadow: 0 18px 40px rgba(0, 0, 0, 0.18);
}

.kpi-card:hover {
    border-color: rgba(0, 212, 170, 0.55);
    transform: translateY(-3px);
    box-shadow: 0 22px 48px rgba(0, 0, 0, 0.24);
}

.kpi-card::before {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    width: 100%;
    height: 3px;
    background: var(--accent-green);
}

.kpi-card.energy::before { background: var(--accent-green); }
.kpi-card.gas::before { background: var(--accent-amber); }
.kpi-card.co2::before { background: var(--accent-red); }
.kpi-card.sensors::before { background: var(--accent-cyan); }

.kpi-label {
    color: var(--text-dim);
    font-family: var(--font-mono);
    font-size: 0.72rem;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    margin-bottom: 0.8rem;
    font-weight: 600;
}

.kpi-value {
    font-family: var(--font-sans);
    font-size: 2.2rem;
    font-weight: 700;
    color: var(--text);
    line-height: 1;
    margin-bottom: 0.3rem;
    display: flex;
    align-items: baseline;
    gap: 0.45rem;
    flex-wrap: wrap;
}

.kpi-unit {
    color: var(--text-dim);
    font-family: var(--font-mono);
    font-size: 0.82rem;
    letter-spacing: 0.08em;
    text-transform: uppercase;
}

.kpi-change {
    font-family: var(--font-mono);
    font-size: 0.74rem;
    color: var(--accent-green);
    margin-top: 0.5rem;
}

.kpi-change.negative {
    color: var(--accent-amber);
}

/* Section headers */
.section-header {
    font-family: var(--font-mono);
    font-size: 0.95rem;
    letter-spacing: 0.15em;
    text-transform: uppercase;
    color: var(--accent-green);
    border-left: 3px solid var(--accent-green);
    padding-left: 0.8rem;
    margin: 2.5rem 0 1.5rem 0;
    font-weight: 600;
}

.section-card {
    background: linear-gradient(180deg, rgba(17, 22, 31, 0.92) 0%, rgba(12, 16, 23, 0.92) 100%);
    border: 1px solid rgba(31, 42, 58, 0.9);
    border-radius: 20px;
    padding: 1rem;
    box-shadow: 0 18px 48px rgba(0, 0, 0, 0.22);
}

.soft-card {
    background: linear-gradient(135deg, rgba(22, 28, 39, 0.96) 0%, rgba(17, 22, 31, 0.92) 100%);
    border: 1px solid rgba(31, 42, 58, 0.9);
    border-radius: 18px;
    padding: 1rem 1.1rem;
}

/* Tabs */
.stTabs [data-baseweb="tab-list"] {
    gap: 8px;
    border-bottom: 1px solid var(--border);
}

.stTabs [data-baseweb="tab"] {
    background: transparent;
    color: var(--text-dim);
    border: 1px solid var(--border);
    border-radius: 8px 8px 0 0;
    font-family: var(--font-mono);
    font-size: 0.8rem;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    font-weight: 600;
    padding: 0.8rem 1.2rem;
    transition: all 0.2s;
}

.stTabs [aria-selected="true"] {
    background: var(--bg-card);
    color: var(--accent-cyan);
    border-color: var(--accent-cyan);
}

/* Sidebar */
section[data-testid="stSidebar"] {
    background:
        linear-gradient(180deg, rgba(17, 22, 31, 0.98) 0%, rgba(11, 15, 22, 0.98) 100%);
    border-right: 1px solid rgba(31, 42, 58, 0.8);
    box-shadow: 18px 0 48px rgba(0, 0, 0, 0.2);
    padding-top: 0.5rem;
}

section[data-testid="stSidebar"] h1,
section[data-testid="stSidebar"] h2,
section[data-testid="stSidebar"] h3 {
    font-family: var(--font-mono);
    color: var(--accent-cyan);
    font-size: 0.85rem;
    letter-spacing: 0.15em;
    text-transform: uppercase;
    font-weight: 700;
}

section[data-testid="stSidebar"] .stMarkdown p,
section[data-testid="stSidebar"] label,
section[data-testid="stSidebar"] span {
    font-family: var(--font-sans);
}

section[data-testid="stSidebar"] [data-testid="stVerticalBlock"] {
    gap: 0.25rem;
}

section[data-testid="stSidebar"] hr {
    border-color: rgba(31, 42, 58, 0.85);
}

section[data-testid="stSidebar"] .stButton > button {
    width: 100%;
    background: linear-gradient(135deg, rgba(0, 184, 212, 0.92), rgba(0, 212, 170, 0.92)) !important;
    color: #061017 !important;
    border-radius: 14px !important;
    border: 1px solid rgba(255, 255, 255, 0.08) !important;
    box-shadow: 0 10px 24px rgba(0, 184, 212, 0.18);
}

section[data-testid="stSidebar"] .stButton > button:hover {
    transform: translateY(-1px);
    box-shadow: 0 16px 28px rgba(0, 184, 212, 0.25);
}

section[data-testid="stSidebar"] [data-baseweb="radio"] {
    background: rgba(255, 255, 255, 0.02);
    border: 1px solid rgba(31, 42, 58, 0.9);
    border-radius: 16px;
    padding: 0.35rem 0.4rem;
}

section[data-testid="stSidebar"] [data-baseweb="radio"] > div {
    gap: 0.2rem;
}

section[data-testid="stSidebar"] [role="radio"] {
    border-radius: 12px;
    padding: 0.4rem 0.55rem;
}

section[data-testid="stSidebar"] [data-testid="stCheckbox"] {
    padding: 0.2rem 0;
}

section[data-testid="stSidebar"] [data-baseweb="slider"] {
    padding-top: 0.75rem;
}

section[data-testid="stSidebar"] [data-baseweb="slider"] [role="slider"] {
    background: linear-gradient(135deg, rgba(0, 184, 212, 0.95), rgba(0, 212, 170, 0.95));
    box-shadow: 0 0 0 6px rgba(0, 184, 212, 0.08);
}

section[data-testid="stSidebar"] [data-baseweb="slider"] div[style*="background-color"] {
    border-radius: 999px;
}

section[data-testid="stSidebar"] [data-baseweb="slider"] span {
    font-family: var(--font-mono);
}

section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p {
    color: var(--text);
}

section[data-testid="stSidebar"] .stCaption {
    color: var(--text-dim);
    line-height: 1.4;
}

section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] {
    padding-top: 0.35rem;
}

section[data-testid="stSidebar"] [data-baseweb="select"] > div,
section[data-testid="stSidebar"] [data-baseweb="input"] > div,
section[data-testid="stSidebar"] [data-baseweb="textarea"] > div,
section[data-testid="stSidebar"] [data-baseweb="menu"] {
    background-color: rgba(10, 14, 20, 0.92) !important;
    border-color: rgba(31, 42, 58, 0.95) !important;
}

section[data-testid="stSidebar"] [data-baseweb="select"] {
    border-radius: 14px;
}

section[data-testid="stSidebar"] [data-baseweb="select"] > div {
    border-radius: 14px !important;
    min-height: 44px;
}

section[data-testid="stSidebar"] [data-testid="stMultiSelect"] {
    border-radius: 14px;
}

section[data-testid="stSidebar"] [data-testid="stDateInput"] {
    border-radius: 14px;
}

section[data-testid="stSidebar"] [data-testid="stDateInput"] input {
    background: rgba(10, 14, 20, 0.92) !important;
    color: var(--text) !important;
}

section[data-testid="stSidebar"] [data-baseweb="tag"] {
    background: rgba(0, 184, 212, 0.14) !important;
    color: var(--text) !important;
    border-radius: 999px;
}

/* Dataframes */
[data-testid="stDataFrame"] {
    border: 1px solid var(--border);
    border-radius: 14px;
    background: var(--bg-card);
}

/* Buttons */
.stButton > button {
    background: linear-gradient(135deg, rgba(0, 184, 212, 0.94), rgba(0, 212, 170, 0.94)) !important;
    color: #061017 !important;
    font-weight: 700;
    border-radius: 14px !important;
    text-transform: uppercase;
    font-family: var(--font-mono);
    letter-spacing: 0.11em;
    font-size: 0.8rem;
    transition: all 0.2s;
    border: 1px solid rgba(255, 255, 255, 0.08) !important;
    box-shadow: 0 10px 24px rgba(0, 184, 212, 0.14);
}

.stButton > button:hover {
    background: linear-gradient(135deg, rgba(0, 212, 170, 0.98), rgba(0, 184, 212, 0.98)) !important;
    transform: translateY(-2px);
    box-shadow: 0 14px 28px rgba(0, 184, 212, 0.2);
}

/* Anomaly alert */
.anomaly-alert {
    background: linear-gradient(135deg, rgba(255, 71, 87, 0.12), rgba(255, 176, 0, 0.08));
    border: 1.5px solid rgba(255, 71, 87, 0.7);
    border-radius: 14px;
    padding: 1rem;
    margin: 1rem 0;
    color: var(--accent-red);
    font-family: var(--font-mono);
    font-weight: 600;
}

.footer {
    margin-top: 3rem;
    padding-top: 1.5rem;
    border-top: 1px solid var(--border);
    color: var(--text-dim);
    font-family: var(--font-mono);
    font-size: 0.7rem;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    text-align: center;
}

.metric-chip {
    display: inline-flex;
    align-items: baseline;
    gap: 0.35rem;
    flex-wrap: wrap;
}

.metric-chip .value {
    font-size: 2.1rem;
    font-weight: 700;
    line-height: 1;
    color: var(--text);
}

.metric-chip .unit {
    color: var(--text-dim);
    font-family: var(--font-mono);
    font-size: 0.82rem;
    letter-spacing: 0.08em;
    text-transform: uppercase;
}

.viz-shell {
    background: linear-gradient(180deg, rgba(17, 22, 31, 0.92) 0%, rgba(13, 17, 25, 0.95) 100%);
    border: 1px solid rgba(31, 42, 58, 0.9);
    border-radius: 22px;
    padding: 1.1rem 1.1rem 0.6rem;
    box-shadow: 0 20px 54px rgba(0, 0, 0, 0.22);
    margin-bottom: 1rem;
}

.historical-hero {
    display: grid;
    grid-template-columns: 1.4fr 0.9fr;
    gap: 1rem;
    margin-bottom: 1.25rem;
}

.hero-panel {
    background: linear-gradient(135deg, rgba(22, 28, 39, 0.96) 0%, rgba(17, 22, 31, 0.9) 100%);
    border: 1px solid rgba(31, 42, 58, 0.9);
    border-radius: 20px;
    padding: 1.15rem 1.2rem;
}

.hero-kicker {
    font-family: var(--font-mono);
    font-size: 0.75rem;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    color: var(--accent-cyan);
    margin-bottom: 0.55rem;
}

.hero-title {
    font-family: var(--font-sans);
    font-size: 1.7rem;
    font-weight: 700;
    color: var(--text);
    margin: 0;
}

.hero-copy {
    color: var(--text-dim);
    margin-top: 0.55rem;
    line-height: 1.6;
}

.stat-strip {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 0.85rem;
}

.stat-card {
    background: rgba(10, 14, 20, 0.7);
    border: 1px solid rgba(31, 42, 58, 0.9);
    border-radius: 16px;
    padding: 1rem;
}

.stat-card .label {
    font-family: var(--font-mono);
    font-size: 0.7rem;
    letter-spacing: 0.16em;
    text-transform: uppercase;
    color: var(--text-dim);
}

.stat-card .value {
    display: block;
    margin-top: 0.45rem;
    font-size: 1.55rem;
    font-weight: 700;
    color: var(--text);
}

.stat-card .hint {
    display: block;
    margin-top: 0.25rem;
    color: var(--text-dim);
    font-family: var(--font-mono);
    font-size: 0.72rem;
}

.surface-panel {
    background: linear-gradient(180deg, rgba(17, 22, 31, 0.96) 0%, rgba(13, 17, 25, 0.96) 100%);
    border: 1px solid rgba(31, 42, 58, 0.9);
    border-radius: 20px;
    padding: 1rem;
    margin-bottom: 1rem;
}

.hero-grid {
    display: grid;
    grid-template-columns: 1.2fr 0.8fr;
    gap: 1rem;
    margin-bottom: 1rem;
}

.mini-stat-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 0.8rem;
}

.mini-stat {
    background: rgba(10, 14, 20, 0.58);
    border: 1px solid rgba(31, 42, 58, 0.85);
    border-radius: 16px;
    padding: 0.95rem 1rem;
}

.mini-stat .label {
    display: block;
    font-family: var(--font-mono);
    font-size: 0.7rem;
    letter-spacing: 0.16em;
    text-transform: uppercase;
    color: var(--text-dim);
}

.mini-stat .value {
    display: block;
    margin-top: 0.35rem;
    font-size: 1.55rem;
    font-weight: 700;
    color: var(--text);
}

.mini-stat .hint {
    display: block;
    margin-top: 0.2rem;
    color: var(--text-dim);
    font-family: var(--font-mono);
    font-size: 0.72rem;
}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)

# Plotly theme to match
PLOTLY_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="JetBrains Mono, monospace", color="#e6edf3", size=11),
    xaxis=dict(gridcolor="#1f2a3a", linecolor="#1f2a3a", zerolinecolor="#1f2a3a"),
    yaxis=dict(gridcolor="#1f2a3a", linecolor="#1f2a3a", zerolinecolor="#1f2a3a"),
    margin=dict(l=10, r=10, t=30, b=10),
    legend=dict(font=dict(size=10), bgcolor="rgba(0,0,0,0)"),
    hovermode="x unified",
)

# Toggle during debugging to force a visible sidebar marker
DEBUG_SIDEBAR = True

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------
def _read_jsonl_tail(path: Path, n: int = 500) -> list[dict]:
    """Read last n lines from JSONL file."""
    if not path.exists():
        return []
    try:
        with path.open("r", encoding="utf-8") as f:
            lines = f.readlines()[-n:]
    except OSError:
        return []
    out = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def _coerce_live_timestamp(value, fallback=None):
    if isinstance(value, str):
        parsed = pd.to_datetime(value, utc=True, errors="coerce")
        if not pd.isna(parsed):
            return parsed

    if isinstance(value, (int, float)) and value >= 10_000_000_000:
        parsed = pd.to_datetime(value, unit="ms", utc=True, errors="coerce")
        if not pd.isna(parsed):
            return parsed

    if fallback is not None:
        parsed = pd.to_datetime(fallback, utc=True, errors="coerce")
        if not pd.isna(parsed):
            return parsed

    return pd.NaT


def _normalize_live_record(record: dict) -> dict:
    normalized = dict(record)

    raw_payload = normalized.get("raw_payload")
    if isinstance(raw_payload, dict):
        for key, value in raw_payload.items():
            if key == "sensors" and isinstance(value, dict):
                for sensor_name, sensor_value in value.items():
                    if isinstance(sensor_value, dict) and "value" in sensor_value:
                        normalized.setdefault(sensor_name, sensor_value.get("value"))
                        if "unit" in sensor_value:
                            normalized.setdefault(f"{sensor_name}_unit", sensor_value.get("unit"))
                    else:
                        normalized.setdefault(sensor_name, sensor_value)
            elif isinstance(value, dict) and "value" in value:
                normalized.setdefault(key, value.get("value"))
                if "unit" in value:
                    normalized.setdefault(f"{key}_unit", value.get("unit"))
            else:
                normalized.setdefault(key, value)

    sensors = normalized.get("sensors")
    if isinstance(sensors, dict):
        for sensor_name, sensor_value in sensors.items():
            if isinstance(sensor_value, dict) and "value" in sensor_value:
                normalized.setdefault(sensor_name, sensor_value.get("value"))
                if "unit" in sensor_value:
                    normalized.setdefault(f"{sensor_name}_unit", sensor_value.get("unit"))

    if "temperature_c" not in normalized and "temperature" in normalized:
        normalized["temperature_c"] = normalized.get("temperature")
    if "humidity_pct" not in normalized and "humidity" in normalized:
        normalized["humidity_pct"] = normalized.get("humidity")

    normalized["timestamp"] = _coerce_live_timestamp(
        normalized.get("timestamp"),
        normalized.get("received_at"),
    )
    return normalized


def _get_live_metrics() -> dict:
    """Extract latest metrics from enriched log."""
    msgs = [_normalize_live_record(msg) for msg in _read_jsonl_tail(ENRICHED_LOG, n=100)]
    if not msgs:
        return {
            "timestamp": "—",
            "received_at": "—",
            "mqtt_topic": "—",
            "data_age_seconds": 0.0,
            "power_kw": 0,
            "gas_flow_nm3h": 0,
            "temperature_c": 0,
            "humidity_pct": 0,
            "co2_ppm": 0,
            "voltage_v": 0,
            "current_a": 0,
            "flame_digital": 0,
            "flame_analog": 0,
            "energy_kwh": 0,
            "is_anomaly": False,
            "anomaly_reasons": [],
        }
    
    last = msgs[-1]
    last_timestamp = last.get("timestamp")
    if pd.isna(last_timestamp):
        last_timestamp = pd.Timestamp.now(tz="UTC")
    data_age_seconds = 0.0
    try:
        data_age_seconds = max((pd.Timestamp.now(tz="UTC") - last_timestamp).total_seconds(), 0.0)
    except Exception:
        pass

    return {
        "timestamp": last_timestamp.isoformat() if not pd.isna(last_timestamp) else "—",
        "received_at": last.get("received_at", "—"),
        "mqtt_topic": last.get("mqtt_topic", "—"),
        "data_age_seconds": float(data_age_seconds),
        "power_kw": float(last.get("power_kw", 0) or 0),
        "gas_flow_nm3h": float(last.get("gas_flow_nm3h", 0) or 0),
        "temperature_c": float(last.get("temperature_c", 0) or 0),
        "humidity_pct": float(last.get("humidity_pct", 0) or 0),
        "co2_ppm": float(last.get("co2_ppm", 0) or 0),
        "voltage_v": float(last.get("voltage_v", 0) or 0),
        "current_a": float(last.get("current_a", 0) or 0),
        "flame_digital": last.get("flame_digital", 0),
        "flame_analog": float(last.get("flame_analog", 0) or 0),
        "energy_kwh": float(last.get("energy_kwh", 0) or 0),
        "is_anomaly": bool(last.get("is_anomaly", False)),
        "anomaly_reasons": last.get("anomaly_reasons", []),
        "window_kwh": float(last.get("window_kwh", 0)),
        "window_co2_kg": float(last.get("window_co2_kg", 0)),
    }


def _get_timeseries_data(minutes: int = 60) -> pd.DataFrame:
    """Get last N minutes of data as DataFrame."""
    msgs = [_normalize_live_record(msg) for msg in _read_jsonl_tail(ENRICHED_LOG, n=5000)]
    if not msgs:
        return pd.DataFrame()
    
    df = pd.DataFrame(msgs)
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce", utc=True)
        # Filter to last N minutes
        now = pd.Timestamp.now(tz="UTC")
        cutoff = now - timedelta(minutes=minutes)
        df = df[df["timestamp"] >= cutoff]
    
    return df.sort_values("timestamp")


def _get_energy_stats(df: pd.DataFrame) -> dict:
    """Calculate aggregated energy statistics."""
    if df.empty:
        return {"total_kwh": 0, "total_co2_kg": 0, "avg_power_kw": 0, "count": 0}
    
    total_kwh = df["window_kwh"].sum() if "window_kwh" in df.columns else 0
    total_co2_kg = df["window_co2_kg"].sum() if "window_co2_kg" in df.columns else 0
    avg_power = df["power_kw"].mean() if "power_kw" in df.columns else 0
    
    return {
        "total_kwh": float(total_kwh),
        "total_co2_kg": float(total_co2_kg),
        "avg_power_kw": float(avg_power),
        "count": len(df),
    }


@st.cache_data(show_spinner=False, ttl=300)
def load_historical_data() -> pd.DataFrame:
    """Load historical processed data."""
    path = Path(PROCESSED_DATA_DIR) / "energy_consolidated.csv"
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path, parse_dates=["timestamp"], low_memory=False)
    return df


# ---------------------------------------------------------------------------
# HEADER
# ---------------------------------------------------------------------------
st.markdown(
    """
    <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 1.5rem;">
        <div>
            <h1 class="dashboard-title">
                Re·Tech <span class="highlight">Fusion</span>
            </h1>
            <div class="dashboard-subtitle">
                🌍 Live Monitoring Hub · Streaming Data (Latency: 2-3s)
            </div>
        </div>
        <div class="status-live">
            <span class="status-dot"></span> LIVE FEED
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Sidebar controls
# ---------------------------------------------------------------------------
with st.sidebar:
    # Debug marker: visible box to confirm sidebar renders (toggle via DEBUG_SIDEBAR)
    if DEBUG_SIDEBAR:
        st.markdown(
            """
            <div style='background:#ffffff;color:#061017;padding:0.5rem;border-radius:8px;margin-bottom:0.75rem;'>
                <strong>SIDEBAR DEBUG:</strong> content rendered
            </div>
            """,
            unsafe_allow_html=True,
        )
    st.markdown(
        """
        <div class='hero-panel' style='margin-bottom:1rem;'>
            <div class='hero-kicker'>Control Deck</div>
            <div class='hero-title' style='font-size:1.15rem;'>Live Ops Console</div>
            <div class='hero-copy' style='font-size:0.9rem;'>Realtime filters, export actions, and signal health in one place.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown("### 📊 DASHBOARD MODE")
    mode = st.radio(
        "View Mode",
        ["🔴 LIVE (Real-time)", "📈 Historical"],
        label_visibility="collapsed",
        key="mode_select"
    )
    
    st.markdown("---")
    st.markdown("### 🎛️ FILTERS")
    
    # Time range for data display
    time_range = st.select_slider(
        "Data Window",
        options=[5, 15, 30, 60, 120, 240],
        value=60,
        format_func=lambda x: f"{x} min"
    )
    
    st.markdown("---")
    st.markdown("### ⚡ METRICS")
    show_energy = st.checkbox("Energy (Power)", value=True)
    show_gas = st.checkbox("Natural Gas Flow", value=True)
    show_temp = st.checkbox("Temperature", value=True)
    show_flame = st.checkbox("Flame Sensors", value=True)
    show_co2 = st.checkbox("CO₂ PPM", value=False)
    
    st.markdown("---")
    st.markdown("### 📋 EXPORT")
    # Prepare last-hour export payloads once per render to avoid dynamic endpoint creation
    df_export = _get_timeseries_data(minutes=60)
    if df_export.empty:
        st.caption("No recent data available for export")
        # Render disabled download buttons to avoid runtime 404s caused by creating buttons only on click
        st.download_button(
            "📥 Download CSV",
            data=b"",
            file_name=f"retech_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv",
            disabled=True,
        )
        st.download_button(
            "📤 Download JSON",
            data="",
            file_name=f"retech_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
            mime="application/json",
            disabled=True,
        )
    else:
        csv = df_export.to_csv(index=False).encode("utf-8")
        json_str = df_export.to_json(orient="records", date_format="iso")
        st.download_button(
            "📥 Download CSV",
            data=csv,
            file_name=f"retech_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv",
        )
        st.download_button(
            "📤 Download JSON",
            data=json_str,
            file_name=f"retech_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
            mime="application/json",
        )
    
    st.markdown("---")
    st.markdown("### ℹ️ INFO")
    st.caption("🔋 Énergie Grid: 0.468 kg CO₂/kWh")
    st.caption("🔥 Gaz Naturel: 0.202 kg CO₂/kWh")
    st.caption("⏱️ Update: 2-3s")


# ---------------------------------------------------------------------------
# MAIN CONTENT - OVERVIEW TAB (LIVE)
# ---------------------------------------------------------------------------
if "🔴 LIVE" in mode:
    # Get latest metrics
    metrics = _get_live_metrics()
    ts_df = _get_timeseries_data(minutes=time_range)
    stats = _get_energy_stats(ts_df)
    is_board_topic = "esp32" in str(metrics.get("mqtt_topic", "")).lower() or "flame_analog" in ts_df.columns

    st.caption(
        f"Source: {metrics.get('mqtt_topic', '—')} · Last packet: {metrics.get('timestamp', '—')} · Age: {metrics.get('data_age_seconds', 0.0):.1f}s"
    )
    
    # ===== KPI ROW =====
    st.markdown("<h2 class='section-header'>⚡ LIVE METRICS</h2>", unsafe_allow_html=True)
    
    if is_board_topic:
        kpi1, kpi2, kpi3, kpi4 = st.columns(4)

        with kpi1:
            st.markdown(
                f"""
                <div class='kpi-card sensors'>
                    <div class='kpi-label'>🌡️ TEMPERATURE</div>
                    <div class='kpi-value'><span class='metric-chip'><span class='value'>{metrics['temperature_c']:.1f}</span><span class='unit'>°C</span></span></div>
                    <div class='kpi-change'>ESP32 live feed</div>
                </div>
                """,
                unsafe_allow_html=True
            )

        with kpi2:
            st.markdown(
                f"""
                <div class='kpi-card energy'>
                    <div class='kpi-label'>💧 HUMIDITY</div>
                    <div class='kpi-value'><span class='metric-chip'><span class='value'>{metrics['humidity_pct']:.1f}</span><span class='unit'>%</span></span></div>
                    <div class='kpi-change'>Relative humidity</div>
                </div>
                """,
                unsafe_allow_html=True
            )

        with kpi3:
            flame_state = "ALERT" if bool(metrics.get("flame_digital")) else "SAFE"
            st.markdown(
                f"""
                <div class='kpi-card co2'>
                    <div class='kpi-label'>🔥 FLAME STATE</div>
                    <div class='kpi-value'><span class='metric-chip'><span class='value'>{flame_state}</span><span class='unit'>digital</span></span></div>
                    <div class='kpi-change'>Digital input</div>
                </div>
                """,
                unsafe_allow_html=True
            )

        with kpi4:
            st.markdown(
                f"""
                <div class='kpi-card gas'>
                    <div class='kpi-label'>🎛️ FLAME ANALOG</div>
                    <div class='kpi-value'><span class='metric-chip'><span class='value'>{metrics['flame_analog']:.0f}</span><span class='unit'>raw</span></span></div>
                    <div class='kpi-change'>{metrics.get('mqtt_topic', '—')}</div>
                </div>
                """,
                unsafe_allow_html=True
            )
    else:
        kpi1, kpi2, kpi3, kpi4 = st.columns(4)

        with kpi1:
            st.markdown(
                f"""
                <div class='kpi-card energy'>
                    <div class='kpi-label'>📊 TOTAL ENERGY</div>
                    <div class='kpi-value'><span class='metric-chip'><span class='value'>{stats['total_kwh']:.2f}</span><span class='unit'>kWh</span></span></div>
                    <div class='kpi-change'>+{stats['avg_power_kw']:.1f} kW avg</div>
                </div>
                """,
                unsafe_allow_html=True
            )

        with kpi2:
            st.markdown(
                f"""
                <div class='kpi-card gas'>
                    <div class='kpi-label'>🔥 NATURAL GAS</div>
                    <div class='kpi-value'><span class='metric-chip'><span class='value'>{metrics['gas_flow_nm3h']:.1f}</span><span class='unit'>Nm³/h</span></span></div>
                    <div class='kpi-change'>Flow rate</div>
                </div>
                """,
                unsafe_allow_html=True
            )

        with kpi3:
            st.markdown(
                f"""
                <div class='kpi-card co2'>
                    <div class='kpi-label'>☁️ CO₂ INTENSITY</div>
                    <div class='kpi-value'><span class='metric-chip'><span class='value'>{metrics['co2_ppm']:.0f}</span><span class='unit'>ppm</span></span></div>
                    <div class='kpi-change'>{stats['total_co2_kg']:.3f} kg</div>
                </div>
                """,
                unsafe_allow_html=True
            )

        with kpi4:
            sensor_count = ts_df["device_id"].nunique() if "device_id" in ts_df.columns and not ts_df.empty else 1
            anomaly_count = len(ts_df[ts_df["is_anomaly"].fillna(False)]) if "is_anomaly" in ts_df.columns and not ts_df.empty else 0
            st.markdown(
                f"""
                <div class='kpi-card sensors'>
                    <div class='kpi-label'>🎛️ ACTIVE SENSORS</div>
                    <div class='kpi-value'><span class='metric-chip'><span class='value'>{sensor_count:,}</span><span class='unit'>nodes</span></span></div>
                    <div class='kpi-change'>⚠ {anomaly_count} anomalies</div>
                </div>
                """,
                unsafe_allow_html=True
            )
    
    # Anomaly alert if present
    if metrics["is_anomaly"]:
        st.markdown(
            f"""
            <div class='anomaly-alert'>
            ⚠ ANOMALY DETECTED: {', '.join(metrics['anomaly_reasons']) or 'Unknown'}
            </div>
            """,
            unsafe_allow_html=True
        )
    
    # ===== TIME SERIES WAVEFORMS =====
    st.markdown("<h2 class='section-header'>📈 LIVE SYSTEM WAVEFORMS</h2>", unsafe_allow_html=True)
    
    if not ts_df.empty:
        col1, col2 = st.columns(2)
        
        with col1:
            if show_energy and "power_kw" in ts_df.columns:
                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    x=ts_df["timestamp"],
                    y=ts_df["power_kw"],
                    mode="lines",
                    name="Power (kW)",
                    line=dict(color="#ffb000", width=2),
                    fill="tozeroy",
                    fillcolor="rgba(255, 176, 0, 0.15)"
                ))
                fig.update_layout(
                    **PLOTLY_LAYOUT,
                    title="⚡ ACTIVE LOAD",
                    height=300,
                    yaxis_title="Power (kW)",
                )
                st.plotly_chart(fig, use_container_width=True)
        
        with col2:
            if show_gas and "gas_flow_nm3h" in ts_df.columns:
                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    x=ts_df["timestamp"],
                    y=ts_df["gas_flow_nm3h"],
                    mode="lines",
                    name="Gas Flow (Nm³/h)",
                    line=dict(color="#ff9500", width=2),
                    fill="tozeroy",
                    fillcolor="rgba(255, 149, 0, 0.15)"
                ))
                fig.update_layout(
                    **PLOTLY_LAYOUT,
                    title="🔥 NATURAL GAS FLOW",
                    height=300,
                    yaxis_title="Flow (Nm³/h)",
                )
                st.plotly_chart(fig, use_container_width=True)
        
        # Temperature & Humidity
        col3, col4 = st.columns(2)
        
        with col3:
            if show_temp and "temperature_c" in ts_df.columns:
                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    x=ts_df["timestamp"],
                    y=ts_df["temperature_c"],
                    mode="lines",
                    name="Temperature (°C)",
                    line=dict(color="#00d4aa", width=2),
                ))
                fig.update_layout(
                    **PLOTLY_LAYOUT,
                    title="🌡️ INTERNAL TEMPERATURE",
                    height=280,
                    yaxis_title="°C",
                )
                st.plotly_chart(fig, use_container_width=True)
        
        with col4:
            if "humidity_pct" in ts_df.columns:
                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    x=ts_df["timestamp"],
                    y=ts_df["humidity_pct"],
                    mode="lines",
                    name="Humidity (%)",
                    line=dict(color="#00b8d4", width=2),
                ))
                fig.update_layout(
                    **PLOTLY_LAYOUT,
                    title="💧 HUMIDITY LEVELS",
                    height=280,
                    yaxis_title="%",
                    yaxis_range=[0, 100],
                )
                st.plotly_chart(fig, use_container_width=True)

        col5, col6 = st.columns(2)

        with col5:
            if show_flame and "flame_analog" in ts_df.columns:
                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    x=ts_df["timestamp"],
                    y=ts_df["flame_analog"],
                    mode="lines",
                    name="Flame Analog",
                    line=dict(color="#ff4757", width=2),
                ))
                fig.update_layout(
                    **PLOTLY_LAYOUT,
                    title="🔥 FLAME ANALOG",
                    height=280,
                    yaxis_title="Raw value",
                )
                st.plotly_chart(fig, use_container_width=True)

        with col6:
            if show_flame and "flame_digital" in ts_df.columns:
                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    x=ts_df["timestamp"],
                    y=pd.to_numeric(ts_df["flame_digital"], errors="coerce"),
                    mode="lines",
                    name="Flame Digital",
                    line=dict(color="#ffb000", width=2),
                ))
                fig.update_layout(
                    **PLOTLY_LAYOUT,
                    title="🧯 FLAME DIGITAL",
                    height=280,
                    yaxis_title="State",
                    yaxis_range=[-0.1, 1.1],
                )
                st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("⏳ Waiting for data... Make sure MQTT listener is running.")
    
    # ===== DATA TABLE =====
    st.markdown("<h2 class='section-header'>📋 LATEST READINGS</h2>", unsafe_allow_html=True)
    
    if not ts_df.empty:
        display_cols = [
            "timestamp", "power_kw", "gas_flow_nm3h", "temperature_c",
            "humidity_pct", "co2_ppm", "voltage_v", "current_a", "is_anomaly"
        ]
        display_cols = [c for c in display_cols if c in ts_df.columns]
        st.dataframe(
            ts_df[display_cols].tail(20),
            use_container_width=True,
            hide_index=True
        )
    
else:
    # ===== HISTORICAL MODE =====
    st.markdown("<h2 class='section-header'>📊 HISTORICAL ANALYSIS</h2>", unsafe_allow_html=True)
    
    df = load_historical_data()
    
    if df.empty:
        st.error(
            "No processed historical data available. "
            "Run the pipeline:\n\n```bash\npython main.py\n```"
        )
        st.stop()

    # Debug info: show source file path and quick preview to confirm load
    try:
        src_path = Path(PROCESSED_DATA_DIR) / "energy_consolidated.csv"
        st.caption(f"Chargé depuis: {src_path} — {len(df):,} lignes")
        st.dataframe(df.head(8), use_container_width=True)
    except Exception:
        pass
    
    # Apply filters for historical data
    st.markdown("<div class='surface-panel'>", unsafe_allow_html=True)
    filter_col1, filter_col2, filter_col3 = st.columns([1.1, 1.1, 1.2])

    with filter_col1:
        if "source" in df.columns:
            sources = sorted(df["source"].dropna().unique())
            selected_sources = st.multiselect("📁 Source Files", sources, default=sources[:3] if len(sources) > 3 else sources)
            df = df[df["source"].isin(selected_sources)]

    with filter_col2:
        if "quantity_type" in df.columns:
            quantity_types = sorted(df["quantity_type"].dropna().unique())
            selected_qt = st.multiselect("🎯 Measurement Types", quantity_types, default=quantity_types)
            df = df[df["quantity_type"].isin(selected_qt)]

    with filter_col3:
        if "timestamp" in df.columns:
            valid_ts = df["timestamp"].dropna()
            if not valid_ts.empty:
                min_d = valid_ts.min().date()
                max_d = valid_ts.max().date()
                date_range = st.date_input("📅 Date Range", (min_d, max_d), min_value=min_d, max_value=max_d)
                if len(date_range) == 2:
                    start, end = date_range
                    df = df[(df["timestamp"].dt.date >= start) & (df["timestamp"].dt.date <= end)]
    st.markdown("</div>", unsafe_allow_html=True)
    
    if df.empty:
        st.warning("No data matches filters.")
        st.stop()
    
    # Calculate KPIs for historical data
    energy_rows = df[df.get("quantity_type", "") == "energy"] if "quantity_type" in df.columns else df
    total_kwh = energy_rows.get("delta_kwh", pd.Series()).sum() if "delta_kwh" in energy_rows.columns else 0
    total_co2 = energy_rows.get("co2_kg", pd.Series()).sum() if "co2_kg" in energy_rows.columns else 0

    anomalies_count = int(df["is_anomaly"].sum()) if "is_anomaly" in df.columns else 0
    source_count = int(df["source"].nunique()) if "source" in df.columns else 0
    avg_value = df.get("value", pd.Series(dtype="float64")).mean()

    st.markdown(
        f"""
        <div class='hero-grid'>
            <div class='hero-panel'>
                <div class='hero-kicker'>Analytics view</div>
                <h3 class='hero-title'>Historical data explorer</h3>
                <div class='hero-copy'>
                    Inspect consolidated energy records, isolate anomalies, and export filtered slices without leaving the dashboard.
                </div>
            </div>
            <div class='hero-panel'>
                <div class='hero-kicker'>Dataset state</div>
                <div class='mini-stat-grid'>
                    <div class='mini-stat'>
                        <span class='label'>Rows</span>
                        <span class='value'>{len(df):,}</span>
                        <span class='hint'>filtered records</span>
                    </div>
                    <div class='mini-stat'>
                        <span class='label'>Sources</span>
                        <span class='value'>{source_count:,}</span>
                        <span class='hint'>input files</span>
                    </div>
                    <div class='mini-stat'>
                        <span class='label'>Energy</span>
                        <span class='value'>{total_kwh:,.1f}</span>
                        <span class='hint'>kWh window</span>
                    </div>
                    <div class='mini-stat'>
                        <span class='label'>Anomalies</span>
                        <span class='value'>{anomalies_count:,}</span>
                        <span class='hint'>flagged points</span>
                    </div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(
        f"""
        <div class='surface-panel' style='margin-top:0.8rem;'>
            <div class='hero-kicker'>Context snapshot</div>
            <div class='mini-stat-grid' style='grid-template-columns: repeat(3, minmax(0, 1fr)); margin-top:0.75rem;'>
                <div class='mini-stat'>
                    <span class='label'>Avg value</span>
                    <span class='value'>{avg_value:.2f}</span>
                    <span class='hint'>current filtered mean</span>
                </div>
                <div class='mini-stat'>
                    <span class='label'>CO₂ kg</span>
                    <span class='value'>{total_co2:,.1f}</span>
                    <span class='hint'>emissions window</span>
                </div>
                <div class='mini-stat'>
                    <span class='label'>Anomaly rate</span>
                    <span class='value'>{(anomalies_count / max(len(df), 1)) * 100:.1f}%</span>
                    <span class='hint'>share of filtered rows</span>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    
    # Tabs for historical analysis
    tab_overview, tab_timeseries, tab_anomalies, tab_export = st.tabs(
        ["📊 Overview", "📈 Time Series", "⚠️ Anomalies", "💾 Export"]
    )
    
    with tab_overview:
        left, right = st.columns([1.05, 1.2])
        with left:
            st.markdown("<div class='hero-panel'>", unsafe_allow_html=True)
            st.markdown("<div class='hero-kicker'>Overview</div>", unsafe_allow_html=True)
            st.markdown("<h3 class='hero-title' style='font-size:1.2rem;'>Energy mix by source</h3>", unsafe_allow_html=True)
            st.markdown("<div class='hero-copy'>The historical dataset can be broken down by source file, making it easier to spot skew in the consolidated feed.</div>", unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)
        with right:
            if "co2_source" in df.columns and "delta_kwh" in df.columns:
                mix = df.groupby("co2_source")["delta_kwh"].sum().reset_index()
                fig = px.pie(mix, values="delta_kwh", names="co2_source", hole=0.45)
                fig.update_layout(**PLOTLY_LAYOUT, height=360)
                st.plotly_chart(fig, use_container_width=True)
    
    with tab_timeseries:
        st.markdown("<div class='surface-panel'>", unsafe_allow_html=True)
        if "timestamp" in df.columns and "value" in df.columns:
            ts_plot = df.sort_values("timestamp")
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=ts_plot["timestamp"],
                y=ts_plot["value"],
                mode="lines",
                name="Value",
                line=dict(color="#00d4aa", width=2.3),
                fill="tozeroy",
                fillcolor="rgba(0, 212, 170, 0.12)",
            ))
            fig.update_layout(**PLOTLY_LAYOUT, height=420, title="Consumption over time")
            st.plotly_chart(fig, use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)
    
    with tab_anomalies:
        st.markdown("<div class='surface-panel'>", unsafe_allow_html=True)
        anomaly_left, anomaly_right = st.columns([0.9, 1.3])
        with anomaly_left:
            st.markdown("<div class='hero-kicker'>Integrity</div>", unsafe_allow_html=True)
            st.markdown("<h3 class='hero-title' style='font-size:1.2rem;'>Detected anomalies</h3>", unsafe_allow_html=True)
            st.markdown("<div class='hero-copy'>A quick view of inconsistent points in the filtered slice. Use the table for inspection or switch back to live mode for realtime surveillance.</div>", unsafe_allow_html=True)
            if "is_anomaly" in df.columns:
                anomalies = df[df["is_anomaly"] == True]
                st.markdown(
                    f"""
                    <div class='stat-card' style='margin-top:1rem;'>
                        <span class='label'>Total anomalies</span>
                        <span class='value'>{len(anomalies):,}</span>
                        <span class='hint'>flagged rows in the current filter set</span>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            else:
                st.info("No anomaly data available.")
        with anomaly_right:
            if "is_anomaly" in df.columns:
                anomalies = df[df["is_anomaly"] == True]
                if not anomalies.empty:
                    st.dataframe(anomalies.head(50), use_container_width=True, hide_index=True)
                else:
                    st.success("No anomalies in the current historical slice.")
        st.markdown("</div>", unsafe_allow_html=True)
    
    with tab_export:
        export_left, export_right = st.columns([1.05, 0.95])
        with export_left:
            st.markdown("<div class='hero-panel'>", unsafe_allow_html=True)
            st.markdown("<div class='hero-kicker'>Export</div>", unsafe_allow_html=True)
            st.markdown("<h3 class='hero-title' style='font-size:1.2rem;'>Filtered dataset</h3>", unsafe_allow_html=True)
            st.markdown("<div class='hero-copy'>Download the current slice as CSV or JSON with the active source, measurement, and date filters applied.</div>", unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)
        with export_right:
            st.markdown("<div class='surface-panel'>", unsafe_allow_html=True)
            csv = df.to_csv(index=False).encode("utf-8")
            st.download_button(
                "📥 Download as CSV",
                csv,
                f"retech_historical_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                "text/csv"
            )
            
            json_data = df.to_json(orient="records", date_format="iso")
            st.download_button(
                "📤 Download as JSON",
                json_data,
                f"retech_historical_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                "application/json"
            )
            st.markdown("</div>", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# FOOTER
# ---------------------------------------------------------------------------
st.markdown(
    "<div class='footer'>"
    "⚡ Re·Tech Fusion · Live Monitoring Dashboard · INSAT "
    "</div>",
    unsafe_allow_html=True,
)