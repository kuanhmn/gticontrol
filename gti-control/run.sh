#!/bin/sh
set -e
export PYTHONPATH=/app:${PYTHONPATH}
echo "[gti] starting GTI Control (Ingress UI)"
exec uvicorn server:app --host 0.0.0.0 --port 8099
COPY run.sh /run.sh
RUN sed -i 's/\r$//' /run.sh && chmod a+x /run.sh