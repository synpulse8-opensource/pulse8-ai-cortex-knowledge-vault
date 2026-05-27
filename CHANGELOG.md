# Changelog

All notable changes to PULSE8.ai Cortex are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [1.0.2] — 2026-05-27

### Removed

- **Internal JFrog CI workflow**: Removed `build-container-jfrog.yml` which referenced the private `synpulse-group/s8-actions` action, causing every push to `main` on the opensource repo to fail with "Unable to resolve action".

## [1.0.1] — 2026-05-27

### Fixed

- **fastmcp dependency floor**: Bumped `fastmcp` from `>=2.0.0` to `>=3.0.0` in `pyproject.toml`. The codebase uses fastmcp 3.x APIs (`FastMCP`, `OIDCProxy`, `http_app`) which are unavailable in 2.x. The loose lower bound caused namespace-package corruption resulting in `ImportError: cannot import name 'FastMCP'`, breaking 15 tests.

## [1.0.0] — 2026-05-18

### Added — Authentication & Security

- **API key authentication**: New `AUTH_METHOD=apikey` mode — clients pass `x-api-key` header. Simple, stateless, no OAuth popups.
- **Microsoft Entra ID (OIDC)**: New `AUTH_METHOD=oidc` mode with OAuth 2.0 Authorization Code Flow + MFA support. Interactive browser-based login for enterprise environments.
- **OpenAPI specification**: Auto-generated OpenAPI docs served via FastAPI.

### Added — GPU Support & Flexible Deployment

- **NVIDIA GPU support for QMD**: New `Dockerfile.gpu` (CUDA 12.8 runtime + Node.js 22) and `docker-compose.gpu.yml` overlay enable GPU-accelerated embedding, reranking, and query expansion on EC2.
- **Cortex-only deployment mode**: `./scripts/start.sh --cortex-only` starts only the Cortex container without QMD, allowing QMD to run natively on macOS with Metal GPU acceleration.
- **Configurable embed timeout**: New `QMD_EMBED_TIMEOUT_MS` environment variable replaces the hardcoded 600s timeout.
- **EC2 GPU setup guide**: New `docs/ec2-gpu-setup.md` covering instance selection, NVIDIA driver installation, and cost estimates.

### Added — CI/CD & Operations

- **JFrog build & push workflow**: Automated container image builds and publishing.
- **Enhanced logging**: Ingestion and compilation steps now emit structured logs for observability.
- **Import constraints**: Compiler enforces import boundaries for cleaner module architecture.

### Fixed

- **SameFileError in bulk ingest**: Prevented crash when source and destination are the same file.
- **Dockerfile.gpu Node version**: Updated to a newer Node.js version for compatibility.
- **Directory path crash in `read_note`**: Raises `IsADirectoryError` with a clear message instead of crashing.
- **Pylint test using wrong Python**: Uses `sys.executable` instead of bare `python`.
- **Flaky perf test**: Adjusted budget for CI runners.
- **QMD model download race**: Embed no longer starts before model download completes.
- **Permission and logging issues**: Various fixes for Docker volume permissions and log suppression.

### Changed

- **Development status**: Promoted from Beta to Production/Stable.

## [0.6.0] — 2026-05-16

### Added — GPU Support & Flexible Deployment

- **NVIDIA GPU support for QMD**: New `Dockerfile.gpu` (CUDA 12.8 runtime + Node.js 22) and `docker-compose.gpu.yml` overlay enable GPU-accelerated embedding, reranking, and query expansion on EC2. GPU is opt-in — base compose remains CPU-only and works on any machine.
- **Cortex-only deployment mode**: `./scripts/start.sh --cortex-only` starts only the Cortex container without QMD, allowing QMD to run natively on macOS with Metal GPU acceleration. New `docker-compose.cortex-only.yml` overlay clears `depends_on` and points `CORTEX_QMD_URL` to `host.docker.internal`.
- **Configurable embed timeout**: New `QMD_EMBED_TIMEOUT_MS` environment variable replaces the hardcoded 600s timeout in `server.mjs`, allowing CPU-only deployments to set a longer window.
- **EC2 GPU setup guide**: New `docs/ec2-gpu-setup.md` covering instance selection (g4dn.xlarge), NVIDIA driver/toolkit installation, GPU compose deployment, multi-instance scaling, cost estimates, and security checklist.

### Fixed

- **Directory path crash in `read_note`**: `read_note()` now raises `IsADirectoryError` with a clear message instead of letting `frontmatter.load` crash with an unhelpful traceback. The `vault:read` handler catches it gracefully.
- **Pylint test using wrong Python**: `test_pylint_passes` now uses `sys.executable` instead of bare `python`, preventing false failures when the system Python differs from the venv.

### Tests

- 1 new test for directory path guard in `read_note`
- All 260 tests passing

## [0.5.0] — 2026-05-04

### Added — LLM Enrichment Pipeline

- **Post-conversion LLM enrichment**: After MarkItDown converts a raw file to Markdown, the LLM now adds `[[wikilinks]]` and suggests tags via the new `enrich_article()` method. This restores intelligent graph linking that was lost when the conversion step moved to MarkItDown.
- **`ENRICH_SYSTEM_PROMPT`**: New system prompt in `prompts.py` that instructs the LLM to add wikilinks and tags while preserving original content.
- **Automatic cross-referencing**: `compile_cross_references()` is now automatically called after `ingest_source` in both `handle_vault_ingest` (when `auto_compile=true`) and `handle_vault_compile`.
- **API key guard on cross-references**: `compile_cross_references()` gracefully skips when no LLM API key is configured, matching the enrichment behaviour.

