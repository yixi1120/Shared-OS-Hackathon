#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-/mnt/workspace/Shared-OS-Hackathon}"
ENV_FILE="${ENV_FILE:-/mnt/workspace/.sharedos-secrets/sharedos.env}"

cd "$PROJECT_DIR"
if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing secret environment file: $ENV_FILE" >&2
  exit 2
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

export BUILD_SHA="${BUILD_SHA:-$(git rev-parse --short=12 HEAD)}"

uv run sharednet-agent doctor --test-generation

terminate() {
  kill "${api_pid:-}" "${listener_pid:-}" 2>/dev/null || true
  wait "${api_pid:-}" "${listener_pid:-}" 2>/dev/null || true
}
trap terminate EXIT INT TERM

restart_api() {
  while true; do
    uv run commerce-api
    echo "Seller API exited; restarting in 2 seconds" >&2
    sleep 2
  done
}

restart_listener() {
  while true; do
    uv run sharednet-agent listen --announce
    echo "SharedNet listener exited; restarting in 2 seconds" >&2
    sleep 2
  done
}

restart_api &
api_pid=$!
restart_listener &
listener_pid=$!
wait "$api_pid" "$listener_pid"
