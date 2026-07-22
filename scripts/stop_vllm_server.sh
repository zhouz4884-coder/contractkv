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

descendants() {
  local parent=$1 child
  while read -r child; do
    [[ -n "$child" ]] || continue
    descendants "$child"
    printf '%s\n' "$child"
  done < <(pgrep -P "$parent" 2>/dev/null || true)
}

if [[ -n "$PID_PATH" && -f "$PID_PATH" ]]; then
  PID="$(cat "$PID_PATH")"
  if [[ -n "$PID" ]] && kill -0 "$PID" 2>/dev/null; then
    # Capture the multiprocessing tree before terminating the API parent;
    # EngineCore/resource_tracker children are reparented to PID 1 otherwise.
    mapfile -t CHILD_PIDS < <(descendants "$PID")
    kill "$PID" "${CHILD_PIDS[@]}" 2>/dev/null || true
    for _ in $(seq 1 30); do
      alive=0
      for target in "$PID" "${CHILD_PIDS[@]}"; do
        kill -0 "$target" 2>/dev/null && alive=1
      done
      (( alive == 0 )) && break
      sleep 1
    done
    for target in "$PID" "${CHILD_PIDS[@]}"; do
      kill -0 "$target" 2>/dev/null && kill -9 "$target" 2>/dev/null || true
    done
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
