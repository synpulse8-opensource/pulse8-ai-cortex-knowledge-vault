# Changelog

All notable changes to PULSE8.ai Cortex are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [1.6.0] — 2026-07-27

### Added

- **Retrieval benchmark harness** (`evals/`): reproducible, auditable evaluation of Cortex retrieval end-to-end through the public REST API (ingest → compile → search → answer → judge). Pinned YAML configs (dataset SHA-256, models, seed; a hash mismatch aborts the run), per-question vault isolation with a synchronous QMD reindex hook, LLM-as-judge with strict yes/no verdict parsing and enforced judge ≠ answerer, official LongMemEval per-type grading prompts, recall@k from dataset evidence labels, per-phase token accounting, crash-safe JSONL trace streaming, and blind human validation (identifier-stripped samples, percent + Cohen's kappa agreement).
- **First published benchmark result — LongMemEval-S (hybrid search)**: 45.0% overall accuracy, 65.6% evidence recall@8 over all 500 questions with zero judge errors. Full per-category table, methodology, and caveats in [docs/benchmarks/README.md](docs/benchmarks/README.md); reproduce with `uv run python -m evals.run_longmemeval --config evals/configs/longmemeval-s-hybrid.yaml`.
- **Native QMD mode** (`--native-qmd`): `start.sh` / `stop.sh` can run QMD directly on the host instead of in Docker — on Apple-silicon Macs this gives QMD Metal-GPU embedding (Docker Desktop cannot access the GPU, forcing slow CPU emulation). PID/log files are managed under the repo root; `stop.sh` cleans up a native QMD automatically.

### Fixed

- **Trace files with Unicode line separators**: `read_traces` now splits records on newline only; model answers containing U+2028/U+2029 (written unescaped with `ensure_ascii=False`) previously corrupted JSONL parsing via `splitlines()`.

## [1.5.0] — 2026-07-26

### Added

- **Pluggable LLM backends** (`LLM_BACKEND` / `CORTEX_LLM_BACKEND`): `openai-compatible` (OpenRouter, Azure OpenAI, Ollama, vLLM — default), `bedrock` (AWS credential chain, lazy `boto3`), or `none`. All compiler LLM usage now routes through `cortex/llm/backend.py`.
- **Zero-LLM (deterministic-first) mode**: `LLM_BACKEND=none` guarantees no LLM client is constructed and no model call is made — ingest, graph, and search all work. `start.sh` no longer requires an API key for `none`/`bedrock`. Pinned by contract tests.
- **Edge lineage**: every graph edge now carries an `origin` label — `extracted` (deterministic structure extraction), `manual` (created via `vault_link`/REST), reserved `inferred` for LLM cross-references.
- **`vault_trace`** (MCP + `GET /api/v1/trace/{path}`): full lineage of a note — provenance (author, model, timestamps), raw sources via `derived_from`, and all labeled edges. Answers "why does the vault say X".
- **Graph query surface**: `vault_path` (shortest paths between notes, tag hubs excluded, every hop typed and origin-labeled; `GET /api/v1/graph/path`), `vault_impact` (transitive upstream dependents for change-impact analysis; `GET /api/v1/graph/impact`), `vault_explain` (summary + provenance + grouped connections; `GET /api/v1/explain/{path}`).
- **Usage counters**: MCP and REST note reads increment per-note counters in `.cortex/usage.json`.
- **Feedback outcomes**: `vault_feedback` and `POST /api/v1/feedbacks` accept an optional `outcome` label (`useful` / `dead-end` / `corrected`).
- **Curation report** (`GET /api/v1/curation/report`): most-read, never-read, stale (configurable `stale_days`), and contradicted notes (contradiction edges + corrected feedback) — knowledge quality management from usage and outcome signals.

## [1.4.0] — 2026-07-26

### Added

- **Image ingestion with AI captioning**: `.jpg`, `.jpeg`, and `.png` files are now first-class ingestable sources. When an LLM key is configured, MarkItDown attaches a vision model that converts image content (text, tables, UI labels, diagrams) into searchable Markdown. New optional `COMPILER_VISION_MODEL` / `CORTEX_COMPILER_VISION_MODEL` setting selects a vision-capable model; defaults to `COMPILER_MODEL`.

### Fixed

- **QMD collections silently dropped**: the QMD container initialized `index.yml` with `collections: []` (array), which caused QMD to drop collection metadata on save, leaving `collection list` empty. The entrypoint now initializes it as `collections: {}` (object) and repairs existing broken files on startup. Also sets `XDG_CACHE_HOME` in the QMD image and compose environment.

## [1.3.0] — 2026-06-25

### Added

- **MCP resources (token-light large payloads)**: `vault_search` and `vault_context` accept `as_resource: true` to return a short `cortex://resource/{id}` handle instead of inlining the full payload, keeping the LLM context window small. Handles are read back via the MCP `resources/read` protocol, the `vault_resource_read` fallback tool, or `GET /api/v1/resources/{id}`. The in-memory store is asyncio-safe, TTL-evicted (`CORTEX_RESOURCE_TTL_SECONDS`, default 3600), and LRU-bounded (`CORTEX_RESOURCE_MAX_ITEMS`, default 1000). Shared across MCP and REST.
- **Copilot Studio guide**: [docs/copilot-studio.md](docs/copilot-studio.md) documents wiring a Copilot Studio agent to Cortex via MCP with the resources-as-tool-inputs pattern — no Cortex code change required.
- **Bulk ingest coordination**: vault- and source-scoped locking (`cortex/compiler/bulk_coordination.py`) prevents concurrent bulk ingests from corrupting the vault; manifest handling hardened with fuller tests.
- **Vault layout helpers**: `cortex/vault/layout.py` centralizes vault-path/structure utilities with dedicated tests.

### Changed

- **4 MB tool-response cap**: MCP tool responses are truncated to stay under Copilot Studio's 5 MB connector ceiling (`_enforce_payload_size` recursively caps string values with a `…[truncated]` suffix).
- **QMD retry with backoff**: `QMDSearch._run` and the QMD HTTP server's `qmdWithRetry` now retry transient failures (lock contention, resource pressure) with exponential backoff; permanent errors (`already exists`, `SQLITE_CONSTRAINT`) fail fast.
- **QMD setup-readiness guard**: `/search` returns `503` instead of an empty `200` when setup is not yet ready.
- **Streaming QMD logs**: long-running `embed` commands stream child stdout/stderr to the server log line-by-line instead of going silent.

## [1.2.2] — 2026-06-12

### Changed

- **Re-release to trigger MCP Registry publishing**: `1.2.1` was tagged and released before the `publish-mcp.yml` workflow reached the default branch, so the registry listing never ran. No functional code changes since `1.2.1`; this release exists to publish the server to `registry.modelcontextprotocol.io`.

## [1.2.1] — 2026-06-12

### Added

- **Official MCP Registry listing**: Added `server.json` (schema `2025-12-11`) describing the server under the namespace `io.github.synpulse8-opensource/pulse8-ai-cortex-knowledge-vault`, plus an `mcp-name:` ownership marker in the README so the registry can verify the PyPI package. Enables discovery via `registry.modelcontextprotocol.io`.

## [1.2.0] — 2026-06-11

### Added

- **Feedback vault collection**: New `feedback/` folder with `vault_feedback` and `vault_list_feedbacks` MCP tools plus REST endpoints, capturing user/agent feedback on vault quality with `status` and `related_paths`.
- **Microsoft Teams notifications**: Optional `TEAMS_WEBHOOK_URL` posts an adaptive card after each new feedback note; optional `TEAMS_APP_BASE_URL` adds a "View in Cortex" link.
- **Daily activity log**: Every `vault_write`, `vault_ingest`, and successful compile is mirrored into `daily/<UTC-date>.md` as a greppable `## [HH:MM] event | summary` entry with a `[[wiki-stem]]` wikilink. Writes to `daily/`, `feedback/`, and `.cortex/` are excluded to avoid self-reference.
- **Folder-based node typing**: Files under `agents/`, `sessions/`, and `daily/` are classified as `AGENT_DEF`, `SESSION`, and the new `NodeType.DAILY` without requiring a filename suffix. Frontmatter `type:` and the existing `.agent.md`/`.session.md` suffixes still take precedence/work.
- **Configurable search tuning**: `CORTEX_QMD_CACHE_TTL_SECONDS` (result-cache TTL, default 30s) and `CORTEX_QMD_SEARCH_TIMEOUT_SECONDS` (search request timeout, default 120s).

### Changed

- **Default search mode is now `hybrid`** (was `keyword`). Clients that don't pass an explicit `mode` now get the best-quality BM25 + vector + re-ranking results. Set `CORTEX_QMD_SEARCH_MODE=keyword` to restore the previous fast-but-shallow default. Latency is mitigated by the result cache and the HTTP QMD container.

### Fixed

- **QMD container returned no results**: The image installed `qmd` via `npm install -g .`, which created a global symlink into a build directory deleted in the same layer — leaving a dangling `qmd` binary so every search failed with `spawn qmd ENOENT` and silently returned `[]`. Now installed from a packed tarball with a build-time `qmd --version` smoke check.
- **Hybrid searches silently truncated**: QMD HTTP searches hit a hardcoded 30s timeout on CPU-only hosts and returned `[]` while QMD was still working. Timeout is now configurable (default 120s).
- **Cached search failures**: Empty result sets (transport errors/timeouts) are no longer cached, preventing a transient failure from blanking search for the full cache TTL.

### Performance

- **Memoized QMD path index**: `build_path_index_from_graph` is cached per graph mutation and no longer rebuilt on every search/read.
- **Non-blocking reads**: `vault_read` offloads note parsing to a thread so concurrent MCP requests no longer serialize behind file I/O.

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
