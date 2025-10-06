#!/bin/sh
set -e
export PYTHONPATH=/app:${PYTHONPATH}
echo "[gti] starting GTI Control (Ingress UI)"
exec /opt/venv/bin/python -m uvicorn server:app --host 0.0.0.0 --port 8099