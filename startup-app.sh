#!/bin/bash
set -e

cd /home/uppcoder/app

exec /home/uppcoder/app/.pixi/envs/web-fastapi/bin/python \
    -m uvicorn main:app \
    --host 0.0.0.0 \
    --port "${APP_PORT:-8000}"
