#!/usr/bin/env sh
set -eu

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$ROOT_DIR"

RUN_DEMO=0
if [ "${1:-}" = "--demo" ]; then
  RUN_DEMO=1
fi

if ! docker info >/dev/null 2>&1; then
  printf 'Docker daemon is not running. Start Docker Desktop (or another Docker daemon) and rerun this script.\n' >&2
  exit 1
fi

wait_for() {
  name="$1"
  url="$2"
  attempts="${3:-120}"
  i=1
  while [ "$i" -le "$attempts" ]; do
    if curl -fsS "$url" >/dev/null 2>&1; then
      printf '%s is ready at %s\n' "$name" "$url"
      return 0
    fi
    sleep 2
    i=$((i + 1))
  done
  printf 'Timed out waiting for %s at %s\n' "$name" "$url" >&2
  return 1
}

docker compose up -d --build

wait_for "Ingestion" "http://localhost:8001/healthz"
wait_for "Fusion" "http://localhost:8002/healthz"
wait_for "Memory" "http://localhost:8003/healthz"
wait_for "Reasoning" "http://localhost:8004/healthz"
wait_for "Governance" "http://localhost:8005/healthz"
wait_for "Action" "http://localhost:8006/healthz"
wait_for "Realtime" "http://localhost:8007/healthz"
wait_for "Kernel" "http://localhost:8008/healthz"
wait_for "Dashboard" "http://localhost:3000"

printf '\nAETHER is up.\n'
printf 'Dashboard: http://localhost:3000\n'
printf 'Kernel docs: http://localhost:8008/docs\n'
printf 'Grafana: http://localhost:3001\n'
printf 'Prometheus: http://localhost:9090\n'
printf 'Jaeger: http://localhost:16686\n'

if [ "$RUN_DEMO" -eq 1 ]; then
  printf '\nTriggering the end-to-end demo pipeline...\n'
  "$ROOT_DIR/scripts/demo-local.sh"
fi
