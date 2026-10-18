#!/usr/bin/env bash
set -euo pipefail

ROOT="${ROOT:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv}"
PY="${PYTHON_BIN:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/envs/contractkv-lmcache-039/bin/python}"
MODEL="/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/models/Llama-3.1-8B-Instruct"
SESSIONS="$ROOT/results/cross_model/llama_broad_generalization_r3/heldout_sealed_sessions_v0.jsonl"
MANIFEST="$ROOT/results/cross_model/llama_broad_generalization_r3/llama_broad_qualification_v0.json"
OUT="$ROOT/results/external_baseline/llama_lmcache_v1"
LOG="$ROOT/logs/external_baseline/llama_lmcache_v1"
CELLS="${CELLS:-lmcache:1 blendraw:1 cacheblend:1 lmcache:2 blendraw:2 cacheblend:2 lmcache:3 blendraw:3 cacheblend:3 lmcache:4 blendraw:4 cacheblend:4 lmcache:5 blendraw:5 cacheblend:5}"
mkdir -p "$OUT" "$LOG"; cd "$ROOT"

complete() {
  local output=$1
  [[ -s "$output" ]] || return 1
  "$PY" -c 'import json,sys; r=[json.loads(x) for x in open(sys.argv[1]) if x.strip()]; f=[x for x in r if x.get("row_type")=="future"]; raise SystemExit(0 if len(f)==450 and sum(x.get("success") is True for x in f)==450 else 1)' "$output"
}

write_config() {
  local mode=$1 path=$2
  {
    # CacheBlend 0.3.9 forces save_unfull_chunk=false in layerwise mode.  The
    # frozen Llama protocol has 58--98-token stable segments separated by an
    # exact one-token delimiter, so its default 256-token chunk silently
    # degenerates to zero stored segments.  A 32-token chunk preserves actual
    # segment hits without caching the 16-token dynamic observation.
    if [[ "$mode" == cacheblend ]]; then
      echo 'chunk_size: 32'
    else
      echo 'chunk_size: 256'
    fi
    echo 'local_cpu: true'
    echo 'max_local_cpu_size: 8.0'
    echo 'save_decode_cache: false'
    if [[ "$mode" == cacheblend ]]; then
      echo 'use_layerwise: true'
      echo 'enable_blending: true'
      echo 'blend_recompute_ratios: [0.15]'
      echo 'blend_thresholds: [0.0]'
      echo 'blend_check_layers: [1]'
      echo 'blend_min_tokens: 64'
      # A normal-text delimiter changes BPE identity at real segment
      # boundaries inside the Llama chat template.  This unused Llama special
      # token is one exact token both in isolation and in the rendered prompt.
      echo 'blend_special_str: "<|reserved_special_token_0|>"'
    fi
  } > "$path"
}

