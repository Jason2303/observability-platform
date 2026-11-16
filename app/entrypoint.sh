#!/bin/sh
# loadgen runs the client loop; every other role is served by gunicorn.
# 1 worker + threads: keeps prometheus_client in single-process mode.
set -e
if [ "$SERVICE_NAME" = "loadgen" ]; then
  exec python /srv/app.py
fi
exec gunicorn --bind 0.0.0.0:8080 --workers 1 --threads 8 app:app
