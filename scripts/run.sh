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

wait_for_proxy_mcp_ready() {
  local proxy_url="$1"
  local max_attempts="${2:-300}"
  local payload='{"jsonrpc":"2.0","id":"proxy-ready","method":"tools/call","params":{"name":"safe_tool","arguments":{"thinking":"readiness-check"}}}'
  local i code
  for ((i=1; i<=max_attempts; i++)); do
    code="$(curl -sS -o /tmp/agentstack-proxy-ready.json -w "%{http_code}" \
      -X POST "$proxy_url" \
      -H 'Content-Type: application/json' \
      -d "$payload" || true)"
    if [[ "$code" == "200" ]]; then
      return 0
    fi
    sleep 1
  done
  echo "Timed out waiting for AstraGraph proxy MCP readiness" >&2
  return 1
}

post_json_with_retry() {
  local output_path="$1"
  local max_attempts="$2"
  shift 2
  local i
  for ((i=1; i<=max_attempts; i++)); do
    if curl -fsS "$@" > "$output_path"; then
      return 0
    fi
    sleep 1
  done
  echo "Timed out waiting for successful POST: $*" >&2
  return 1
}

post_no_output_with_retry() {
  local max_attempts="$1"
  shift
  local i
  for ((i=1; i<=max_attempts; i++)); do
    if curl -fsS "$@" >/dev/null; then
      return 0
    fi
    sleep 1
  done
  echo "Timed out waiting for successful POST: $*" >&2
  return 1
}

ASTRAGRAPH_MODE="${AGENTSTACK_ASTRAGRAPH_MODE:-mock}"
case "$ASTRAGRAPH_MODE" in
  mock)
    ASTRAGRAPH_SERVICES=(astragraph-proxy-mock)
    PROXY_HEALTH_URL="http://localhost:17070/mcp/tools/call"
    unset MCP_UPSTREAM_URL_OVERRIDE
    ;;
  real)
    ASTRAGRAPH_SERVICES=(graph policy verifier astragraph-proxy)
    PROXY_HEALTH_URL="http://localhost:17071/mcp/tools/call"
    export MCP_UPSTREAM_URL_OVERRIDE="http://astragraph-proxy:7070"
    ;;
  *)
    echo "Invalid AGENTSTACK_ASTRAGRAPH_MODE='$ASTRAGRAPH_MODE'. Use 'mock' or 'real'." >&2
    exit 1
    ;;
esac

docker compose up -d --build \
  redis mock-mcp otel-collector "${ASTRAGRAPH_SERVICES[@]}" \
  nexusgate fluxroute-router fluxroute-controlplane

wait_for_url "http://localhost:18088/health"
wait_for_url "http://localhost:18090/healthz"
if [[ "$ASTRAGRAPH_MODE" == "real" ]]; then
  wait_for_url "http://localhost:18080/graphs" 900
  wait_for_url "http://localhost:18081/policies" 900
fi
wait_for_proxy_mcp_ready "$PROXY_HEALTH_URL" 900

ADMIN_TOKEN="$(curl -fsS -X POST http://localhost:18088/admin/token \
  -H 'Content-Type: application/json' \
  -d "{\"secret\":\"$ADMIN_SECRET\"}" | \
  python3 -c 'import json,sys; print(json.load(sys.stdin)["token"])')"

API_KEY="$(curl -fsS -X POST http://localhost:18088/admin/keys \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"name":"agentstack-demo","budget_workflow_daily_usd":5,"budget_workflow_monthly_usd":100}' | \
  python3 -c 'import json,sys; print(json.load(sys.stdin)["key"])')"

post_json_with_retry "$ROOT_DIR/examples/weather-agent/output/nexusgate-mcp-response.json" 45 \
  -X POST http://localhost:18088/mcp/tools/call \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -H "X-Workflow-ID: weather-agent" \
  -d '{"jsonrpc":"2.0","id":"wf-weather-1","method":"tools/call","params":{"name":"safe_tool","arguments":{"city":"Pune"}}}'

post_no_output_with_retry 30 \
  -X POST http://localhost:18090/v1/run \
  -H 'Content-Type: application/json' \
  -d '{"manifest_path":"/workspace/examples/weather-agent/manifest.yaml"}'

sleep 2

"$ROOT_DIR/scripts/audit_to_tests.sh"

echo "Artifacts ready in examples/weather-agent/output/"
