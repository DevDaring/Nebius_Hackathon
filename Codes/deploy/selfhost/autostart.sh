#!/usr/bin/env bash
# NemoTwins watchdog - idempotent: starts the API only if nothing listens on its port (cron: @reboot and */5).
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PORT="${PORT:-8150}"
[ -x "$APP_DIR/run.sh" ] || exit 0
ss -tln 2>/dev/null | grep -q ":$PORT " && exit 0
mkdir -p "$APP_DIR/logs"
echo "$(date -Is) autostart: starting nemotwins" >> "$APP_DIR/logs/autostart.log"
"$APP_DIR/run.sh" >> "$APP_DIR/logs/autostart.log" 2>&1
