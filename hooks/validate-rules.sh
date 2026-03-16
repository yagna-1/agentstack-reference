#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RULES_PATH="$ROOT_DIR/RULES.md"
POLICY_PATH="$ROOT_DIR/examples/policy/agentstack-platform.yaml"
DERIVED_PATH="/tmp/agentstack-derived-policy.yaml"

python3 "$ROOT_DIR/scripts/rules_to_policy.py" "$RULES_PATH" > "$DERIVED_PATH"
diff -u "$DERIVED_PATH" "$POLICY_PATH" > /tmp/agentstack-policy-diff.txt || {
  echo "ERROR: RULES.md and agentstack-platform policy YAML are out of sync." >&2
  cat /tmp/agentstack-policy-diff.txt >&2
  exit 1
}

echo "RULES.md and policy YAML are in sync."
