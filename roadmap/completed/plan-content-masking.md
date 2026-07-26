# Content Masking During Ingestion

**Status:** Planned  
**Created:** 2026-05-13

## Problem

When ingesting documents from enterprise or regulated environments, raw content often contains sensitive information that must not appear in the compiled wiki — client names, internal project codes, employee identifiers, financial figures, IP addresses, proprietary terms, etc. Today, the ingestion pipeline has no awareness of sensitivity: whatever comes in through `raw/` passes through MarkItDown conversion and LLM enrichment verbatim into `wiki/`.

Users need a way to define masking rules once, and have the system automatically apply them to every ingested document before the LLM enrichment step — so that neither the compiled wiki pages nor the LLM API calls ever see unmasked sensitive content.

## Current Ingestion Pipeline

```
raw/source.pdf
    │
    ▼
MarkItDown.convert_local()     ← text extraction (no LLM)
    │
    ▼
md_content (plain Markdown)
    │
    ▼
enrich_article()               ← LLM call: adds wikilinks + tags
    │
    ▼
write_note() → wiki/{slug}.md
```

The masking step must run **after** MarkItDown extraction (which produces the readable text) and **before** LLM enrichment (which sends content to an external API).

## Proposed Pipeline

```
raw/source.pdf
    │
    ▼
MarkItDown.convert_local()     ← text extraction (no LLM)
    │
    ▼
md_content (plain Markdown)
    │
    ▼
┌──────────────────────────────────────┐
│  NEW: content masking step           │
│                                      │
│  if masking enabled:                 │
│    1. Load rules from .cortex/       │
│       masking-rules.md               │
│    2. Apply regex-based rules first  │
│    3. Send to LLM with rules for     │
│       context-aware masking          │
│    4. Return masked content          │
│                                      │
│  else:                               │
│    pass through unchanged            │
└──────────────────────────────────────┘
    │
    ▼
masked_content
    │
    ▼
enrich_article()               ← LLM only sees masked content
    │
    ▼
write_note() → wiki/{slug}.md  ← wiki only contains masked content
```

## Masking Rules File

A Markdown file at `.cortex/masking-rules.md` that is both human-readable and machine-parseable. Users write rules in natural language sections with optional regex patterns. The LLM uses the natural language descriptions for context-aware masking; the system uses the regex patterns for deterministic pre-masking.

### Example `.cortex/masking-rules.md`

```markdown
# Content Masking Rules

These rules are applied to all ingested content before LLM enrichment
and wiki compilation.

## Client Names

Replace all client and customer names with anonymized placeholders.
Use the format `[CLIENT-A]`, `[CLIENT-B]`, etc. Maintain consistency:
the same client should always get the same placeholder within a document.

### Patterns
- `Acme Corp(oration)?`
- `Wayne Enterprises`
- `Globex`

## Financial Figures

Mask specific monetary amounts, revenue figures, and financial projections.
Replace with `[AMOUNT]` or `[FINANCIAL_FIGURE]`. Preserve the currency
and order of magnitude if contextually important (e.g., "multi-million"
is acceptable, "$4.7M" is not).

### Patterns
- `\$[\d,]+(\.\d{2})?(\s*(million|billion|M|B|k|K))?`
- `(EUR|CHF|GBP)\s*[\d,]+(\.\d{2})?`

## Internal Project Codes

Replace internal project codes and codenames with generic placeholders.
Use `[PROJECT-X]` format.

### Patterns
- `PRJ-\d{4,6}`
- `Project (Phoenix|Titan|Orion|Neptune)`

## Employee Information

Remove or mask employee names, employee IDs, email addresses, and
phone numbers. Replace names with role descriptions where possible
(e.g., "the project lead" instead of "John Smith").

### Patterns
- `EMP-\d{5,7}`
- `[a-zA-Z0-9._%+-]+@(acmecorp|internal)\.(com|org|net)`

## IP Addresses and Infrastructure

Mask internal IP addresses, hostnames, and infrastructure details.

### Patterns
- `10\.\d{1,3}\.\d{1,3}\.\d{1,3}`
- `192\.168\.\d{1,3}\.\d{1,3}`
- `[a-z]+-[a-z]+-\d+\.internal\.example\.com`

## Custom Rules

Add any domain-specific masking rules below. Each rule should have
a description explaining what to mask and why, plus optional regex
patterns for deterministic matching.
```

### Rule File Format

Each `##` section defines a masking category:
- **Section body** — natural language description for the LLM to understand the intent, context, and replacement strategy
- **`### Patterns` subsection** — optional list of regex patterns for deterministic pre-masking before the LLM step

This two-layer approach (regex + LLM) catches both exact pattern matches and context-dependent cases that regex alone cannot handle (e.g., recognizing "the CEO of our biggest client" as needing masking even without a name match).

## Configuration

### Settings

Add to `CortexSettings` in `cortex/config.py`:

```python
masking_enabled: bool = False
masking_rules_path: str = ".cortex/masking-rules.md"
masking_model: str = ""  # defaults to compiler_model if empty
```

Activated via environment variables:

```bash
CORTEX_MASKING_ENABLED=true
CORTEX_MASKING_RULES_PATH=.cortex/masking-rules.md  # optional override
CORTEX_MASKING_MODEL=anthropic/claude-sonnet-4       # optional, separate model
```

