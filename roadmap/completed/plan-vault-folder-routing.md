# Vault Folder Routing: agents/, daily/, sessions/

**Status:** Planned  
**Created:** 2026-05-13  
**Reference:** [Karpathy LLM Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)

## Problem

The vault layout defines four content directories (`wiki/`, `agents/`, `sessions/`, `daily/`) and the read side of the system is fully aware of them — `scan_vault`, `build_wikilink_index`, `resolve_wikilink`, and QMD search all traverse these folders. However, every ingestion path (MCP ingest, bulk ingest, REST API, compiler) hardcodes `wiki/` as the output directory. The `agents/`, `sessions/`, and `daily/` folders are never populated by the system.

### Current Write Path

```
raw source ──► KnowledgeCompiler.ingest_source() ──► wiki/{slug}.md
```

The destination is hardcoded at `compiler.py:112`:

```python
note_path = self.vault_path / "wiki" / filename
```

### Current Read Path (already folder-aware)

| Component | Awareness |
|---|---|
| `scan_vault` | Walks all subdirs recursively |
| `build_wikilink_index` | Prioritizes `wiki/ > agents/ > sessions/ > daily/` |
| `resolve_wikilink` | Searches `wiki/`, `agents/`, `sessions/`, `daily/` in order |
| `infer_node_type` | Classifies by suffix (`.agent.md`, `.session.md`, `.memory.md`) and path prefix (`raw/`) |
| QMD search | Indexes all `.md` files in the vault |
| `vault/index.py` | Sections by folder name |

## Design

Inspired by Karpathy's LLM Wiki pattern, the vault separates concerns into distinct layers. The compiler should route content to the appropriate folder based on its nature:

### Folder Purposes

| Folder | Content Type | How it gets populated |
|---|---|---|
| `raw/` | Immutable source documents (PDFs, papers, articles) | User drops files or uses ingest API. Never modified by the system. |
| `wiki/` | LLM-compiled knowledge articles — summaries, entity pages, concept pages, comparisons, synthesis | Compiler output from `ingest_source()`. The persistent, compounding knowledge layer. |
| `agents/` | Agent definition files (`*.agent.md`) — reusable personas, tool configurations, system prompts | User-authored or generated via a future "create agent" workflow. |
| `sessions/` | Session transcripts (`*.session.md`) — captured conversations, Q&A logs, exploration records | Auto-captured from MCP/API chat sessions. Append-only records of what was discussed. |
| `daily/` | Daily compilation logs — chronological digest of what was ingested, queried, and changed each day | Auto-generated daily summaries of vault activity. Similar to Karpathy's `log.md` but structured as one file per day. |

### Key Insight from Karpathy's LLM Wiki

> "The wiki keeps getting richer with every source you add and **every question you ask**."

The `sessions/` and `daily/` folders close this loop: questions asked and answers generated during sessions should be captured and optionally promoted into the wiki as new pages, so explorations compound in the knowledge base rather than disappearing into chat history.

## Proposed Changes

### Phase 1: Session Capture

Automatically capture MCP/API interactions as session files.

1. **Session writer** — new module `cortex/vault/session.py`
   - On session start (first MCP tool call), create `sessions/YYYY-MM-DD-HHMMSS.session.md`
   - Append each Q&A pair as a section: query, context used, answer, tool calls
   - Close session file when idle timeout expires or explicit close

2. **Frontmatter schema for sessions**
   ```yaml
   ---
   title: "Research session — transformer architectures"
   type: session
   started_at: 2026-05-13T14:30:00Z
   ended_at: 2026-05-13T15:12:00Z
   queries: 7
   sources_referenced: ["wiki/attention-mechanisms.md", "wiki/transformers.md"]
   ---
   ```

3. **Session-to-wiki promotion** — MCP tool `vault:promote_session`
   - User reviews a session and promotes valuable answers into wiki pages
   - Promoted content gets compiled through the enrichment pipeline
   - Original session entry gets a `promoted_to: wiki/new-page.md` frontmatter field

### Phase 2: Daily Digests

Auto-generate daily compilation logs.

1. **Daily digest generator** — new module `cortex/vault/daily.py`
   - At end of day (or on demand), generate `daily/YYYY-MM-DD.md`
   - Summarize: files ingested, queries answered, pages created/updated, contradictions found
   - Link to relevant wiki pages and sessions

2. **Frontmatter schema for daily logs**
   ```yaml
   ---
   title: "2026-05-13"
   type: daily
   date: 2026-05-13
   ingested: 3
   queries: 12
   pages_created: 2
   pages_updated: 5
   ---
   ```

3. **Integration with audit log** — complement the existing `.cortex/log.md` append-only log with structured daily summaries

### Phase 3: Agent Definitions

Support agent definition files as first-class vault content.

1. **Agent file conventions**
   - Files in `agents/` with `.agent.md` suffix
   - Already recognized by `infer_node_type` as `NodeType.AGENT_DEF`
   - Contains system prompts, tool configurations, persona definitions

2. **Frontmatter schema for agents**
   ```yaml
   ---
   title: "Research Scout"
   type: agent_def
   authored_by: human
   tools: ["vault:search", "vault:context", "vault:ingest"]
   description: "Scans raw sources and identifies key claims for wiki integration"
   ---
   ```

3. **Agent-as-compiler** — allow agent definitions to customize the compilation pipeline (e.g., a "research scout" agent that focuses on extracting citations, vs. a "summarizer" agent that creates executive summaries)

### Phase 4: Compiler Routing (if needed)

If content should be auto-routed to folders during ingestion:

1. **Route by frontmatter `type`** — if the LLM enrichment step detects or is told the content type, route accordingly
2. **Route by source convention** — e.g., files named `*.transcript.*` go to `sessions/`
3. **Make destination configurable** — `ingest_source(destination="sessions")` override

## Node Type Alignment

Update `infer_node_type` to also consider directory path:

```python
if path.startswith("daily/"):
    return NodeType.NOTE  # or a new NodeType.DAILY
if path.startswith("agents/"):
    return NodeType.AGENT_DEF
if path.startswith("sessions/"):
    return NodeType.SESSION
```

Consider adding a `NodeType.DAILY` enum value for daily digest files.

## What This Enables

- **Explorations compound** — session Q&A doesn't vanish into chat history
- **Activity is observable** — daily digests give a timeline of the wiki's evolution
- **Agents are reusable** — agent definitions stored alongside the knowledge they help build
- **Graph is richer** — session → wiki edges, daily → session edges, agent → wiki edges create a more connected knowledge graph

## Dependencies

- Existing `infer_node_type` already handles `.agent.md`, `.session.md`, `.memory.md` suffixes
- Existing `build_wikilink_index` already prioritizes across all four folders
- Existing `scan_vault` already walks all subdirectories
- QMD already indexes all `.md` files

## Out of Scope (for now)

- **Lint / health-check operations** — Karpathy describes periodic LLM audits for contradictions, orphan pages, stale claims. This is a separate roadmap item.
- **Wiki-to-wiki cross-referencing at ingest** — already partially implemented via `compile_cross_references`
- **Embedding-based RAG** — the current index.md + QMD approach works at moderate scale (~100s of sources)