run_cell() {
  local mode=$1 repeat=$2 gpu=$3 port=$4
  local tag="llama-r${repeat}-${mode}"
  local output="$OUT/$tag.jsonl" summary="$OUT/${tag}_summary.json"
  local config="$LOG/$tag.yaml" log="$LOG/$tag.log" pid="$LOG/$tag.pid"
  # A tag owns one result file. Refuse duplicate launchers before either can
  # append to it; this also makes detached orchestration retries idempotent.
  exec 9>"$LOG/$tag.lock"
  if ! flock -n 9; then
    echo "CELL_ALREADY_RUNNING $tag" >&2
    return 20
  fi
  complete "$output" && { echo "SKIP_COMPLETE $tag"; return; }
  rm -f "$output" "$summary" "$pid"
  write_config "$mode" "$config"
  (
    export CUDA_VISIBLE_DEVICES="$gpu" LMCACHE_CONFIG_FILE="$config" PYTHON_BIN="$PY"
    # LMCache usage telemetry is unrelated to the serving experiment and its
    # py-cpuinfo helper inherits sitecustomize in CacheBlend compatibility
    # mode. Use LMCache's supported opt-out so helper stdout cannot corrupt
    # startup while leaving the cache and blending paths untouched.
    export LMCACHE_TRACK_USAGE=false DO_NOT_TRACK=1
    # FlashInfer is present only for CacheBlend's sparse-attention primitive.
    # Keep vLLM sampling on its native backend so installing that optional
    # dependency does not change the common generation path or trigger an
    # unrelated sampling-kernel JIT build.
    export VLLM_USE_FLASHINFER_SAMPLER=0
    export VLLM_STARTUP_POLLS="${VLLM_STARTUP_POLLS:-600}"
    if [[ "$mode" == cacheblend ]]; then
      export CONTRACTKV_LMCACHE_CACHEBLEND_COMPAT=1
      # LMCache 0.3.9's sparse backend explicitly targets FlashInfer 0.3.1:
      # older releases miss check_shape_dtype_device, while 0.6 removes the
      # block-sparse offset API used here.
      FLASHINFER_COMPAT="${FLASHINFER_COMPAT:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/envs/flashinfer-0.3.1}"
      export PYTHONPATH="$FLASHINFER_COMPAT:$ROOT/third_party/patches/lmcache_cacheblend_v0102${PYTHONPATH:+:$PYTHONPATH}"
      # CacheBlend's sparse-attention compatibility path JIT-compiles a CUDA
      # extension.  The host /usr/local/cuda is 11.2, while this environment
      # and the server driver use CUDA 12.8.  Keep the compiler toolchain on
      # the data disk and bind it only for CacheBlend cells.
      export CUDA_HOME="${CUDA_HOME:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/envs/cuda-nvcc-12.8}"
      export PATH="$CUDA_HOME/bin:$PATH"
      export TORCH_CUDA_ARCH_LIST="${TORCH_CUDA_ARCH_LIST:-8.6}"
    fi
    export EXTRA_VLLM_ARGS='--no-enable-prefix-caching --kv-transfer-config={"kv_connector":"LMCacheConnectorV1","kv_role":"kv_both"}'
    cleanup(){ bash scripts/stop_vllm_server.sh --pid-path "$pid" --port "$port" || true; }
    trap cleanup EXIT
    bash scripts/run_vllm_server.sh --phase "$tag" --model-path "$MODEL" --served-model-name llama31-8b \
      --port "$port" --gpu-ids "$gpu" --tensor-parallel-size 1 --dtype float16 \
      --max-model-len 8192 --max-num-seqs 2 --gpu-memory-utilization .80 --log-path "$log" --pid-path "$pid"
    args=(--sessions "$SESSIONS" --qualification-manifest "$MANIFEST" --base-url "http://127.0.0.1:$port/v1" \
      --model llama31-8b --model-path "$MODEL" --backend-label "$mode" --mode raw --concurrency 2 \
      --turns 10 --stable-word-limit 1500 --stable-pieces 16 --max-tokens 96 --slo-ms 1500 \
      --output "$output" --summary-output "$summary")
    [[ "$mode" == cacheblend || "$mode" == blendraw ]] && args+=(--segment-separator '<|reserved_special_token_0|>')
    "$PY" scripts/run_external_llama_radix_replay.py "${args[@]}"
  )
}

pending=($CELLS); index=0
LEFT_GPU="${LEFT_GPU:-0}"
RIGHT_GPU="${RIGHT_GPU:-1}"
LEFT_PORT_BASE="${LEFT_PORT_BASE:-9100}"
RIGHT_PORT_BASE="${RIGHT_PORT_BASE:-9300}"
while (( index < ${#pending[@]} )); do
  left="${pending[$index]}"; right="${pending[$((index+1))]:-}"
  IFS=: read -r lm lr <<<"$left"; run_cell "$lm" "$lr" "$LEFT_GPU" $((LEFT_PORT_BASE + index)) & p0=$!
  if [[ -n "$right" ]]; then
    sleep "${CELL_START_STAGGER_SEC:-120}"
    IFS=: read -r rm rr <<<"$right"; run_cell "$rm" "$rr" "$RIGHT_GPU" $((RIGHT_PORT_BASE + index)) & p1=$!
    wait "$p0"; wait "$p1"
  else
    wait "$p0"
  fi
  index=$((index+2))
done
echo LLAMA_LMCACHE_BASELINES_COMPLETE
