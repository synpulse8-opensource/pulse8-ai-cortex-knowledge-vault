#!/usr/bin/env bats
# Tests for scripts/start.sh environment validation logic.
# Requires: bats-core (brew install bats-core)

setup() {
    export SCRIPT_DIR="$(cd "$BATS_TEST_DIRNAME/.." && pwd)"
    # Source only the validation function
    source "$SCRIPT_DIR/scripts/env_check.sh"
}

@test "env_check: no API key triggers error" {
    unset LLM_API_KEY OPENROUTER_API_KEY CORTEX_LLM_API_KEY LLM_BACKEND
    run check_required_env
    [ "$status" -ne 0 ]
    [[ "$output" == *"No LLM API key found"* ]]
}

@test "env_check: LLM_BACKEND=none needs no API key" {
    unset LLM_API_KEY OPENROUTER_API_KEY CORTEX_LLM_API_KEY
    export LLM_BACKEND="none"
    run check_required_env
    [ "$status" -eq 0 ]
}

@test "env_check: LLM_BACKEND=bedrock needs no API key" {
    unset LLM_API_KEY OPENROUTER_API_KEY CORTEX_LLM_API_KEY
    export LLM_BACKEND="bedrock"
    run check_required_env
    [ "$status" -eq 0 ]
}

@test "env_check: LLM_BACKEND written to .env file" {
    export LLM_BACKEND="none"
    export LLM_API_KEY="unused"
    apply_defaults
    tmpenv="$(mktemp)"
    write_env_file "$tmpenv"
    grep -q "LLM_BACKEND=none" "$tmpenv"
    rm -f "$tmpenv"
}

@test "env_check: LLM_API_KEY set passes" {
    unset OPENROUTER_API_KEY CORTEX_LLM_API_KEY
    export LLM_API_KEY="sk-or-test-123"
    run check_required_env
    [ "$status" -eq 0 ]
}

@test "env_check: OPENROUTER_API_KEY is accepted" {
    unset LLM_API_KEY CORTEX_LLM_API_KEY
    export OPENROUTER_API_KEY="sk-or-alt-456"
    check_required_env
    [ "$LLM_API_KEY" = "sk-or-alt-456" ]
}

@test "env_check: CORTEX_LLM_API_KEY is accepted" {
    unset LLM_API_KEY OPENROUTER_API_KEY
    export CORTEX_LLM_API_KEY="sk-or-cortex-789"
    check_required_env
    [ "$LLM_API_KEY" = "sk-or-cortex-789" ]
}

@test "env_check: VAULT_DIR defaults to ./example_vault" {
    unset VAULT_DIR
    apply_defaults
    [ "$VAULT_DIR" = "./example_vault" ]
}

@test "env_check: VAULT_DIR preserves user override" {
    export VAULT_DIR="/my/vault"
    apply_defaults
    [ "$VAULT_DIR" = "/my/vault" ]
}

@test "env_check: COMPILER_MODEL defaults when unset" {
    unset COMPILER_MODEL
    apply_defaults
    [ -n "$COMPILER_MODEL" ]
}

@test "env_check: COMPILER_MODEL preserves user override" {
    export COMPILER_MODEL="openai/gpt-4o"
    apply_defaults
    [ "$COMPILER_MODEL" = "openai/gpt-4o" ]
}

@test "env_check: writes .env file" {
    export LLM_API_KEY="sk-or-test-123"
    export COMPILER_MODEL="openai/gpt-4o"
    export VAULT_DIR="./example_vault"
    local tmpenv="$(mktemp)"
    write_env_file "$tmpenv"
    grep -q "LLM_API_KEY=sk-or-test-123" "$tmpenv"
    grep -q "COMPILER_MODEL=openai/gpt-4o" "$tmpenv"
    grep -q "VAULT_DIR=./example_vault" "$tmpenv"
    rm -f "$tmpenv"
}