### Changed

- **`auto_compile` defaults to `True`**: Ingested files are now automatically compiled (MarkItDown + LLM enrichment + cross-references) unless the caller explicitly passes `auto_compile=false`. Applies to REST API, MCP stdio, and MCP HTTP surfaces.

### Fixed — Example Vault

- Repaired wiki articles with proper titles, `[[wikilinks]]`, and tags
- Added 3 new raw sources and enriched wiki articles (alignment faking, attention paper, emotion concepts)
- Gitignored vault runtime artifacts (`.cortex/graph.json`, `index.md`, `log.md`, `.obsidian/`)

### Tests

- 8 new tests for LLM enrichment, cross-reference wiring, and prompt validation
- Total test count: 227

## [0.4.0] — 2026-05-04

### Changed — MarkItDown Compiler

- **Replace LLM-based file conversion with MarkItDown**: The `KnowledgeCompiler.ingest_source` method now uses [Microsoft MarkItDown](https://github.com/microsoft/markitdown) to convert raw files to Markdown instead of calling an LLM. Supported formats include PDF, DOCX, PPTX, XLSX, XLS, HTML, CSV, JSON, XML, images (EXIF metadata), and plain text. The LLM is still used for cross-reference detection between articles (`compile_cross_references`).
- **LLM API key is now optional**: An OpenRouter API key is no longer required for file ingestion and conversion. It is only needed for optional cross-referencing between wiki articles.

### Added — Binary File Ingestion

- **REST file upload endpoint**: New `POST /api/v1/ingest/upload` accepts multipart file uploads for binary formats (PDF, DOCX, etc.).
- **MCP base64 ingestion**: The `vault_ingest` MCP tool now accepts a `content_base64` parameter for binary file ingestion via JSON.
- **Shared binary handler**: `handle_vault_ingest` accepts a `file_bytes` parameter alongside the existing `content` parameter.
- **Expanded extractor**: `cortex/compiler/extractor.py` now provides a unified `extract_text()` function powered by MarkItDown, replacing the previous `pdftotext` and `httpx`-based helpers.

### Removed

- `INGEST_SYSTEM_PROMPT` — no longer needed since file conversion is handled by MarkItDown.
- `KnowledgeCompiler._parse_articles()` — no longer needed since MarkItDown produces Markdown directly.
- `extract_text_from_pdf()` and `extract_text_from_url()` — replaced by MarkItDown's `extract_text()`.

### Dependencies

- Added `markitdown[pdf,docx,pptx,xlsx,xls]>=0.1.0`
- Added `pylint>=3.0.0` to dev dependencies

### Tests

- 7 new tests for MarkItDown-based ingestion and helpers
- 7 new tests for binary file ingestion (REST upload, MCP base64, shared handler)
- Total test count: 220

## [0.2.0] — 2026-04-25

### Performance — QMD Search

- **Deduplicate periodic refresh**: Cortex no longer runs its own periodic QMD refresh timer when using the Docker stack, since the QMD container already manages its own. Cuts redundant `update` + `embed` cycles in half.
- **Fix `/update` client timeout**: Extended the `QMDHttpSearch.update()` timeout from 30s to 600s to match the server-side embed duration. Prevents silent client-side timeouts on large vaults.
- **Debounce write-triggered re-index**: Added `DebouncedQMDUpdate` that coalesces rapid writes into a single deferred `qmd.update()` call, avoiding N full re-indexes during batch operations.
- **Batch graph edge lookups**: Added `GraphEngine.get_edges_batch()` using `asyncio.gather` to fetch edges for all search results in parallel instead of sequentially.
- **TTL search cache**: Wrapped QMD search with `CachedQMDSearch` — identical queries within a 30s window return cached results without spawning a QMD process. Cache is invalidated on `update()`.
- **Skip duplicate `/setup`**: `QMDHttpSearch.initialize()` now polls `/health` first and skips calling `/setup` if the QMD container has already finished its own setup, reducing cold-boot time.

### Performance — Vault Loading

- **Batch graph persistence**: Added `GraphEngine.batch()` context manager that defers `save()` calls during `build_graph`, replacing O(N) JSON serializations with a single write at the end.
- **Parallel vault scanning**: Added `scan_vault_async()` that offloads frontmatter parsing to a `ThreadPoolExecutor` for concurrent file I/O during startup.
- **Wikilink index**: Added `build_wikilink_index()` that pre-builds a stem-to-path lookup map, giving `build_graph` O(1) wikilink resolution instead of per-link filesystem traversals.
- **Accept pre-scanned notes in `rebuild_index`**: `rebuild_index()` now takes an optional `notes` parameter to skip redundant full vault scans when notes are already loaded.

### Fixed

- **Consistent search mode**: `build_context_window` now respects `CORTEX_QMD_SEARCH_MODE` instead of always defaulting to `hybrid`, which is the most expensive mode.

### New Modules

- `cortex/search/qmd_debounce.py` — Debounced update scheduler
- `cortex/search/qmd_cache.py` — TTL search result cache

### Tests

- 34 new tests covering all performance improvements
- Total test count: 200+

## [0.1.0] — 2026-04-20

Initial open-source release.

- Knowledge graph engine (NetworkX) with typed edges and wikilinks
- Full-text search via QMD (keyword / semantic / hybrid)
- LLM compiler for transforming raw sources into wiki articles
- MCP server (streamable HTTP + stdio transport)
- REST API at `/api/v1/`
- Real-time vault watcher with filesystem monitoring
- Docker Compose stack with QMD sidecar
- Apache 2.0 license with PULSE8.ai additional terms
