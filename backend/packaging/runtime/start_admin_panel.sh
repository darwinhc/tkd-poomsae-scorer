#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"
export TKD_RUNTIME_ROOT="$ROOT_DIR"

EXE_PATH="./PoomsaeServer/PoomsaeServer"
if [[ ! -x "$EXE_PATH" ]]; then
  echo "[ERROR] Linux executable not found at: $EXE_PATH"
  exit 1
fi

OPEN_HOST="127.0.0.1"
OPEN_PORT="8080"
ADMIN_PATH="/admin"

if [[ -f .env ]]; then
  while IFS='=' read -r k v; do
    [[ -z "${k}" || "${k}" =~ ^# ]] && continue
    if [[ "$k" == "TKD_PORT" ]]; then
      OPEN_PORT="$v"
    elif [[ "$k" == "TKD_ADMIN_BASE_PATH" ]]; then
      ADMIN_PATH="$v"
    fi
  done < .env
fi

"$EXE_PATH" &
SERVER_PID=$!

sleep 2
if command -v xdg-open >/dev/null 2>&1; then
  xdg-open "http://${OPEN_HOST}:${OPEN_PORT}${ADMIN_PATH}" >/dev/null 2>&1 || true
fi

echo "Server started with PID ${SERVER_PID}."
wait "$SERVER_PID"
