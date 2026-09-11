# =============================================================================
# Re·Tech Fusion — Energy Pipeline image
# =============================================================================
# Single image that can run both:
#   - the pipeline (CMD: python main.py)
#   - the dashboard (CMD: streamlit run src/dashboard/app.py)
# The actual command is chosen by docker-compose per service.
# =============================================================================

FROM python:3.11-slim

# Avoid Python writing .pyc files and force unbuffered stdout (real-time logs)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DEBIAN_FRONTEND=noninteractive

# -----------------------------------------------------------------------------
# System dependencies
#   - tesseract-ocr + language packs : for OCR module (image extraction)
#   - poppler-utils                  : for PDF -> image conversion (pdf2image)
#   - libgl1 + libglib2.0-0          : runtime deps for opencv-python-headless
# -----------------------------------------------------------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    tesseract-ocr \
    tesseract-ocr-fra \
    tesseract-ocr-ara \
    poppler-utils \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# -----------------------------------------------------------------------------
# Python deps (cached layer — only rebuilt when requirements.txt changes)
# -----------------------------------------------------------------------------
COPY requirements.txt .
# Upgrade packaging tools first to avoid build-time failures for some wheels
RUN python -m pip install --upgrade pip setuptools wheel && \
    pip install -r requirements.txt

# -----------------------------------------------------------------------------
# Application code
# -----------------------------------------------------------------------------
COPY . .

# Make /app importable as a package root
ENV PYTHONPATH=/app

# Streamlit needs these envs to bind on all interfaces (not just 127.0.0.1)
# and to be container-friendly
ENV STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_SERVER_PORT=8501 \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false \
    STREAMLIT_SERVER_ENABLECORS=false \
    STREAMLIT_SERVER_ENABLEXSRFPROTECTION=false \
    STREAMLIT_SERVER_FILE_WATCHER_TYPE=poll

EXPOSE 8501

# Default CMD — overridden per service in docker-compose.yml
CMD ["python", "main.py"]