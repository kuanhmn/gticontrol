#!/bin/sh
set -e
export PYTHONPATH=/app:${PYTHONPATH}
echo "[gti] starting GTI Control (uvicorn) on 0.0.0.0:8099"
exec /opt/venv/bin/python -m uvicorn server:app \
    --host 0.0.0.0 \
    --port 8099 \
    --reload \
    --log-level debug
