"""extract_pdf.py — Extract energy data from PDF invoices/reports.

Strategy:
  1. Try `pdfplumber` for native (text-based) PDFs.
  2. If the PDF appears scanned (very little extractable text), fall back to
     Gemini OCR on each rasterized page.

Output: long-format DataFrame  source | sheet | timestamp | category | measure | value | unit
"""
from __future__ import annotations

from pathlib import Path
from typing import Union

import pandas as pd
import pdfplumber
from loguru import logger

# A page is "scanned" if pdfplumber pulls out fewer than this many chars.
_SCANNED_CHAR_THRESHOLD = 50


def _looks_scanned(pdf_path: Path) -> bool:
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text() or ""
                if len(text.strip()) >= _SCANNED_CHAR_THRESHOLD:
                    return False
        return True
    except Exception as e:
        logger.warning(f"pdfplumber probe failed on {pdf_path.name}: {e}")
        return True


def _extract_native(pdf_path: Path) -> pd.DataFrame:
    """Best-effort table extraction from text-based PDFs.

    Without a known schema we just dump table rows; the normalize stage
    drops anything that does not classify as energy.
    """
    rows: list[dict] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_idx, page in enumerate(pdf.pages, 1):
            for table in page.extract_tables() or []:
                for row in table:
                    if not row:
                        continue
                    # Find the first numeric cell as value, the rest as label
                    label_parts = [c for c in row if c and not _is_numeric(c)]
                    value = next((_parse_num(c) for c in row if c and _is_numeric(c)), None)
                    if value is None or not label_parts:
                        continue
                    rows.append({
                        "source": pdf_path.name,
                        "sheet": f"page_{page_idx}",
                        "timestamp": pd.NaT,
                        "category": "PDF_TABLE",
                        "measure": " ".join(label_parts)[:120],
                        "value": value,
                        "unit": "",
                    })
    return pd.DataFrame(rows)


def _is_numeric(cell: str) -> bool:
    s = cell.strip().replace(" ", "").replace("\xa0", "").replace(",", ".")
    if not s:
        return False
    try:
        float(s)
        return True
    except ValueError:
        return False


def _parse_num(cell: str) -> float | None:
    s = cell.strip().replace(" ", "").replace("\xa0", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def extract_pdf(filepath: Union[str, Path]) -> pd.DataFrame:
    filepath = Path(filepath)
    logger.info(f"Reading PDF: {filepath.name}")

    if _looks_scanned(filepath):
        logger.info(f"  {filepath.name} looks scanned — using Gemini")
        try:
            from src.extraction.extract_gemini import extract_pdf_with_gemini, is_available
            if is_available():
                df = extract_pdf_with_gemini(filepath)
                if not df.empty:
                    return df
                logger.warning(f"  Gemini returned nothing for {filepath.name}")
            else:
                logger.warning("  Gemini unavailable (no API key); skipping scanned PDF")
        except Exception as e:
            logger.error(f"  Gemini PDF extraction errored: {e}")
        return pd.DataFrame()

    return _extract_native(filepath)


def extract_all_pdfs(folder: Union[str, Path]) -> pd.DataFrame:
    folder = Path(folder)
    files = sorted(folder.glob("*.pdf")) + sorted(folder.glob("*.PDF"))
    logger.info(f"Found {len(files)} PDF file(s) in {folder}")
    dfs: list[pd.DataFrame] = []
    for f in files:
        try:
            df = extract_pdf(f)
            if not df.empty:
                dfs.append(df)
        except Exception as e:
            logger.error(f"  Failed on {f.name}: {e}")
    if not dfs:
        return pd.DataFrame(
            columns=["source", "sheet", "timestamp", "category", "measure", "value", "unit"]
        )
    out = pd.concat(dfs, ignore_index=True)
    logger.success(f"Total PDF rows extracted: {len(out):,}")
    return out


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        p = Path(sys.argv[1])
        df = extract_all_pdfs(p) if p.is_dir() else extract_pdf(p)
        print(df.head(20))
        print(f"\nShape: {df.shape}")
    else:
        print("Usage: python extract_pdf.py <pdf_or_folder>")
