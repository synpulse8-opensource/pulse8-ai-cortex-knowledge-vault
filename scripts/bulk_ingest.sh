#!/usr/bin/env bash
set -euo pipefail

# PULSE8.ai Cortex — one-click bulk ingest
# Ingests all files from a source directory into the vault, compiles them,
# and rebuilds the index. Works standalone — no running server required.
#
# Usage:
#   ./scripts/bulk_ingest.sh /path/to/papers
#   ./scripts/bulk_ingest.sh /path/to/papers --dry-run
#   ./scripts/bulk_ingest.sh /path/to/papers --force
#   ./scripts/bulk_ingest.sh /path/to/papers --concurrency 8

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$SCRIPT_DIR"

# ── Load .env if present ────────────────────────────────────────────
if [ -f .env ]; then
    set -a
    # shellcheck disable=SC1091
    source .env
    set +a
fi

# ── Resolve LLM key from common aliases ─────────────────────────────
if [ -z "${CORTEX_LLM_API_KEY:-}" ]; then
    if [ -n "${LLM_API_KEY:-}" ]; then
        export CORTEX_LLM_API_KEY="$LLM_API_KEY"
    elif [ -n "${OPENROUTER_API_KEY:-}" ]; then
        export CORTEX_LLM_API_KEY="$OPENROUTER_API_KEY"
    fi
fi

# ── Resolve vault path ──────────────────────────────────────────────
export CORTEX_VAULT_PATH="${CORTEX_VAULT_PATH:-${VAULT_DIR:-./example_vault}}"

# ── Parse arguments ─────────────────────────────────────────────────
if [ $# -lt 1 ]; then
    echo "PULSE8.ai Cortex — Bulk Ingest"
    echo ""
    echo "Usage: $0 <source-directory> [options]"
    echo ""
    echo "Options:"
    echo "  --concurrency N   Max parallel LLM calls (default: 4)"
    echo "  --force           Re-ingest all files, bypass dedup manifest"
    echo "  --dry-run         Preview what would be ingested without changes"
    echo ""
    echo "Examples:"
    echo "  $0 ./my-papers/"
    echo "  $0 ./my-papers/ --dry-run"
    echo "  $0 ./my-papers/ --force --concurrency 8"
    exit 1
fi

SOURCE_DIR="$1"
shift

if [ ! -d "$SOURCE_DIR" ]; then
    echo "ERROR: Source directory does not exist: $SOURCE_DIR"
    exit 1
fi

FILE_COUNT=$(find "$SOURCE_DIR" -maxdepth 1 -type f | wc -l | tr -d ' ')

# ── Summary ─────────────────────────────────────────────────────────
echo ""
echo "PULSE8.ai Cortex — Bulk Ingest"
echo ""
echo "  Source:      $SOURCE_DIR ($FILE_COUNT files)"
echo "  Vault:       $CORTEX_VAULT_PATH"
if [ -n "${CORTEX_LLM_API_KEY:-}" ]; then
    echo "  LLM:         enabled (key set)"
else
    echo "  LLM:         disabled (no key — files will be converted without enrichment)"
fi
echo "  Extra args:  ${*:-(none)}"
echo ""

# ── Run ─────────────────────────────────────────────────────────────
uv run cortex-bulk-ingest --source "$SOURCE_DIR" "$@"

echo ""
echo "Done."
