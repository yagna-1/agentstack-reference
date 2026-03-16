#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RULES_PATH="$ROOT_DIR/RULES.md"
POLICY_PATH="$ROOT_DIR/examples/policy/agentstack-platform.yaml"

if [[ ! -f "$RULES_PATH" || ! -f "$POLICY_PATH" ]]; then
  echo "Missing RULES.md or policy YAML." >&2
  exit 1
fi

python3 "$ROOT_DIR/scripts/rules_to_policy.py" "$RULES_PATH" > /tmp/agentstack-derived-policy.yaml
if ! diff -u /tmp/agentstack-derived-policy.yaml "$POLICY_PATH" > /tmp/agentstack-policy-diff.txt; then
  echo "RULES.md and policy YAML are out of sync." >&2
  cat /tmp/agentstack-policy-diff.txt >&2
  exit 1
fi

echo "pre-demo: RULES and policy are in sync"
