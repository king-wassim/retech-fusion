"""main.py — Pipeline orchestrator.

End-to-end flow:
    1. Extract from Excel (PDFs and images skipped if their modules
       are still skeletons; the pipeline degrades gracefully).
    2. Normalize units to kWh (only for energy measurements).
    3. Convert cumulative meter indices to per-period deltas.
    4. Compute CO2 emissions on the deltas.
    5. (Optional) Detect anomalies.
    6. Save consolidated CSV for the Streamlit dashboard.
"""
from pathlib import Path

import pandas as pd
from loguru import logger

from src.extraction.extract_excel import extract_all_excels
from src.normalization.normalize import normalize_to_kwh
from src.emissions.co2 import add_co2_emissions, cumulative_to_delta
from src.utils.config import RAW_DATA_DIR, PROCESSED_DATA_DIR


def _safe_extract(name, fn, *args):
    try:
        out = fn(*args)
        logger.info(f"{name}: {len(out):,} rows")
        return out
    except Exception as e:
        logger.warning(f"{name} skipped: {e}")
        return pd.DataFrame()


def run_pipeline() -> pd.DataFrame:
    logger.info("=== Re·Tech Fusion pipeline started ===")

    # 1. EXTRACT — Excel (mandatory) + PDFs + images (best-effort)
    df_excel = extract_all_excels(RAW_DATA_DIR)

    from src.extraction.extract_pdf import extract_all_pdfs
    from src.extraction.extract_image import extract_all_images
    df_pdf = _safe_extract("PDFs", extract_all_pdfs, RAW_DATA_DIR)
    df_img = _safe_extract("Images", extract_all_images, RAW_DATA_DIR)

    parts = [d for d in (df_excel, df_pdf, df_img) if d is not None and not d.empty]
    if not parts:
        logger.error(f"No data extracted from {RAW_DATA_DIR}. Aborting.")
        return pd.DataFrame()
    df = pd.concat(parts, ignore_index=True)
    logger.info(f"Combined extract: {len(df):,} rows "
                f"(excel={len(df_excel)}, pdf={len(df_pdf)}, img={len(df_img)})")

    # 2. NORMALIZE units
    df = normalize_to_kwh(df)

    # 3. Cumulative indices -> per-period deltas
    df = cumulative_to_delta(df, group_cols=("source", "measure"))

    # 4. CO2 on the DELTA, not the cumulative index
    df_for_co2 = df.copy()
    df_for_co2["value_kwh"] = df_for_co2["delta_kwh"]
    df_with_co2 = add_co2_emissions(df_for_co2)
    df["co2_kg"] = df_with_co2["co2_kg"]
    df["co2_source"] = df_with_co2["co2_source"]
    df["co2_factor"] = df_with_co2["co2_factor"]

    # 5. Anomaly detection — optional, skip if module not ready
    try:
        from src.anomalies.detect import detect_anomalies
        df = detect_anomalies(df)
    except Exception as e:
        logger.warning(f"Anomaly detection skipped: {e}")

    # 6. SAVE
    out_path = Path(PROCESSED_DATA_DIR) / "energy_consolidated.csv"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path, index=False)
    logger.success(f"Saved {len(df):,} rows -> {out_path}")
    return df


if __name__ == "__main__":
    run_pipeline()