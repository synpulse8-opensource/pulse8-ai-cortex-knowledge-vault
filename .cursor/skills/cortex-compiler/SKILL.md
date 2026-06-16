---
name: cortex-compiler
description: >-
  Cortex raw-to-wiki compiler — ingest, compile, bulk-ingest, manifests, LLM
  compilation. Use for ingestion pipelines, bulk.py, or compile endpoints.
---

# Cortex compiler

## Pipeline overview

```
raw/  →  Compiler (LLM)  →  wiki/*.md  →  graph + QMD index
```

## Key modules

| Module | Role |
|--------|------|
| `cortex/compiler/compiler.py` | Single-file compile |
| `cortex/compiler/bulk.py` | Recursive directory scan, concurrency, manifests |
| `cortex/compiler/prompts.py` | LLM prompts |
| `cortex/mcp/tools.py` | `vault_ingest`, `vault_compile` |

## Manifests (under `.cortex/`)

- `ingest-manifest.json` — SHA-256 of successfully compiled raw files (skip on re-run unless `force`)
- `ingest-skip-manifest.json` — failures and skips

## REST endpoints

| Endpoint | Behavior |
|----------|----------|
| `POST /api/v1/ingest` | JSON content → `raw/` |
| `POST /api/v1/ingest/upload` | Multipart upload |
| `POST /api/v1/compile` | Async compile all pending (202) |
| `GET /api/v1/compile/status` | Job status |
| `POST /api/v1/bulk-ingest` | Scan `source_dir` on **server** filesystem |

### Bulk ingest body

```json
{
  "source_dir": "/ingest",
  "concurrency": 4,
  "force": false,
  "dry_run": false
}
```

Logs (`cortex.compiler.bulk`): `Scanning source directory`, per-file progress. Also logged from `cortex.api.routes` on request receipt.

**Recursive scan:** `source_dir` is walked recursively; subfolder structure is preserved under the vault raw dir (e.g. `source_dir/abcde/a.html` → `{VAULT_RAW_DIR}/abcde/a.html`).

**Common failure:** `source_dir` not mounted in container → 400 before bulk runs.

## MCP

- `vault_ingest` — write bytes to `raw/`
- `vault_compile` — trigger compile pass

## Config

LLM provider settings in `cortex/config.py` (model, API keys via env). See `.env.example`.

## Related skills

- Vault layout: `cortex-vault`
- Deploy `/ingest` mount: `cortex-deploy`
- API details: `cortex-api`
