#!/usr/bin/env bash
# Environment validation helpers for Cortex startup.
# Sourced by start.sh — do NOT run directly.

check_required_env() {
    # Accept key from common alternative env var names
    if [ -z "${LLM_API_KEY:-}" ]; then
        if [ -n "${OPENROUTER_API_KEY:-}" ]; then
            export LLM_API_KEY="$OPENROUTER_API_KEY"
        elif [ -n "${CORTEX_LLM_API_KEY:-}" ]; then
            export LLM_API_KEY="$CORTEX_LLM_API_KEY"
        fi
    fi

    if [ -z "${LLM_API_KEY:-}" ]; then
        echo "ERROR: No LLM API key found."
        echo "  Set one of: LLM_API_KEY, OPENROUTER_API_KEY, or CORTEX_LLM_API_KEY"
        echo "  Get a key at https://openrouter.ai/keys"
        return 1
    fi

    return 0
}

apply_defaults() {
    export VAULT_DIR="${VAULT_DIR:-./example_vault}"
    export COMPILER_MODEL="${COMPILER_MODEL:-anthropic/claude-sonnet-4}"
    export LLM_BASE_URL="${LLM_BASE_URL:-https://openrouter.ai/api/v1}"
    export QMD_REFRESH_INTERVAL_SECONDS="${QMD_REFRESH_INTERVAL_SECONDS:-900}"
    export MASKING_ENABLED="${MASKING_ENABLED:-false}"
    export MASKING_RULES_PATH="${MASKING_RULES_PATH:-.cortex/masking-rules.md}"
    export MASKING_MODEL="${MASKING_MODEL:-}"
}

write_env_file() {
    local target="${1:-.env}"
    cat > "$target" <<EOF
LLM_API_KEY=${LLM_API_KEY}
COMPILER_MODEL=${COMPILER_MODEL}
LLM_BASE_URL=${LLM_BASE_URL:-https://openrouter.ai/api/v1}
VAULT_DIR=${VAULT_DIR}
QMD_REFRESH_INTERVAL_SECONDS=${QMD_REFRESH_INTERVAL_SECONDS:-900}
MASKING_ENABLED=${MASKING_ENABLED:-false}
MASKING_RULES_PATH=${MASKING_RULES_PATH:-.cortex/masking-rules.md}
MASKING_MODEL=${MASKING_MODEL:-}
EOF
}

check_masking_rules() {
    if [ "${MASKING_ENABLED:-false}" = "true" ]; then
        local vault="${VAULT_DIR:-./example_vault}"
        local rules_file="${vault}/${MASKING_RULES_PATH:-.cortex/masking-rules.md}"
        if [ ! -f "$rules_file" ]; then
            echo "WARNING: Masking is enabled but rules file not found: $rules_file"
            echo "  Copy the example rules: cp example_vault/.cortex/masking-rules.md $rules_file"
            return 1
        fi
    fi
    return 0
}

prompt_missing_env() {
    echo ""
    echo "=== Cortex Configuration ==="
    echo ""

    if [ -z "${LLM_API_KEY:-}" ]; then
        printf "Enter your LLM API key (OpenRouter): "
        read -r LLM_API_KEY
        export LLM_API_KEY
    fi

    if [ -z "${LLM_API_KEY:-}" ]; then
        echo "ERROR: LLM_API_KEY is required. Aborting."
        return 1
    fi

    apply_defaults

    echo ""
    echo "Configuration:"
    echo "  LLM API Key:  ${LLM_API_KEY:0:12}..."
    echo "  Model:        $COMPILER_MODEL"
    echo "  LLM Base URL: $LLM_BASE_URL"
    echo "  Vault:        $VAULT_DIR"
    echo "  QMD Refresh:  ${QMD_REFRESH_INTERVAL_SECONDS}s"
    echo "  Masking:      ${MASKING_ENABLED}"
    echo ""
}
