#!/usr/bin/env bash
# NemoTwins - (re)start the API on 127.0.0.1:8150. Caddy serves web/ and proxies /api.
set -e
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PORT="${PORT:-8150}"
PY="${PY:-python3.12}"
cd "$APP_DIR"
"$APP_DIR/stop.sh" >/dev/null 2>&1 || true
mkdir -p logs
# PYTHONPATH pins the installed copy in $APP_DIR/backend; settings are read from $APP_DIR/.env.
setsid bash -c "cd '$APP_DIR/backend' && export PYTHONPATH='$APP_DIR/backend' OMP_NUM_THREADS=2 MPLBACKEND=Agg && exec $PY -m uvicorn nemotwins.api.main:app --host 127.0.0.1 --port $PORT --workers 1 --proxy-headers --forwarded-allow-ips=127.0.0.1 --timeout-graceful-shutdown 20" \
  >> logs/api.log 2>&1 < /dev/null &
echo $! > logs/api.pid
for i in $(seq 1 90); do curl -sf "http://127.0.0.1:$PORT/api/health" >/dev/null && { echo "nemotwins up on 127.0.0.1:$PORT"; exit 0; }; sleep 1; done
echo "nemotwins did not become healthy; see logs/api.log" >&2; exit 1
