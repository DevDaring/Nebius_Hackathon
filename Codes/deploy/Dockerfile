# NemoTwins single-container image for Nebius AI Serverless endpoints (and any container host).
# One process serves the SPA and /api on port 8000. No secrets are baked in: TOKENFACTORY_2009_API_KEY,
# JWT_SECRET and DATABASE_URL are injected at runtime (Nebius MysteryBox via --env-secret).
# Build from the repository root:  docker build -f deploy/Dockerfile -t nemotwins:local .

# ---------- 1) frontend build
FROM node:20.18.1-alpine3.20 AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
ENV VITE_MOCK=0
RUN npm run build

# ---------- 2) API runtime
FROM python:3.12.8-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app \
    OMP_NUM_THREADS=2 \
    MPLBACKEND=Agg \
    STATIC_DIR=/app/static \
    APP_ENVIRONMENT=nebius

# libgomp1: OpenMP runtime for LightGBM.
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*
WORKDIR /app

# Pinned dependencies (tested versions), then the code.
COPY backend/requirements.lock ./requirements.lock
RUN pip install -r requirements.lock

COPY backend/nemotwins ./nemotwins
COPY backend/artifacts ./artifacts
COPY backend/reports ./reports
COPY backend/fixtures ./fixtures
COPY backend/capabilities ./capabilities
COPY backend/data/food ./data/food
COPY --from=web /web/dist ./static

ARG GIT_COMMIT=""
ENV GIT_COMMIT=${GIT_COMMIT}

RUN useradd --create-home --uid 10001 app \
    && mkdir -p artifacts/persona_states data/cache/runtime \
    && chown -R app:app artifacts data/cache
USER app

EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=60s --retries=10 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).status == 200 else 1)"

# One worker: per-user rate limits and forecast ownership are in-process; the engine is memory-heavy.
# uvicorn handles SIGTERM gracefully (finishes in-flight requests).
CMD ["uvicorn", "nemotwins.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", \
     "--proxy-headers", "--forwarded-allow-ips", "*", "--timeout-graceful-shutdown", "20"]
