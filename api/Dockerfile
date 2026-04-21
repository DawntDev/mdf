# syntax=docker/dockerfile:1.7
# -----------------------------------------------------------------------------
# MDF Dictionary Extractor — API image
# -----------------------------------------------------------------------------
# Python 3.12 slim + Tesseract OCR (spa + eng packs) so the OCR fallback
# works out of the box for image-based PDFs.
# -----------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# System dependencies:
#   * tesseract-ocr + spa/eng language packs for the automatic OCR fallback.
#   * libgl1 / libglib2.0-0 are required by Pillow for some rasterization paths.
#   * build-essential is kept minimal; PyMuPDF ships manylinux wheels so no
#     C toolchain is needed at install time.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        tesseract-ocr \
        tesseract-ocr-spa \
        tesseract-ocr-eng \
        libgl1 \
        libglib2.0-0 \
        curl \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first so the layer cache survives source edits.
COPY requirements.txt ./
RUN pip install --upgrade pip \
 && pip install -r requirements.txt

# Application source
COPY . .

# Non-root user (principle of least privilege).
RUN useradd --create-home --shell /bin/bash appuser \
 && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# Healthcheck hits the dedicated /api/v1/health endpoint.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -fsS http://localhost:8000/api/v1/health || exit 1

# Uvicorn is pulled in transitively by fastapi[standard]. We bind to 0.0.0.0
# so the container is reachable on the compose network.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
