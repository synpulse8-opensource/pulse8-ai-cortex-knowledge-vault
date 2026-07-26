#!/usr/bin/env bash
# Native QMD lifecycle — run QMD on the host instead of in Docker.
#
# On macOS this is the only way QMD can use the GPU: Docker Desktop cannot
# expose Apple's Metal API to containers, so containerized embedding runs
# on emulated CPU (orders of magnitude slower). The native qmd binary picks
# up Metal automatically.
#
# Sourced by scripts/start.sh / scripts/stop.sh; functions are testable via
# tests/test_qmd_native.bats.

QMD_NATIVE_PID_FILE="${QMD_NATIVE_PID_FILE:-.qmd-native.pid}"
QMD_NATIVE_LOG_FILE="${QMD_NATIVE_LOG_FILE:-.qmd-native.log}"
QMD_NATIVE_PORT="${QMD_NATIVE_PORT:-3100}"
QMD_NATIVE_HEALTH_RETRIES="${QMD_NATIVE_HEALTH_RETRIES:-30}"
QMD_NATIVE_HEALTH_DELAY="${QMD_NATIVE_HEALTH_DELAY:-2}"

native_qmd_running() {
    [ -f "$QMD_NATIVE_PID_FILE" ] && kill -0 "$(cat "$QMD_NATIVE_PID_FILE")" 2>/dev/null
}

# native_qmd_start <vault_dir> [wiki_dir] [refresh_seconds]
native_qmd_start() {
    local vault_dir="$1"
    local wiki_dir="${2:-${VAULT_WIKI_DIR:-wiki}}"
    local refresh="${3:-${QMD_REFRESH_INTERVAL_SECONDS:-900}}"

    if native_qmd_running; then
        echo "Native QMD already running (pid $(cat "$QMD_NATIVE_PID_FILE"))."
        return 0
    fi

    if ! command -v qmd >/dev/null 2>&1; then
        echo "ERROR: 'qmd' binary not found. Install it first:" >&2
        echo "  brew install tobi/tap/qmd   # or: npm install -g @tobilu/qmd" >&2
        return 1
    fi
    if ! command -v node >/dev/null 2>&1; then
        echo "ERROR: 'node' not found (needed to run docker/qmd/server.mjs)." >&2
        return 1
    fi

    echo "Starting native QMD on port $QMD_NATIVE_PORT (vault: $vault_dir)..."
    # </dev/null and 3>&- detach the child from the caller's stdin and from
    # bats' internal fd 3, so test runs don't hang waiting on the daemon.
    VAULT_PATH="$vault_dir" \
    VAULT_WIKI_DIR="$wiki_dir" \
    QMD_PORT="$QMD_NATIVE_PORT" \
    QMD_REFRESH_INTERVAL_SECONDS="$refresh" \
        nohup node docker/qmd/server.mjs > "$QMD_NATIVE_LOG_FILE" 2>&1 </dev/null 3>&- &
    echo $! > "$QMD_NATIVE_PID_FILE"

    local i
    for i in $(seq 1 "$QMD_NATIVE_HEALTH_RETRIES"); do
        if curl -sf "http://localhost:$QMD_NATIVE_PORT/health" >/dev/null 2>&1; then
            echo "Native QMD is up (pid $(cat "$QMD_NATIVE_PID_FILE"), log: $QMD_NATIVE_LOG_FILE)."
            return 0
        fi
        if ! native_qmd_running; then
            echo "ERROR: native QMD exited during startup. Last log lines:" >&2
            tail -5 "$QMD_NATIVE_LOG_FILE" >&2 || true
            rm -f "$QMD_NATIVE_PID_FILE"
            return 1
        fi
        sleep "$QMD_NATIVE_HEALTH_DELAY"
    done

    echo "ERROR: native QMD did not become healthy in time. See $QMD_NATIVE_LOG_FILE" >&2
    return 1
}

native_qmd_stop() {
    if [ ! -f "$QMD_NATIVE_PID_FILE" ]; then
        return 0
    fi
    local pid
    pid="$(cat "$QMD_NATIVE_PID_FILE")"
    if kill -0 "$pid" 2>/dev/null; then
        echo "Stopping native QMD (pid $pid)..."
        kill "$pid" 2>/dev/null || true
        local i
        for i in 1 2 3 4 5; do
            kill -0 "$pid" 2>/dev/null || break
            sleep 1
        done
        kill -9 "$pid" 2>/dev/null || true
    fi
    rm -f "$QMD_NATIVE_PID_FILE"
    echo "Native QMD stopped."
}
