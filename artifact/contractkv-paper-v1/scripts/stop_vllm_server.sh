#!/usr/bin/env bash
set -euo pipefail

PID_PATH=""
PORT=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --pid-path) PID_PATH="$2"; shift 2 ;;
    --port) PORT="$2"; shift 2 ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done

if [[ -n "$PID_PATH" && -f "$PID_PATH" ]]; then
  PID="$(cat "$PID_PATH")"
  if [[ -n "$PID" ]] && kill -0 "$PID" 2>/dev/null; then
    kill "$PID"
    for _ in $(seq 1 30); do
      kill -0 "$PID" 2>/dev/null || break
      sleep 1
    done
    kill -0 "$PID" 2>/dev/null && kill -9 "$PID" || true
  fi
  rm -f "$PID_PATH"
fi
if [[ -n "$PORT" ]]; then
  if command -v lsof >/dev/null 2>&1; then
    lsof -ti ":${PORT}" | xargs -r kill
  else
    echo "lsof not available; port-based stop skipped." >&2
  fi
fi
