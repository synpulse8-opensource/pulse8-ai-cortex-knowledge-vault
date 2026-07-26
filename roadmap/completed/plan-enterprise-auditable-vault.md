# Enterprise Auditable Vault: Lineage, Query Surface, Scoped Access

**Status:** Phases 1–4 implemented (v1.5.0); Phases 5–6 pending design-partner validation
**Created:** 2026-07-26
**Updated:** 2026-07-26 — Phase 1 (backends + zero-LLM contract), Phase 2 (edge origin labels + `vault_trace`), Phase 3 (`vault_path` / `vault_impact` / `vault_explain`), Phase 4 (usage counters, feedback outcomes, curation report) shipped.
**Reference:** Graphify feature analysis — borrow provenance tagging, deterministic-first ingestion, query/path surface, outcome-memory loop, honest benchmarks; skip the installer matrix and virality mechanics.

## Framing

Cortex's differentiation against open-source knowledge tools (graphify et al.) is not developer virality — it is being the vault an enterprise (BFSI first) can actually deploy: auditable, air-gap-capable, access-scoped. Two of the five phases below remove adoption objections; the middle two create differentiation; the last one proves it with a number.

**Pressure-test before committing to this order:** lineage and access scoping only pay off if buyers are compliance-adjacent. Front-office knowledge management cares more about freshness and coverage than audit trails. Validate with a design-partner bank which pain is acute before starting Phase 2; if freshness wins, pull Phase 4 (outcome loop / staleness) forward and let lineage ride behind it.

## Where the codebase already is

The survey of current internals shows several phases are partially built, which changes scoping:

| Idea | Current state |
|---|---|
| Deterministic-first ingest | Already true: MarkItDown converts without any LLM key; enrichment and cross-referencing are skipped when `llm_api_key` is empty (`enrichment_status: incomplete`). What's missing is backend pluggability and making this an advertised architectural guarantee with tests. |
| Lineage | Note-level `Provenance` dataclass exists (`authored_by`, `created_at`, `updated_at`, `model`, `confidence`, `source_path`) and `Edge` already carries a free-form `metadata` dict. What's missing: edge-level provenance labels, page/section granularity, model version stamping, and a trace query. |
| Query surface | `vault_link` (edge CRUD), `vault_context` (BFS context window), `graph/stats` exist. No shortest-path, no multi-hop path query, no "explain this entity" composite. NetworkX `MultiDiGraph` is already in place — path algorithms are cheap to add. |
| Outcome loop | `vault_feedback` captures quality feedback as notes with `related_paths`. No usage telemetry, no outcome recording (useful / dead-end / corrected), no staleness signal. |
| Access scoping | `AUTH_METHOD none/apikey/oidc` with Entra claims on `request.state.user_claims`, used only for display names. No per-path ACL anywhere. No Sentinel integration in the codebase yet. |

## Phase 1: Deterministic-first guarantee + pluggable LLM backends

Removes the "external API call" objection at the architecture level.

1. **Backend abstraction** — new module `cortex/llm/backend.py`
   - Protocol/ABC `LLMBackend` with `complete()` and `caption_image()`; today's direct `openai.AsyncOpenAI` usage in `KnowledgeCompiler` and `extractor.make_markitdown` moves behind it.
   - Implementations: `OpenAICompatibleBackend` (covers OpenRouter, Azure OpenAI, Ollama, vLLM — all OpenAI-compatible; differ only in `base_url`/auth) and `BedrockBackend` (boto3, for AWS-native shops).
   - Config: `CORTEX_LLM_BACKEND` (`openai-compatible` | `bedrock` | `none`), reusing existing `llm_base_url` / `compiler_model`. `none` disables enrichment explicitly rather than inferring from a missing key.
2. **Contract tests for zero-LLM mode** — pin the guarantee that with `CORTEX_LLM_BACKEND=none`: ingest produces a wiki note, wikilinks/tags/`DERIVED_FROM` edges are built, QMD indexes it, and no network call is attempted (assert via a backend spy). This is the marketing claim made falsifiable.
3. **Docs** — README section "Runs without an LLM" + air-gapped deployment note (Ollama example) in `docs/`.

Out of scope for this phase: swapping QMD's embedding model provider (separate concern, QMD owns it).

## Phase 2: Lineage metadata (provenance on every node and edge)

The compliance answer to "why does the vault say X."

1. **Edge provenance** — standardize keys inside the existing `Edge.metadata` dict rather than schema migration:
   - `origin`: `extracted` (deterministic — wikilink/tag/frontmatter), `inferred` (LLM cross-reference), `manual` (via `vault_link`/REST)
   - `model`, `model_version` when `origin: inferred`
   - `source_ref`: `{path, page?, section?}` pointing at the raw document location that justifies the edge
   - `build_graph` stamps `origin: extracted` on all auto-built edges; `compile_cross_references` stamps `origin: inferred` + model; `vault_link` stamps `origin: manual` + authenticated user (from `user_claims`).
