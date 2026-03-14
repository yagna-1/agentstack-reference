#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ ! -d "$ROOT_DIR/deps/nexusgate/.git" ]]; then
  echo "Dependencies not found. Run ./scripts/bootstrap.sh first." >&2
  exit 1
fi

mkdir -p "$ROOT_DIR/examples/weather-agent/output"

ADMIN_SECRET="${ADMIN_JWT_SECRET:-agentstack-local-admin-secret-change-me-123456}"
export ADMIN_JWT_SECRET="$ADMIN_SECRET"

wait_for_url() {
  local url="$1"
  local max_attempts="${2:-60}"
  local i
  for ((i=1; i<=max_attempts; i++)); do
    if curl -fsS "$url" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  echo "Timed out waiting for $url" >&2
  return 1
}

docker compose up -d --build \
  redis mock-mcp otel-collector graph policy verifier astragraph-proxy \
  nexusgate fluxroute-router fluxroute-controlplane

wait_for_url "http://localhost:18088/health"
wait_for_url "http://localhost:18090/healthz"

ADMIN_TOKEN="$(curl -fsS -X POST http://localhost:18088/admin/token \
  -H 'Content-Type: application/json' \
  -d "{\"secret\":\"$ADMIN_SECRET\"}" | \
  python3 -c 'import json,sys; print(json.load(sys.stdin)["token"])')"

API_KEY="$(curl -fsS -X POST http://localhost:18088/admin/keys \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"name":"agentstack-demo","budget_workflow_daily_usd":5,"budget_workflow_monthly_usd":100}' | \
  python3 -c 'import json,sys; print(json.load(sys.stdin)["key"])')"

curl -fsS -X POST http://localhost:18088/mcp/tools/call \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -H "X-Workflow-ID: weather-agent" \
  -d '{"jsonrpc":"2.0","id":"wf-weather-1","method":"tools/call","params":{"name":"safe_tool","arguments":{"city":"Pune"}}}' \
  > "$ROOT_DIR/examples/weather-agent/output/nexusgate-mcp-response.json"

curl -fsS -X POST http://localhost:18090/v1/run \
  -H 'Content-Type: application/json' \
  -d '{"manifest_path":"/workspace/examples/weather-agent/manifest.yaml"}' >/dev/null

sleep 2

"$ROOT_DIR/scripts/audit_to_tests.sh"

echo "Artifacts ready in examples/weather-agent/output/"
