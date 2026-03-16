# RULES.md - AgentStack Platform

## Enforced rules (AstraGraph policy: agentstack-platform)

- Every governed workflow must include a workflow_id.
- Policy enforcement is fail-closed for all restricted actions.
- Audit artifacts must be written to memory/ after each demo run.
- Test compilation from audit artifacts must be deterministic.

## Human review required (PR, not direct commit)

- Any policy threshold relaxation.
- Any change to RULES.md that alters enforcement behavior.
- Any bypass to mandatory audit export or memory commit steps.

## Auto-blocked (AstraGraph fail-closed)

- Workflow execution without workflow_id.
- Requests that bypass policy verification.
- Attempts to run demo flow when RULES.md and policy YAML diverge.
