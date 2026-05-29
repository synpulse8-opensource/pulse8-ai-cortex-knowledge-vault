---
name: cortex-deploy
description: >-
  Cortex deployment — Docker Compose, env_check.sh, CORTEX_* env vars, EC2/rsync,
  logs. Use for production setup, container config, or server debugging.
---

# Cortex deploy

## Quick start

```bash
./scripts/env_check.sh    # interactive .env generation
docker compose up -d
curl http://localhost:8420/api/v1/health
```

## Docker Compose (`docker-compose.yml`)

| Service | Port | Notes |
|---------|------|-------|
| `cortex` | 8420 | API + MCP HTTP |
| volumes | `vault`, optional `/ingest` | `CORTEX_VAULT_PATH`, bulk source dir |

Env mapping uses `CORTEX_` prefix in compose (e.g. `CORTEX_TEAMS_WEBHOOK_URL`, `CORTEX_API_KEY`).

## Environment dual naming

Settings accept **either**:

- `VAULT_PATH` or `CORTEX_VAULT_PATH`
- `API_KEY` or `CORTEX_API_KEY`
- `TEAMS_WEBHOOK_URL` or `CORTEX_TEAMS_WEBHOOK_URL`

`scripts/env_check.sh` writes unprefixed names; compose often maps to `CORTEX_*`.

## Production sync (example)

```bash
rsync -avz -e "ssh -i ~/.ssh/key" ./vault/ user@host:~/vault/
ssh user@host 'cd app && docker compose restart cortex'
```

Host paths in bulk-ingest must exist **inside** the container (mount at `/ingest`).

## Logs

```bash
docker logs cortex 2>&1 | tail -100
# Access lines → stdout (uvicorn.access)
# App logs → stderr (cortex.*)
```

## Health checks

- `GET /api/v1/health`
- Graph: `GET /api/v1/graph/stats` (with auth if enabled)

## Teams notifications

Optional `TEAMS_WEBHOOK_URL` + `TEAMS_APP_BASE_URL` for feedback cards (`cortex/notify/teams.py`). Validated in `env_check.sh`.

## Related skills

- Auth: `cortex-auth`
- Compiler bulk paths: `cortex-compiler`
