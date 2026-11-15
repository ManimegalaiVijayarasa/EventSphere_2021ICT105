#!/bin/bash
set -e

cd /home/uppcoder/app

PYTHON="/home/uppcoder/app/.pixi/envs/web-fastapi/bin/python"

# Install dependencies into the environment used by EventSphere
"$PYTHON" -m pip install -r requirements.txt

# Start EventSphere
exec "$PYTHON" -m uvicorn main:app \
    --host 0.0.0.0 \
    --port "${APP_PORT:-8000}"