2. **Note provenance hardening** — extend `Provenance` with `model_version` and `ingested_at`; compiler writes exact model identifier (already partially done via `model` frontmatter). Raw-source page anchors: MarkItDown conversion records page boundaries where the format allows (PDF), stored as a `source_pages` map in wiki frontmatter.
3. **Trace query** — MCP tool `vault_trace` + `GET /api/v1/trace/{path}`: given a wiki note (or a claim's note+section), walk `DERIVED_FROM` edges to raw sources and return the full lineage chain: raw file, ingestion timestamp, compiler model version, human edits since (from `updated_at` vs `created_at`), and every inferred edge touching the note with its origin labels.
4. **Backfill** — `scripts/reindex.py` gains a `--stamp-provenance` pass that labels existing edges `extracted`/`unknown` so old vaults aren't second-class.

## Phase 3: Query/path surface (query, path, explain)

Turns the typed graph from plumbing into the product. Regulatory impact analysis is the flagship use case: when MiFID/DORA text changes, walk the graph to everything downstream.

1. **Path queries** — MCP tool `vault_path` + `GET /api/v1/graph/path`
   - `source`, `target`, optional `edge_types` filter, `max_hops`
   - NetworkX `all_shortest_paths` on the existing `MultiDiGraph`, returning each hop with its edge type and provenance labels (Phase 2 makes path results self-justifying).
2. **Explain** — MCP tool `vault_explain` + REST equivalent
   - Composite over existing pieces: note content + provenance chain (Phase 2 trace) + immediate typed neighborhood + contradictions. "Explain this client entity" in one call instead of four.
3. **Impact query** — `vault_impact`: from a node, directional traversal (e.g. everything reachable via `DERIVED_FROM` reversed + `LINKS_TO`) with depth limit — "what is downstream of this regulation."
4. **Shared handler discipline** — per repo convention, handlers live in `cortex/mcp/tools.py` and are shared with REST routes; all three respect `as_resource=true` for token-light returns (reuse the 1.3.0 resource store).

## Phase 4: Outcome-memory loop (knowledge quality management)

Extends `vault_feedback` from complaint box to curation signal.

1. **Usage recording** — lightweight counter on read/search-hit per note, aggregated into `.cortex/usage.json` (no per-user tracking; counts and last-used timestamps only). VaultWatcher-safe (not a vault note, avoids self-indexing).
2. **Outcome recording** — extend `vault_feedback` with `outcome`: `useful` | `dead_end` | `corrected` and optional `superseded_by` path. `corrected` outcomes auto-create a `CONTRADICTS` or `SUPERSEDES` edge (types already exist in `EdgeType`, currently manual-only).
3. **Staleness signal** — `GET /api/v1/curation/report`: notes never used in N days, notes with open `corrected` feedback, notes whose raw source changed after last compile (manifest hash vs current). This is the curation workflow feed.
4. **Daily digest integration** — surface curation stats in the existing `daily/` activity log.

## Phase 5: Scoped access (Sentinel integration point)

A vault holding client knowledge can't let every connected agent see everything. None of the open-source tools handle this — it is the moat, and the hardest phase.

1. **Path-scope model** — scopes are folder-prefix rules attached to a principal (user claim or API key): `{principal, allow: ["wiki/clients/acme/**"], deny: [...]}`. Stored in `.cortex/access.json` initially; Sentinel becomes the external policy source when integrated (Sentinel is the enforcement point per the product thesis — design the interface, don't build the policy engine).
2. **Enforcement layer** — single choke point in the shared handlers (`tools.py`): every path-returning operation (read, search results, context windows, graph traversals, resources) filters against the caller's scope. Graph queries must filter both nodes and edges — a path query must not leak an edge into a denied subtree. Search filtering happens post-QMD (QMD has no auth concept).
3. **Identity plumbing** — `user_claims` (already populated by OIDC middleware) and API-key identity map to principals; MCP stdio transport gets a `CORTEX_PRINCIPAL` env override for local single-user use.
4. **Append-only change history** — per-note history (`.cortex/history/{path}.jsonl`: timestamp, principal, diff hash) as the audit companion to scoping. Retention/deletion workflows are a follow-up roadmap item, not this phase.

## Phase 6: Retrieval eval (prove it)

Superseded by the dedicated plan: [../plan-retrieval-benchmarks.md](../plan-retrieval-benchmarks.md) —
LongMemEval first (public dataset, official judge prompts, comparable
published numbers), LOCOMO second, custom regulatory-corpus eval third, with
blind-validated judging and one-command reproduction.

## Sequencing rationale

1 and 2 remove objections (external-API dependence, no audit trail). 3 and 4 create differentiation (impact analysis, curation loop). 5 is the moat but the most invasive — it benefits from 2's provenance labels (audit trail) and 3's single query surface (fewer enforcement points). 6 converts architects.

Phases 1–2 are independent and can run in parallel. Phase 3 needs 2's edge labels for self-justifying results. Phase 5 should not start before the design-partner validation.

## Explicitly not borrowed from graphify

- Mass-platform installer matrix, HTML-first virality, 30-second demo funnel
- Committing output to git as the collaboration story (Cortex's story is the vault + MCP)
- Their code benchmarks (wrong corpus for our buyer)

## Dependencies

- `Edge.metadata` dict and `Provenance` dataclass (exist — `cortex/vault/models.py`)
- Shared MCP/REST handlers in `cortex/mcp/tools.py` (repo convention)
- Resource store from v1.3.0 for token-light graph query returns
- OIDC claims plumbing (`cortex/auth/middleware.py`) for principals
- TDD per workspace rule: each phase lands as atomic red-green steps with user verification between them

## Out of scope (for now)

- Retention & deletion workflows (needs Phase 5 first; separate plan)
- SSO in front of HTTP transport beyond existing OIDC (infra concern)
- QMD-internal access control or embedding-provider swapping
- Editing graphify's actual mechanics (viral demo, installers)
