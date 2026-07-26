#!/usr/bin/env bats
# Tests for scripts/qmd_native.sh — native (GPU) QMD lifecycle management.

setup() {
    export SCRIPT_DIR="$(cd "$BATS_TEST_DIRNAME/.." && pwd)"
    export WORK_DIR="$(mktemp -d)"
    export QMD_NATIVE_PID_FILE="$WORK_DIR/qmd-native.pid"
    export QMD_NATIVE_LOG_FILE="$WORK_DIR/qmd-native.log"
    export QMD_NATIVE_HEALTH_RETRIES=2
    export QMD_NATIVE_HEALTH_DELAY=0

    # Stub bin dir so tests never touch real qmd/node/curl.
    export STUB_BIN="$WORK_DIR/bin"
    mkdir -p "$STUB_BIN"
    export PATH="$STUB_BIN:$PATH"

    source "$SCRIPT_DIR/scripts/qmd_native.sh"
}

teardown() {
    if [ -f "$QMD_NATIVE_PID_FILE" ]; then
        kill "$(cat "$QMD_NATIVE_PID_FILE")" 2>/dev/null || true
    fi
    rm -rf "$WORK_DIR"
}

_stub_toolchain() {
    printf '#!/bin/sh\nexit 0\n' > "$STUB_BIN/qmd"
    # node stub: stay alive like the real wrapper would.
    printf '#!/bin/sh\nsleep 60\n' > "$STUB_BIN/node"
    printf '#!/bin/sh\nexit 0\n' > "$STUB_BIN/curl"
    chmod +x "$STUB_BIN/qmd" "$STUB_BIN/node" "$STUB_BIN/curl"
}

@test "qmd_native: start fails with install hint when qmd binary missing" {
    printf '#!/bin/sh\nsleep 60\n' > "$STUB_BIN/node"
    chmod +x "$STUB_BIN/node"
    hash -r
    PATH="$STUB_BIN" run native_qmd_start "$WORK_DIR/vault"
    [ "$status" -ne 0 ]
    [[ "$output" == *"qmd"* ]]
    [[ "$output" == *"install"* ]]
}

@test "qmd_native: start launches wrapper and writes pid file" {
    _stub_toolchain
    run native_qmd_start "$WORK_DIR/vault"
    [ "$status" -eq 0 ]
    [ -f "$QMD_NATIVE_PID_FILE" ]
    kill -0 "$(cat "$QMD_NATIVE_PID_FILE")"
}

@test "qmd_native: start is idempotent when already running" {
    _stub_toolchain
    native_qmd_start "$WORK_DIR/vault"
    first_pid="$(cat "$QMD_NATIVE_PID_FILE")"
    run native_qmd_start "$WORK_DIR/vault"
    [ "$status" -eq 0 ]
    [[ "$output" == *"already running"* ]]
    [ "$(cat "$QMD_NATIVE_PID_FILE")" = "$first_pid" ]
}

@test "qmd_native: stop kills process and removes pid file" {
    _stub_toolchain
    native_qmd_start "$WORK_DIR/vault"
    pid="$(cat "$QMD_NATIVE_PID_FILE")"
    run native_qmd_stop
    [ "$status" -eq 0 ]
    [ ! -f "$QMD_NATIVE_PID_FILE" ]
    ! kill -0 "$pid" 2>/dev/null
}

@test "qmd_native: stop is a quiet no-op without pid file" {
    run native_qmd_stop
    [ "$status" -eq 0 ]
}
