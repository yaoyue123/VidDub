# =============================================================================
# You2Bili — Multi-stage Docker build
# =============================================================================
# Usage:
#   docker compose up --build
#
# Stages:
#   1. python-base: common Python layer
#   2. backend-builder: install pip deps + Playwright Chromium
#   3. frontend-builder: npm install + npm run build
#   4. runtime: final image with backend + frontend dist
# =============================================================================

# ── Stage 1: Python base ──
FROM python:3.11-slim AS python-base

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ── Stage 2: Backend builder ──
FROM python-base AS backend-builder

COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

# Install Playwright Chromium
RUN python -m playwright install chromium && \
    python -m playwright install-deps chromium

COPY backend/ /app/backend/

# ── Stage 3: Frontend builder ──
FROM node:20-slim AS frontend-builder

WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# ── Stage 4: Runtime ──
FROM python-base AS runtime

# Copy backend from builder
COPY --from=backend-builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=backend-builder /usr/local/bin /usr/local/bin
COPY --from=backend-builder /app/backend /app/backend
COPY --from=backend-builder /root/.cache/ms-playwright /root/.cache/ms-playwright

# Copy frontend dist
COPY --from=frontend-builder /app/frontend/dist /app/frontend/dist

WORKDIR /app/backend

# Expose ports
EXPOSE 8000

# Default: start backend only
# Frontend should be served via nginx or accessed at :5173 in dev mode
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
