#!/usr/bin/env bash
set -euo pipefail

for port in 8000 8001 8002; do
  echo "=== port ${port} ==="
  if command -v lsof >/dev/null 2>&1; then
    lsof -i ":${port}" || true
  elif command -v ss >/dev/null 2>&1; then
    ss -ltnp | grep ":${port}" || true
  else
    netstat -ltnp 2>/dev/null | grep ":${port}" || true
  fi
done

echo "=== vLLM processes ==="
ps aux | grep -E "vllm|api_server" | grep -v grep || true

