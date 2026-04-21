#!/usr/bin/env sh
set -eu

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$ROOT_DIR"

if ! curl -fsS "http://localhost:8008/healthz" >/dev/null 2>&1; then
  printf 'Kernel service is not reachable on http://localhost:8008. Start the stack first with ./scripts/start-local.sh.\n' >&2
  exit 1
fi

curl -fsS -X POST "http://localhost:8008/api/v1/kernel/pipeline/demo" \
  -H "Content-Type: application/json" | python3 -m json.tool
