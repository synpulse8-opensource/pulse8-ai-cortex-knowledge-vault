# Changelog

All notable changes to PULSE8.ai Cortex are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

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
