#!/usr/bin/env sh
set -eu

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$ROOT_DIR"

if ! docker info >/dev/null 2>&1; then
  printf 'Docker daemon is not running. Nothing to stop through Docker Compose.\n' >&2
  exit 1
fi

docker compose down
