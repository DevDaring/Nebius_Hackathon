# NemoTwins API image (docker compose). Runs fully offline (APP_MODE=demo) with an empty .env.
# Contains code + small artefacts, reports, fixtures and the Indian food table; the raw and
# processed research datasets are NOT included (the demo replays artifacts/demo_*.parquet).
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app \
    OMP_NUM_THREADS=2 \
    MPLBACKEND=Agg \
    APP_MODE=demo

# libgomp1: OpenMP runtime needed by LightGBM.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 1) Dependencies only (cached layer): read them from pyproject.toml.
COPY pyproject.toml ./
RUN python - <<'PY' > /tmp/requirements.txt
import tomllib
print("\n".join(tomllib.load(open("pyproject.toml", "rb"))["project"]["dependencies"]))
PY
RUN pip install -r /tmp/requirements.txt

# 2) Code and runtime data. The package is used from /app (PYTHONPATH) so that
#    nemotwins/config.py resolves artifacts/, reports/, fixtures/ and data/ next to it.
COPY nemotwins ./nemotwins
COPY artifacts ./artifacts
COPY reports ./reports
COPY fixtures ./fixtures
COPY data/food ./data/food

RUN useradd --create-home --uid 10001 app \
    && mkdir -p artifacts/persona_states fixtures/audio data/cache/tts data/cache/runtime \
    && chown -R app:app artifacts fixtures data/cache
USER app

EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=5s --start-period=40s --retries=12 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).status == 200 else 1)"

CMD ["uvicorn", "nemotwins.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
