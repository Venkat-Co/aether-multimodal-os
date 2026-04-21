#!/usr/bin/env sh
set -eu

exec uvicorn "$SERVICE_MODULE" --host 0.0.0.0 --port "$SERVICE_PORT"

