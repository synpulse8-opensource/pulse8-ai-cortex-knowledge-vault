# AGENTS.md — PULSE8.ai Cortex

Agent-native knowledge OS on Markdown: typed graph (NetworkX), full-text search (QMD), MarkItDown compiler, MCP + REST. **No database** — everything is files under the vault directory.

## Repository map

| Path | Purpose |
|------|---------|
| `cortex/` | Python application (FastAPI, MCP, graph, search, compiler, auth) |
| `scripts/` | `start.sh`, `stop.sh`, `serve.py`, `bulk_ingest.sh`, `env_check.sh` |
| `docker/` | QMD container (`docker/qmd/`) |
| `tests/` | Pytest suite |
| `example_vault/` | Sample vault for local dev |
| `docs/` | Deployment guides, design specs |
| `.cursor/skills/` | Project Cursor skills (load for deep workflows) |

## Environment variables

Two naming layers:

| Layer | Example | Used by |
|-------|---------|---------|
| `.env` / Compose | `VAULT_DIR`, `VAULT_RAW_DIR`, `VAULT_WIKI_DIR`, `LLM_API_KEY`, `AUTH_METHOD` | `scripts/start.sh`, `docker-compose.yml` |
| Python `CORTEX_*` | `CORTEX_VAULT_PATH`, `CORTEX_VAULT_RAW_DIR`, `CORTEX_VAULT_WIKI_DIR`, `CORTEX_LLM_API_KEY` | `cortex/config.py` (`CortexSettings`) |

`scripts/env_check.sh` applies defaults, resolves `CORTEX_*` aliases, and writes `.env` for Docker.

See `.env.example` and `cortex/config.py` for the full list. Never commit `.env` or secrets.

## Essential commands

```bash
# Dependencies
uv sync --all-extras

# Start stack (QMD + Cortex)
./scripts/start.sh
./scripts/stop.sh

# Cortex only (external QMD)
./scripts/start.sh --cortex-only

# Dev server without Docker
CORTEX_MCP_TRANSPORT=http CORTEX_VAULT_PATH=./example_vault uv run python scripts/serve.py

# Tests
uv run pytest tests/ -v

# Bulk ingest (no server required)
./scripts/bulk_ingest.sh ./my-papers/
```

## Network endpoints

| Service | URL |
|---------|-----|
| Cortex REST | `http://localhost:8420/api/v1/` |
| Cortex MCP | `http://localhost:8420/mcp/` |
| QMD search | `http://localhost:3100/` |
| OpenAPI | `http://localhost:8420/docs` |

## Cursor skills

Load the **master** skill first, then the sub-skill for your task:

| Skill | When to load |
|-------|----------------|
| `cortex` | Any work in this repo; routes to sub-skills |
| `cortex-deploy` | Docker, EC2, `start.sh`, logs, production ops |
| `cortex-vault` | Vault folders, notes, frontmatter, `.cortex/` |
| `cortex-mcp` | MCP tools, Cursor/Claude Desktop, streamable HTTP |
| `cortex-api` | REST endpoints, curl, FastAPI routes |
| `cortex-compiler` | Ingest, compile, bulk ingest, manifests |
| `cortex-graph-search` | Graph edges, QMD search, `vault_context` |
| `cortex-auth` | API key, Entra ID OIDC, JWT |
| `cortex-feedback` | Feedback notes, Teams notifications |
| `cortex-contributing` | Python changes, tests, new MCP tools |

## Documentation

- [README.md](README.md) — user-facing setup and features
- [.env.example](.env.example) — configuration template
- [docs/ec2-gpu-setup.md](docs/ec2-gpu-setup.md) — GPU production on EC2
- [docs/superpowers/specs/2026-05-29-cursor-skills-design.md](docs/superpowers/specs/2026-05-29-cursor-skills-design.md) — skills pack design

## Conventions for agents

- Prefer **minimal, focused diffs**; match existing patterns in `cortex/`.
- REST and MCP share handlers in `cortex/mcp/tools.py` — keep behavior in sync.
- Vault paths are relative to vault root (e.g. `wiki/foo.md`, not absolute paths).
- Do not commit `.env`, API keys, or webhook URLs.
