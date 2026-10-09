#!/usr/bin/env bash
# Install / update NemoTwins into a host directory (default /home/Debz/Host/nemotwins):
#   backend code + artefacts + reports  -> $TARGET/backend   (FastAPI on 127.0.0.1:$PORT, see run.sh)
#   frontend production build           -> $TARGET/web       (served by Caddy)
# Secrets live only in $TARGET/.env (created once by hand from env.example; never in this repo).
#   deploy/selfhost/install.sh            # from the Codes/ folder of the repository
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TARGET="${TARGET:-/home/Debz/Host/nemotwins}"
mkdir -p "$TARGET/backend/data" "$TARGET/web" "$TARGET/logs"
rsync -a --delete --exclude '__pycache__' --exclude '*.pyc' \
  "$ROOT/backend/nemotwins" "$ROOT/backend/artifacts" "$ROOT/backend/reports" "$ROOT/backend/fixtures" \
  "$ROOT/backend/capabilities" "$ROOT/backend/pyproject.toml" "$ROOT/backend/requirements.lock" "$TARGET/backend/"
rsync -a --delete "$ROOT/backend/data/food" "$TARGET/backend/data/"
if [[ "${SKIP_WEB:-0}" != "1" ]]; then
  (cd "$ROOT/frontend" && { [[ -d node_modules ]] || npm ci --no-audit --no-fund; } && VITE_MOCK=0 npm run build)
  rsync -a --delete "$ROOT/frontend/dist/" "$TARGET/web/"
fi
install -m 755 "$ROOT/deploy/selfhost/run.sh" "$ROOT/deploy/selfhost/stop.sh" "$ROOT/deploy/selfhost/autostart.sh" "$TARGET/"
[[ -f "$TARGET/.env" ]] || { install -m 600 "$ROOT/deploy/selfhost/env.example" "$TARGET/.env";
  echo "Created $TARGET/.env from env.example - fill in the secrets, then run $TARGET/run.sh"; }
echo "installed into $TARGET (git $(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || echo '?'))"
