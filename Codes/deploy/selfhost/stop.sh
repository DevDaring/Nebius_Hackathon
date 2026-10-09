#!/usr/bin/env bash
# Stop only the NemoTwins API (matches its module and port).
PORT="${PORT:-8150}"
for p in $(ps -eo pid,args | awk -v port="--port $PORT" '/uvicorn nemotwins.api.main:app/ && index($0, port) && !/awk/ {print $1}'); do kill "$p"; done
