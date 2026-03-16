#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="policy-change-$(date +%Y%m%d-%H%M%S)"
REVIEWER="${POLICY_REVIEWER:-}"

cd "$ROOT_DIR"
git checkout -b "$BRANCH"
git add RULES.md examples/policy/agentstack-platform.yaml
git commit -m "policy: update $(date -u +%Y-%m-%d)"
git push origin "$BRANCH"

if command -v gh >/dev/null 2>&1; then
  BODY="RULES.md updated. Generated policy YAML kept in sync. Human review required before merge."
  if [[ -n "$REVIEWER" ]]; then
    gh pr create --title "Policy change: requires human review" --body "$BODY" --reviewer "$REVIEWER"
  else
    gh pr create --title "Policy change: requires human review" --body "$BODY"
  fi
else
  echo "gh CLI not found. Open a PR for branch: $BRANCH"
fi
