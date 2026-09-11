"""extract_gemini.py — OCR + structured extraction via the Gemini API.

Replaces the noisy Tesseract-based pipeline for invoice/sheet images and
scanned PDFs. Returns the same long-format DataFrame as the other extractors:

    source | sheet | timestamp | category | measure | value | unit
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Optional, Union

import pandas as pd
from dotenv import load_dotenv
from loguru import logger

load_dotenv()  # ensure .env is loaded regardless of import order

_DEFAULT_GEMINI_MODEL = "gemini-2.0-flash"

PROMPT = """Tu es un extracteur de données de factures d'énergie tunisiennes.
Analyse cette image et retourne un JSON avec exactement ces champs :
{
  "document_type": "STEG_INVOICE_MT" | "STEG_METER_READ" | "SONEDE_WATER" | "UNKNOWN",
  "month": "MM/YYYY",
  "invoice_number": "...",
  "total_kwh": number or null,
  "reactive_kvarh": number or null,
  "net_amount_dt": number or null,
  "meter_readings": [
    {"period": "Jour|Pointe|Nuit|Soir", "old_index": number, "new_index": number}
  ]
}
Retourne UNIQUEMENT le JSON, aucun texte avant ou après."""


def is_available() -> bool:
    """True iff a GEMINI_API_KEY is set and the SDK can be imported."""
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        logger.debug("Gemini disabled: GEMINI_API_KEY not set")
        return False
    try:
        import google.generativeai  # noqa: F401
        return True
    except ImportError:
        logger.warning("Gemini disabled: google-generativeai not installed — run: pip install google-generativeai")
        return False


def _strip_json_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _call_gemini(image_bytes: bytes, mime_type: str = "image/jpeg") -> Optional[dict]:
    import google.generativeai as genai

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        logger.warning("GEMINI_API_KEY not set")
        return None

    model_name = os.getenv("GEMINI_MODEL", _DEFAULT_GEMINI_MODEL)
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(model_name)
    try:
        response = model.generate_content(
            [PROMPT, {"mime_type": mime_type, "data": image_bytes}],
            generation_config={"temperature": 0.0, "response_mime_type": "application/json"},
        )
    except Exception as e:
        logger.error(f"Gemini call failed: {e}")
        return None

    text = _strip_json_fence(response.text or "")
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        logger.warning(f"Gemini returned non-JSON: {e}; raw start: {text[:120]!r}")
        return None


def _parse_month(month_str: Optional[str]) -> pd.Timestamp:
    if not month_str:
        return pd.NaT
    m = re.match(r"\s*(\d{1,2})\s*/\s*(\d{4})\s*", str(month_str))
    if not m:
        return pd.NaT
    try:
        return pd.Timestamp(datetime(int(m.group(2)), int(m.group(1)), 1))
    except ValueError:
        return pd.NaT


def _result_to_rows(result: dict, source: str, sheet_override: Optional[str] = None) -> list[dict]:
    rows: list[dict] = []
    doc_type = result.get("document_type") or "UNKNOWN"
    sheet = sheet_override or doc_type
    timestamp = _parse_month(result.get("month"))
    invoice_no = result.get("invoice_number") or ""

    base = {
        "source": source,
        "sheet": sheet,
        "timestamp": timestamp,
        "doc_id": invoice_no,
    }

    if result.get("total_kwh") is not None:
        rows.append({**base, "category": "Consommation électrique",
                     "measure": "Énergie active totale facturée",
                     "value": float(result["total_kwh"]), "unit": "kWh"})
    if result.get("reactive_kvarh") is not None:
        rows.append({**base, "category": "Consommation électrique",
                     "measure": "Énergie réactive",
                     "value": float(result["reactive_kvarh"]), "unit": "kVARh"})
    if result.get("net_amount_dt") is not None:
        rows.append({**base, "category": "Facture",
                     "measure": "Net à payer",
                     "value": float(result["net_amount_dt"]), "unit": "DT"})

    for r in result.get("meter_readings") or []:
        try:
            old_i = float(r["old_index"])
            new_i = float(r["new_index"])
        except (KeyError, TypeError, ValueError):
            continue
        period = r.get("period", "?")
        unit = "kVARh" if "eactiv" in period.lower() else "kWh"
        rows.append({**base, "category": "Index énergie",
                     "measure": f"Index {period} (consommation période)",
                     "value": max(0.0, new_i - old_i), "unit": unit})
    return rows


def extract_with_gemini(filepath: Union[str, Path]) -> pd.DataFrame:
    """Extract structured data from a single image (jpg/jpeg/png) via Gemini."""
    filepath = Path(filepath)
    logger.info(f"Gemini OCR on: {filepath.name}")

    suffix = filepath.suffix.lower()
    mime = {".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".png": "image/png"}.get(suffix, "image/jpeg")

    with filepath.open("rb") as f:
        image_bytes = f.read()

    result = _call_gemini(image_bytes, mime_type=mime)
    if not result:
        return pd.DataFrame()

    rows = _result_to_rows(result, source=filepath.name)
    if not rows:
        logger.warning(f"Gemini classified {filepath.name} as "
                       f"{result.get('document_type')} but no rows extracted")
    return pd.DataFrame(rows)


def extract_pdf_with_gemini(filepath: Union[str, Path]) -> pd.DataFrame:
    """Convert a PDF to images, send each page to Gemini, concat results."""
    filepath = Path(filepath)
    logger.info(f"Gemini OCR on PDF: {filepath.name}")
    try:
        from pdf2image import convert_from_path
    except ImportError:
        logger.error("pdf2image not installed")
        return pd.DataFrame()

    try:
        pages = convert_from_path(str(filepath), dpi=180)
    except Exception as e:
        logger.error(f"pdf2image failed on {filepath.name}: {e}")
        return pd.DataFrame()

    import io
    dfs: list[pd.DataFrame] = []
    for i, page in enumerate(pages, 1):
        buf = io.BytesIO()
        page.save(buf, format="PNG")
        result = _call_gemini(buf.getvalue(), mime_type="image/png")
        if not result:
            continue
        rows = _result_to_rows(result, source=f"{filepath.name}#p{i}")
        if rows:
            dfs.append(pd.DataFrame(rows))

    if not dfs:
        return pd.DataFrame()
    return pd.concat(dfs, ignore_index=True)


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python extract_gemini.py <image_or_pdf>")
        sys.exit(1)
    p = Path(sys.argv[1])
    if p.suffix.lower() == ".pdf":
        df = extract_pdf_with_gemini(p)
    else:
        df = extract_with_gemini(p)
    print(df)
    print(f"\nShape: {df.shape}")
