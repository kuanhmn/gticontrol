#!/usr/bin/env bash
set -e
export PYTHONUNBUFFERED=1
cd /app
echo "[gti] starting GTI Control (Ingress UI)"
uvicorn server:app --host 0.0.0.0 --port 8099
