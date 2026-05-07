# Bulk Ingest from Trusted Local Storage

**Status:** Completed  
**Created:** 2026-05-07  
**Completed:** 2026-05-07

## Problem

Ingesting files via MCP means: send content through the MCP wire one file at a time, then trigger compile one file at a time. For a large dataset (dozens or hundreds of PDFs, papers, docs) sitting on a local disk already mounted into Docker, this is painfully slow and unnecessary.

## Current State

| What exists | Where | Limitation |
|---|---|---|
| `vault_ingest` MCP tool | `cortex/mcp/tools.py` | One file at a time, transfers content over wire |
| `scripts/compile.py` | CLI script | Only compiles, no copy-from-source; has the old compile-flag bug (doesn't check `enrichment_status`) |
| `scripts/reindex.py` | CLI script | Rebuilds graph + QMD, no ingest |
| Docker volume mount | `docker-compose.yml` | Vault at `/vault`, but no "inbox" mount |

## Proposed Solution: `cortex bulk-ingest` CLI command

A new CLI command that:

1. **Reads from a trusted local directory** (mounted or local) — no MCP wire overhead
2. **Copies files into `raw/`** — only if they're not already there (dedup by content hash)
3. **Compiles in batch** — with concurrency control and progress reporting
4. **Rebuilds graph + QMD index once** at the end — not per-file

## Architecture

```
Local storage (/data/papers/)          Vault (/vault/)
┌─────────────────────┐                ┌──────────────────┐
│ paper1.pdf          │  ── copy ──►   │ raw/paper1.pdf   │
│ paper2.docx         │  (skip dups)   │ raw/paper2.docx  │
│ notes.md            │                │ raw/notes.md     │
└─────────────────────┘                └──────────────────┘
                                              │
                                     ingest_source() × N
                                     (concurrency=4)
                                              │
                                       ┌──────▼──────┐
                                       │ wiki/*.md   │
                                       │ (enriched)  │
                                       └──────┬──────┘
                                              │
                                    compile_cross_references()
                                    rebuild_index + QMD
```

## Deliverables (4 micro-commits)

| # | What | Files |
|---|---|---|
| 1 | **`BulkIngestor` class** — core logic: scan source dir, dedup via SHA-256 manifest, copy to `raw/`, batch compile with concurrency, single reindex at end | `cortex/compiler/bulk.py` (new) |
| 2 | **`cortex-bulk-ingest` CLI entry point** — argparse wrapper: `--source /path`, `--concurrency 4`, `--force`, `--dry-run` | `scripts/bulk_ingest.py` (new), `pyproject.toml` (add script entry) |
| 3 | **Docker support** — add optional `INGEST_DIR` volume mount to `docker-compose.yml`, so you can `docker exec cortex uv run cortex-bulk-ingest --source /ingest` | `docker-compose.yml` |
| 4 | **REST endpoint** — `POST /api/v1/bulk-ingest` that triggers the same logic server-side (for programmatic use without MCP) | `cortex/api/routes.py` |

## Deduplication Strategy

A SHA-256 manifest file at `.cortex/ingest-manifest.json`:

```json
{
  "raw/paper1.pdf": "sha256:abc123...",
  "raw/paper2.docx": "sha256:def456..."
}
```

- Before copying, hash the source file
- If the hash matches an existing entry, skip (already ingested)
- `--force` bypasses the manifest check
- This is faster and more reliable than filename matching

## Concurrency Model

- Use `asyncio.Semaphore(concurrency)` to limit parallel LLM calls
- File copies are cheap — run them all upfront
- LLM enrichment is the bottleneck — bounded concurrency prevents rate-limit errors
- Progress logged per file: `[3/47] Compiling paper1.pdf...`

## CLI Usage

```bash
# Local (outside Docker)
uv run cortex-bulk-ingest --source ./my-papers/ --concurrency 4

# Inside Docker (with mounted volume)
docker exec pulse8-ai-cortex uv run cortex-bulk-ingest --source /ingest

# Dry-run to see what would be ingested
uv run cortex-bulk-ingest --source ./my-papers/ --dry-run

# Force re-ingest everything
uv run cortex-bulk-ingest --source ./my-papers/ --force
```

## What this avoids

- No MCP wire overhead — reads files directly from disk
- No per-file reindex — single graph + QMD rebuild at the end
- No duplicate ingestion — SHA-256 manifest tracks what's already in the vault
- No one-at-a-time bottleneck — concurrent LLM enrichment