### Why a Separate Model Setting

Masking may benefit from a different model than enrichment — a faster/cheaper model for high-volume masking, or a more capable model for nuanced redaction. The `masking_model` setting allows this without affecting the enrichment pipeline.

## Implementation

### New Module: `cortex/compiler/masking.py`

```python
class ContentMasker:
    """Applies masking rules to extracted content before LLM enrichment."""

    def __init__(self, vault_path: Path) -> None: ...
    def load_rules(self) -> MaskingRules: ...
    def apply_regex_rules(self, content: str, rules: MaskingRules) -> str: ...
    async def apply_llm_masking(self, content: str, rules: MaskingRules) -> str: ...
    async def mask(self, content: str) -> MaskingResult: ...
```

### MaskingRules Model

```python
@dataclass
class MaskingRule:
    category: str          # section heading
    description: str       # natural language body
    patterns: list[str]    # regex patterns from ### Patterns subsection

@dataclass
class MaskingRules:
    rules: list[MaskingRule]
    raw_markdown: str      # full rules file for LLM context

@dataclass
class MaskingResult:
    content: str           # masked content
    applied_rules: int     # number of regex matches applied
    llm_masking: bool      # whether LLM masking was used
```

### Masking Prompt

```
You are a content masking agent for a knowledge management system.

You will receive:
1. A document that has been extracted from a raw source file
2. A set of masking rules that describe what sensitive content to redact

Your job:
- Identify and replace sensitive content according to the rules
- Use the specified placeholder formats from each rule
- Maintain consistency: the same entity gets the same placeholder throughout
- Preserve document structure, formatting, and non-sensitive content exactly
- When in doubt, mask rather than expose

Some content may already be partially masked by regex patterns (you'll see
placeholders like [CLIENT-A], [AMOUNT], etc.). Preserve those and apply
additional masking for cases the regex missed.

Return ONLY the masked document content. No explanations, no JSON wrapping.
```

### Integration into `KnowledgeCompiler.ingest_source`

The masking step inserts between MarkItDown extraction and LLM enrichment:

```python
async def ingest_source(self, source_path: Path) -> list[Path]:
    # ... existing MarkItDown conversion ...
    md_content = (result.text_content or "").strip()

    # NEW: apply content masking if enabled
    if settings.masking_enabled:
        masker = ContentMasker(self.vault_path)
        mask_result = await masker.mask(md_content)
        md_content = mask_result.content
        # optionally record masking metadata in frontmatter

    # ... existing enrichment and write logic ...
```

### Frontmatter Metadata

Masked documents get additional frontmatter fields:

```yaml
---
title: "Quarterly Review Summary"
source_path: "raw/quarterly-review-2026-q1.pdf"
masking_applied: true
masking_rules_version: "sha256:abc123..."
enrichment_status: "complete"
---
```

The `masking_rules_version` is a hash of the rules file at the time of masking, enabling re-masking when rules change.

## Deliverables

| # | What | Files | Tests |
|---|---|---|---|
| 1 | **Masking rules parser** — parse `.cortex/masking-rules.md` into structured `MaskingRules` | `cortex/compiler/masking.py` | `tests/test_masking.py` |
| 2 | **Regex pre-masking** — apply deterministic regex patterns from rules | `cortex/compiler/masking.py` | `tests/test_masking.py` |
| 3 | **LLM context-aware masking** — send pre-masked content + rules to LLM for remaining sensitive content | `cortex/compiler/masking.py`, `cortex/compiler/prompts.py` | `tests/test_masking.py` |
| 4 | **Configuration** — `masking_enabled`, `masking_rules_path`, `masking_model` settings | `cortex/config.py` | `tests/test_config.py` |
| 5 | **Pipeline integration** — insert masking step into `ingest_source` and `BulkIngestor` | `cortex/compiler/compiler.py`, `cortex/compiler/bulk.py` | `tests/test_compiler.py` |
| 6 | **Frontmatter metadata** — record masking status and rules version | `cortex/compiler/compiler.py` | `tests/test_compiler.py` |

## Edge Cases

- **Rules file missing** — if masking is enabled but the rules file doesn't exist, log a warning and skip masking (fail open to avoid blocking ingestion)
- **Empty rules** — if the file exists but has no `##` sections, skip masking
- **LLM unavailable** — if the LLM API is unreachable, apply regex rules only and mark the document as `masking_status: partial`
- **Re-masking** — if rules change, provide a CLI command to re-mask previously ingested documents: `cortex-remask --since 2026-05-01` or `--all`
- **Masking too aggressive** — the LLM might over-mask. The rules file should include explicit "do NOT mask" guidance where needed
- **Raw files untouched** — masking never modifies `raw/` files. The original source is always preserved

## Future Extensions

- **Masking audit log** — append to `.cortex/log.md` what was masked, for compliance
- **Reversible masking** — store a mapping (entity → placeholder) in an encrypted file, so authorized users can unmask
- **Per-folder rules** — different masking rules for different content types (e.g., stricter for `sessions/`, lighter for `wiki/`)
- **Masking validation** — a lint step that scans wiki output for patterns that should have been masked
