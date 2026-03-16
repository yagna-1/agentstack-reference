#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="$ROOT_DIR/examples/weather-agent/output"
MEM_DIR="$ROOT_DIR/memory"
TIMESTAMP="$(date -u +"%Y%m%dT%H%M%SZ")"

mkdir -p "$MEM_DIR/astragraph-audits" "$MEM_DIR/fluxroute-traces" "$MEM_DIR/recast-tests"

AUDIT_SRC="$OUT_DIR/astragraph-audit.json"
TRACE_SRC="$OUT_DIR/nexusgate-mcp-response.json"

if [[ -f "$AUDIT_SRC" ]]; then
  cp "$AUDIT_SRC" "$MEM_DIR/astragraph-audits/${TIMESTAMP}-weather-agent-audit.json"
fi

if [[ -f "$TRACE_SRC" ]]; then
  cp "$TRACE_SRC" "$MEM_DIR/fluxroute-traces/${TIMESTAMP}-weather-agent-trace.json"
fi

if [[ -d "$OUT_DIR/playwright-ts" ]]; then
  rsync -a --delete "$OUT_DIR/playwright-ts/" "$MEM_DIR/recast-tests/playwright-ts/"
fi
if [[ -d "$OUT_DIR/playwright-py" ]]; then
  rsync -a --delete "$OUT_DIR/playwright-py/" "$MEM_DIR/recast-tests/playwright-py/"
fi

cat >> "$MEM_DIR/key-decisions.md" <<EOT

## ${TIMESTAMP}  workflow:weather-agent  skill:demo
- Audit: memory/astragraph-audits/${TIMESTAMP}-weather-agent-audit.json
- Trace: memory/fluxroute-traces/${TIMESTAMP}-weather-agent-trace.json
- Tests: memory/recast-tests/
EOT

if [[ -n "$(git -C "$ROOT_DIR" status --porcelain -- memory)" ]]; then
  git -C "$ROOT_DIR" add memory
  git -C "$ROOT_DIR" commit -m "agent: post-demo audit + tests committed [weather-agent-${TIMESTAMP}]" || true
fi

echo "post-demo: memory artifacts updated"
