#!/usr/bin/env bash
set -e
export PYTHONPATH=/app:${PYTHONPATH}
echo "[gti] starting GTI Control (Ingress UI)"
exec uvicorn server:app --host 0.0.0.0 --port 8099