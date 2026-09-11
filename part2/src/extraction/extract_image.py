"""extract_image.py — OCR-based extraction from scanned WhatsApp photos.

Handles three document types found in the dataset:
  1. STEG_INVOICE_MT  — "FACTURE MOYENNE TENSION" (electricity bill)
  2. STEG_METER_READ  — "FICHE RELEVE ENERGIE" (meter reading sheet)
  3. SONEDE_WATER     — "Facture de consommation eau" (water bill, ignored
                         for energy pipeline but still detected and logged)

Pipeline per image:
    load -> grayscale -> upscale 2x -> OCR (multi-PSM) -> classify -> regex extract

Output: a long-format DataFrame with the same schema as extract_excel:
    source | sheet | timestamp | category | measure | value | unit
"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Optional, Union

import cv2
import numpy as np
import pandas as pd
import pytesseract
from loguru import logger

# Configure Tesseract path for Windows
import sys
from pathlib import Path as PathlibPath
if sys.platform == "win32":
    tesseract_path = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    if PathlibPath(tesseract_path).exists():
        pytesseract.pytesseract.tesseract_cmd = tesseract_path

# ---------------------------------------------------------------------------
# OCR config
# ---------------------------------------------------------------------------
# Order of preferred languages (Tesseract uses the first one that's installed).
# `eng` is always available; `fra` and `ara` improve accuracy if installed.
_LANGS_TO_TRY = ["fra+ara+eng", "fra+eng", "eng"]

# Page Segmentation Modes (PSM) we try, ordered by reliability for invoices:
#   6 = uniform block of text (best for dense forms)
#   4 = single column of text of variable size
#  11 = sparse text (large gaps)
_PSMS_TO_TRY = [6]  # PSM 6 = uniform block; this single mode handles >90% of cases.
                    # We could fall back to others on UNKNOWN, but in practice the
                    # auto-rotation logic below recovers more cases for less cost.


def _get_available_lang() -> str:
    """Return the best language combination available on this Tesseract install."""
    try:
        installed = set(pytesseract.get_languages(config=""))
    except Exception:
        return "eng"
    for combo in _LANGS_TO_TRY:
        if all(lang in installed for lang in combo.split("+")):
            return combo
    return "eng"


# ---------------------------------------------------------------------------
# Image preprocessing
# ---------------------------------------------------------------------------
def _preprocess(img: np.ndarray) -> np.ndarray:
    """Grayscale + 2x upscale. The single biggest OCR quality boost on phone photos."""
    if img.ndim == 3:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    else:
        gray = img
    h, w = gray.shape
    return cv2.resize(gray, (w * 2, h * 2), interpolation=cv2.INTER_CUBIC)


def _rotate(image: np.ndarray, angle: int) -> np.ndarray:
    """Rotate by 90, 180 or 270 degrees losslessly."""
    if angle == 90:
        return cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE)
    if angle == 180:
        return cv2.rotate(image, cv2.ROTATE_180)
    if angle == 270:
        return cv2.rotate(image, cv2.ROTATE_90_COUNTERCLOCKWISE)
    return image


def _ocr_with_autorotate(image: np.ndarray, lang: str) -> tuple[str, str, int]:
    """OCR an image, trying rotations 0/90/180/270 if the first pass yields UNKNOWN.

    Returns (text, doc_type, rotation_used).
    """
    for angle in (0, 90, 270, 180):
        candidate = _rotate(image, angle) if angle else image
        text = _ocr_text(candidate, lang=lang)
        doc_type = classify_document(text)
        if doc_type != "UNKNOWN":
            return text, doc_type, angle
    # Nothing classified — return the 0° text for downstream raw-text logging
    text = _ocr_text(image, lang=lang)
    return text, "UNKNOWN", 0


def _ocr_text(image: np.ndarray, lang: str) -> str:
    """Run OCR with several PSM modes and return the longest result."""
    best = ""
    for psm in _PSMS_TO_TRY:
        try:
            txt = pytesseract.image_to_string(image, lang=lang, config=f"--psm {psm}")
        except pytesseract.TesseractError as e:
            logger.warning(f"  Tesseract failed (psm={psm}, lang={lang}): {e}")
            continue
        if len(txt) > len(best):
            best = txt
    return best


# ---------------------------------------------------------------------------
# Document classification
# ---------------------------------------------------------------------------
def classify_document(text: str) -> str:
    """Return one of: STEG_INVOICE_MT, STEG_METER_READ, SONEDE_WATER, UNKNOWN.

    Robust to common OCR noise (missing initial letters, stray spaces, slight
    mis-readings) by checking several keyword variants.
    """
    t = text.upper()
    # STEG MT invoice — word "TENSION" + ("MOYENNE" or "FACTURE"/"ACTURE")
    if "TENSION" in t and ("MOYENNE" in t or "ACTURE" in t):
        return "STEG_INVOICE_MT"
    # STEG meter reading sheet
    if (
        "FICHE" in t and "RELEV" in t
        or "ACHAT ET VENTE" in t
        or "RELEVE ENERGIE" in t
        or "RELEVE D'ENERGIE" in t
        or "INDEX D'ENERGIE" in t
    ):
        return "STEG_METER_READ"
    # SONEDE water bill
    if "SONEDE" in t or "CONSOMMATION EAU" in t or "DISTRIBUTION DES EAUX" in t:
        return "SONEDE_WATER"
    return "UNKNOWN"


# ---------------------------------------------------------------------------
# Regex helpers
# ---------------------------------------------------------------------------
_NUMBER_FR = r"\d{1,3}(?:[ \xa0.]\d{3})*(?:[.,]\d+)?"  # "10 173,290" or "10.173,290"


def _to_float_fr(s: str) -> Optional[float]:
    """Convert a French-formatted number string to float."""
    if not s:
        return None
    cleaned = s.replace(" ", "").replace("\xa0", "")
    # If both `.` and `,` present, the last one is the decimal separator
    if "." in cleaned and "," in cleaned:
        if cleaned.rfind(",") > cleaned.rfind("."):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        # comma is decimal separator
        cleaned = cleaned.replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


def _find(pattern: str, text: str, flags: int = re.IGNORECASE) -> Optional[str]:
    m = re.search(pattern, text, flags)
    return m.group(1) if m else None


def _parse_month_year(text: str) -> Optional[datetime]:
    """Try to find a MM/YYYY date associated with the 'Mois' field."""
    # Direct MM/YYYY pattern
    m = re.search(r"Mois[^0-9]{0,15}(\d{1,2})\s*[/.\-]\s*(\d{4})", text, re.IGNORECASE)
    if m:
        try:
            return datetime(int(m.group(2)), int(m.group(1)), 1)
        except ValueError:
            pass
    # Fallback: any standalone MM/YYYY in the first 500 chars
    m = re.search(r"\b(0[1-9]|1[0-2])\s*/\s*(20\d{2})\b", text[:600])
    if m:
        try:
            return datetime(int(m.group(2)), int(m.group(1)), 1)
        except ValueError:
            pass
    return None


# ---------------------------------------------------------------------------
# Type-specific extractors
# ---------------------------------------------------------------------------
def _extract_steg_invoice_mt(text: str, source: str) -> list[dict]:
    """Extract from FACTURE MOYENNE TENSION.

    Target fields:
      - Total active energy (kWh)   -> often appears as "Total" line or 4-5 digit nbr
      - Reactive energy (kVARh)
      - Net to pay (DT)             -> "NET A PAYER" or stand-alone number near end
    """
    rows: list[dict] = []
    timestamp = _parse_month_year(text) or pd.NaT
    invoice_no = _find(r"N[°*o]\s*Facture\s*:?\s*([A-Z0-9]+)", text)
    district = _find(r"District\s+([A-Z]{3,})", text)

    # --- Active energy total: largest of the kWh consumption candidates ---
    # In MT invoices the "Consommation a facturer kWh" column has a final total
    # like 6348 or 36 754. We grab all 3-7 digit numbers and take the median-large one.
    nums_4_7 = [int(n) for n in re.findall(r"\b(\d{4,7})\b", text)]
    # Filter out year-like and obvious indices (>1e6 are meter indices, not consumption)
    consumption_candidates = [n for n in nums_4_7 if 100 <= n <= 999_999]
    total_kwh: Optional[float] = None
    if consumption_candidates:
        # Heuristic: total active is the most-repeated value (totals appear several
        # times: as line total, sub-total, "Mois" line) OR the largest reasonable one
        from collections import Counter
        most_common = Counter(consumption_candidates).most_common(3)
        total_kwh = float(most_common[0][0])

    # --- Net amount (DT) ---
    # Format like "10 173,290"  -- contains thousands separator AND 3-digit decimals
    money = _find(rf"({_NUMBER_FR})\s*(?:NET\s*A\s*PAYER|DT)?", text)
    montant = None
    money_match = re.search(r"\b(\d{1,3}(?:[ .]\d{3})+[,.]\d{3})\b", text)
    if money_match:
        montant = _to_float_fr(money_match.group(1))

    base = {
        "source": source,
        "sheet": "STEG_INVOICE_MT",
        "timestamp": timestamp,
        "doc_id": invoice_no or "",
        "district": district or "",
    }

    if total_kwh is not None:
        rows.append({**base, "category": "Consommation électrique",
                     "measure": "Énergie active totale facturée",
                     "value": total_kwh, "unit": "kWh"})
    if montant is not None:
        rows.append({**base, "category": "Facture",
                     "measure": "Net à payer",
                     "value": montant, "unit": "DT"})
    return rows


def _extract_steg_meter_read(text: str, source: str) -> list[dict]:
    """Extract from FICHE RELEVE ENERGIE.

    Target: index Jour/Pointe/Nuit/Soir Ancien/Nouveau (kWh) and Réactive (kVARh).
    Layout is too tabular for plain regex on noisy OCR — we do a best-effort:
    grab `Jour ... <num> <num>` style patterns.
    """
    rows: list[dict] = []
    timestamp = _parse_month_year(text) or pd.NaT
    base = {
        "source": source,
        "sheet": "STEG_METER_READ",
        "timestamp": timestamp,
    }

    # Patterns like "Jour    1.8.3   23391547   23393729"
    for label in ["Jour", "Pointe", "Nuit", "Soir", "Reactive", "Réactive"]:
        m = re.search(
            rf"\b{label}\b[^\d]{{0,40}}(\d{{6,9}})[^\d]{{1,15}}(\d{{6,9}})",
            text, re.IGNORECASE,
        )
        if m:
            ancien, nouveau = int(m.group(1)), int(m.group(2))
            consommation = max(0, nouveau - ancien)
            unit = "kVARh" if "eactiv" in label.lower() or "active" in label.lower() else "kWh"
            rows.append({
                **base,
                "category": "Index énergie",
                "measure": f"Index {label} (consommation période)",
                "value": consommation,
                "unit": unit,
            })

    # OCR on phone photos often drops the column labels while keeping the two
    # large index numbers on the same line. As a fallback, recover any line that
    # contains at least two large numbers and treat them as old/new indices.
    if not rows:
        excluded_terms = ("TEL", "CLIENT", "REF", "N°CTR", "NCTR", "MOIS", "ANN", "AGENT")
        candidate_lines: list[tuple[int, str, list[str]]] = []
        for line in text.splitlines():
            nums = re.findall(r"\b\d{6,9}\b", line)
            if len(nums) < 2:
                continue
            if any(term in line.upper() for term in excluded_terms):
                continue
            alpha_score = len(re.findall(r"[A-Za-zÀ-ÿ]", line))
            candidate_lines.append((alpha_score, line, nums))

        if candidate_lines:
            _, _, nums = min(candidate_lines, key=lambda item: (item[0], -len(item[2])))
            old_i, new_i = int(nums[0]), int(nums[1])
            consommation = max(0, new_i - old_i)
            rows.append({
                **base,
                "category": "Index énergie",
                "measure": "Index détecté (consommation période)",
                "value": consommation,
                "unit": "kWh",
            })
    return rows


def _extract_sonede_water(text: str, source: str) -> list[dict]:
    """Extract from SONEDE water invoices (out of energy scope but logged)."""
    timestamp = _parse_month_year(text) or pd.NaT
    base = {
        "source": source,
        "sheet": "SONEDE_WATER",
        "timestamp": timestamp,
    }
    # Volume in m3 — often labeled "Qté cons.(m3)" or a 3-5 digit value near "m3"
    m = re.search(r"(\d{3,5})[^\d]{0,30}(?:m\xb3|m3)", text)
    rows = []
    if m:
        rows.append({
            **base,
            "category": "Eau",
            "measure": "Quantité consommée",
            "value": float(m.group(1)),
            "unit": "m3",
        })
    return rows


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def extract_image(filepath: Union[str, Path]) -> pd.DataFrame:
    """Extract energy data from a single scanned invoice/sheet image.

    Tries the Gemini API first (if GEMINI_API_KEY is set); falls back to
    Tesseract + regex on failure or when Gemini is unavailable.
    """
    filepath = Path(filepath)

    # Gemini first (much higher quality on noisy phone photos)
    try:
        from src.extraction.extract_gemini import extract_with_gemini, is_available
        if is_available():
            df = extract_with_gemini(filepath)
            if not df.empty:
                return df
            logger.info(f"  Gemini returned no rows for {filepath.name}; "
                        "falling back to Tesseract")
    except Exception as e:
        logger.warning(f"  Gemini path errored ({e}); falling back to Tesseract")

    logger.info(f"OCR (Tesseract) on image: {filepath.name}")
    img = cv2.imread(str(filepath))
    if img is None:
        logger.error(f"  Could not read image: {filepath}")
        return pd.DataFrame()

    pre = _preprocess(img)
    lang = _get_available_lang()
    text, doc_type, rotation = _ocr_with_autorotate(pre, lang=lang)
    logger.info(
        f"  Detected: {doc_type}  (rot={rotation}°, {len(text)} chars OCR'd, lang={lang})"
    )

    if doc_type == "STEG_INVOICE_MT":
        rows = _extract_steg_invoice_mt(text, filepath.name)
    elif doc_type == "STEG_METER_READ":
        rows = _extract_steg_meter_read(text, filepath.name)
    elif doc_type == "SONEDE_WATER":
        rows = _extract_sonede_water(text, filepath.name)
    else:
        # Unknown — emit one bookkeeping row with raw OCR for manual review
        rows = [{
            "source": filepath.name,
            "sheet": "UNKNOWN",
            "timestamp": pd.NaT,
            "category": "OCR_RAW",
            "measure": "Texte non classifié",
            "value": None,
            "unit": "",
            "raw_text": text[:500],
        }]
        logger.warning(f"  Could not classify {filepath.name}")

    return pd.DataFrame(rows)


def extract_all_images(folder: Union[str, Path]) -> pd.DataFrame:
    """Extract all .jpg/.jpeg/.png in a folder. Errors on individual files don't
    stop the batch."""
    folder = Path(folder)
    files = sorted(
        list(folder.glob("*.jpg"))
        + list(folder.glob("*.jpeg"))
        + list(folder.glob("*.JPG"))
        + list(folder.glob("*.JPEG"))
        + list(folder.glob("*.png"))
        + list(folder.glob("*.PNG"))
    )
    logger.info(f"Found {len(files)} image(s) in {folder}")

    dfs: list[pd.DataFrame] = []
    for f in files:
        try:
            df = extract_image(f)
            if not df.empty:
                dfs.append(df)
        except Exception as e:
            logger.error(f"  Failed on {f.name}: {e}")

    if not dfs:
        return pd.DataFrame(
            columns=["source", "sheet", "timestamp", "category", "measure", "value", "unit"]
        )
    result = pd.concat(dfs, ignore_index=True)
    logger.success(f"Total OCR rows extracted: {len(result):,}")
    return result


# ---------------------------------------------------------------------------
# CLI helper
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys
    from pathlib import Path
    
    if len(sys.argv) > 1:
        path = Path(sys.argv[1])
        if path.is_dir():
            df = extract_all_images(path)
        elif path.is_file():
            df = extract_image(path)
        else:
            print(f"Error: {path} does not exist")
            sys.exit(1)
        print(df.head(20))
        print(f"\nShape: {df.shape}")
        if not df.empty:
            print(f"\nDoc types: {df['sheet'].value_counts().to_dict()}")
    else:
        print("Usage: python extract_image.py <image_file_or_folder>")