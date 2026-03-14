#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

AUDIT_HOST_PATH="${1:-$ROOT_DIR/examples/weather-agent/output/astragraph-audit.json}"
if [[ ! -f "$AUDIT_HOST_PATH" ]]; then
  echo "Audit file not found: $AUDIT_HOST_PATH" >&2
  exit 1
fi

if [[ "$AUDIT_HOST_PATH" != "$ROOT_DIR"/* ]]; then
  echo "Audit path must be inside the repo" >&2
  exit 1
fi

AUDIT_CONTAINER_PATH="/workspace/${AUDIT_HOST_PATH#"$ROOT_DIR/"}"
OUT_TS_CONTAINER="/workspace/examples/weather-agent/output/playwright-ts"
OUT_PY_CONTAINER="/workspace/examples/weather-agent/output/playwright-py"
mkdir -p "$ROOT_DIR/examples/weather-agent/output/playwright-ts" "$ROOT_DIR/examples/weather-agent/output/playwright-py"

docker compose run --rm recast compile --from astragraph-audit "$AUDIT_CONTAINER_PATH" -t playwright-ts -o "$OUT_TS_CONTAINER"
docker compose run --rm recast compile --from astragraph-audit "$AUDIT_CONTAINER_PATH" -t playwright-py -o "$OUT_PY_CONTAINER"
