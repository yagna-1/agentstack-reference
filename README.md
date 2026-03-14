# agentstack-reference

Glue-only reference repository for wiring five existing services together:

- NexusGate
- FluxRoute
- AstraGraph
- Recast
- mcp-test

This repo contains only orchestration assets:

- `docker-compose.yml`
- sample manifest and policy files
- shell scripts for bootstrap/run/compile

No application code is implemented here.

## Quickstart

```bash
./scripts/bootstrap.sh
cp .env.example .env
./scripts/run.sh
```

## What You Get

- routed MCP call through NexusGate -> AstraGraph proxy
- workflow execution via FluxRoute
- AstraGraph-compatible audit JSON from FluxRoute
- Playwright TS/PY tests generated from audit via Recast
- mcp-test policy assertion helper tests runnable via tools profile

## Useful Commands

```bash
docker compose up -d --build
docker compose down
./scripts/audit_to_tests.sh
docker compose --profile tools run --rm mcp-test
```
