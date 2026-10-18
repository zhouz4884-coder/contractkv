#!/usr/bin/env bash
set -euo pipefail
ROOT="${ROOT:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv}"
PY="${PYTHON_BIN:-/home/user/miniconda3/envs/contractkv-cu128/bin/python}"
MODEL_PATH="${MODEL_PATH:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/models/Mistral-7B-Instruct-v0.3}"
SOURCE_VLLM="${SOURCE_VLLM:-$ROOT/third_party/vllm-contractkv-phase19c}"
SCHEDULER="$SOURCE_VLLM/vllm/v1/core/sched/scheduler.py"
OUT="$ROOT/results/mistral"; LOG="$ROOT/logs/mistral"
cd "$ROOT"; mkdir -p "$OUT" "$LOG" "$OUT/development_cells" "$OUT/heldout_cells" "$OUT/load_extension_cells"
export PYTHONPATH="$SOURCE_VLLM:$ROOT${PYTHONPATH:+:$PYTHONPATH}"

if nvidia-smi --query-compute-apps=pid --format=csv,noheader 2>/dev/null | grep -q '[0-9]'; then
  echo "GPU compute process already exists; refusing to mix a stale process into Extension M" >&2
  exit 20
fi

"$PY" scripts/phaseM_prepare_mistral_split.py \
  --full-pool results/workload/phase14d_full_pool_v2.jsonl \
  --phase19a-quality results/quality/phase19a_frozen_quality_v0.csv \
  --prior-sessions results/end_to_end/phase19b_untouched_sessions_v0.jsonl \
  --prior-sessions results/cross_model/phase19c_calibration_sessions_v0.jsonl \
  --prior-sessions results/cross_model/phase19c_heldout_sessions_v0.jsonl \
  --prior-sessions results/cross_model/phase20d_development_sessions_v0.jsonl \
  --prior-sessions results/cross_model/phase20d_heldout_sealed_sessions_v0.jsonl \
  --development-output "$OUT/development_sessions_v0.jsonl" \
  --heldout-output "$OUT/heldout_sealed_sessions_v0.jsonl" \
  --commitment-output "$OUT/mistral_split_commitment_v0.json"
"$PY" scripts/phaseM_freeze_manifest.py --model-path "$MODEL_PATH" --vllm-source "$SOURCE_VLLM" \
  --split-commitment "$OUT/mistral_split_commitment_v0.json" \
  --candidate-builder scripts/phase19b_end_to_end_live.py --quality-scorer scripts/phase20a_official_quality.py \
  --runtime-output "$OUT/mistral_runtime_manifest_v0.json" --policy-output "$OUT/mistral_policy_v0.json"
POLICY_HASH="$("$PY" -c 'import json;print(json.load(open("results/mistral/mistral_policy_v0.json"))["policy_hash"])')"

"$PY" scripts/install_vllm_v1_ephemeral_shadow_hook.py --scheduler "$SCHEDULER" --action install
"$PY" scripts/install_vllm_v1_prefix_metrics_probe.py --scheduler "$SCHEDULER" --action install
cleanup_probe(){
  "$PY" scripts/install_vllm_v1_prefix_metrics_probe.py --scheduler "$SCHEDULER" --action uninstall || true
  "$PY" scripts/install_vllm_v1_ephemeral_shadow_hook.py --scheduler "$SCHEDULER" --action remove || true
}
trap cleanup_probe EXIT

run_server_job(){
  local name=$1 sessions=$2 policy=$3 conc=$4 gpu=$5 port=$6 output_dir=$7 policy_hash=$8
  (
    set -euo pipefail
    local metrics="$output_dir/${name}_metrics.jsonl" output="$output_dir/${name}.jsonl"
    local pid="$LOG/${name}.pid" log="$LOG/${name}_server.log"
    rm -f "$metrics" "$output" "$pid"
    export CONTRACTKV_PREFIX_METRICS=1 CONTRACTKV_PREFIX_INITIAL_ONLY=1 CONTRACTKV_PREFIX_METRICS_LOG="$metrics"
    export CONTRACTKV_POLICY_HASH="$policy_hash" CONTRACTKV_MIN_CANDIDATE_MARGIN=-1000000000
    export CONTRACTKV_MAX_DEGRADATION=1000000000 EXTRA_VLLM_ARGS="--enable-prefix-caching"
    cleanup_cell(){ bash scripts/stop_vllm_server.sh --pid-path "$pid" --port "$port" || true; }
    trap cleanup_cell EXIT
    bash scripts/run_vllm_server.sh --phase "mistral-$name" --model-path "$MODEL_PATH" \
      --served-model-name mistral7b --port "$port" --gpu-ids "$gpu" --tensor-parallel-size 1 \
      --dtype float16 --max-model-len 8192 --max-num-seqs "$conc" --gpu-memory-utilization .88 \
      --log-path "$log" --pid-path "$pid"
    "$PY" scripts/phase19b_end_to_end_live.py --sessions "$sessions" --base-url "http://127.0.0.1:$port/v1" \
      --model mistral7b --policy "$policy" --policy-hash "$policy_hash" --load-tier "$name" \
      --concurrency "$conc" --turns 10 --max-tokens 128 --stable-word-limit 1500 --tool-slack-ms 2000 \
      --metrics-events "$metrics" --output "$output"
  )
}

# M1: tokenizer/template protocol audit on ten development-only sessions.
PROTO_PID="$LOG/protocol.pid"; PROTO_LOG="$LOG/protocol_server.log"; PROTO_PORT=8061
export CONTRACTKV_POLICY_HASH="$POLICY_HASH" CONTRACTKV_MIN_CANDIDATE_MARGIN=-1000000000
export CONTRACTKV_MAX_DEGRADATION=1000000000 EXTRA_VLLM_ARGS="--enable-prefix-caching"
bash scripts/run_vllm_server.sh --phase mistral-protocol --model-path "$MODEL_PATH" --served-model-name mistral7b \
  --port "$PROTO_PORT" --gpu-ids 0 --tensor-parallel-size 1 --dtype float16 --max-model-len 8192 \
  --max-num-seqs 2 --gpu-memory-utilization .88 --log-path "$PROTO_LOG" --pid-path "$PROTO_PID"
"$PY" scripts/phaseM_protocol_audit.py --sessions "$OUT/development_sessions_v0.jsonl" --model-path "$MODEL_PATH" \
  --base-url "http://127.0.0.1:$PROTO_PORT/v1" --model mistral7b --max-tokens 128 --stable-word-limit 1500 \
  --output "$OUT/protocol_audit_v0.jsonl" --summary-output "$OUT/protocol_audit_summary_v0.json"
"$PY" scripts/phaseM_logprob_payload_audit.py --sessions "$OUT/development_sessions_v0.jsonl" \
  --base-url "http://127.0.0.1:$PROTO_PORT/v1" --model mistral7b --session-id mistral-hotpotqa-152 \
  --output "$OUT/logprob_payload_audit_v0.json"
bash scripts/stop_vllm_server.sh --pid-path "$PROTO_PID" --port "$PROTO_PORT" || true
PROTO_PASS="$("$PY" -c 'import json; a=json.load(open("results/mistral/protocol_audit_summary_v0.json")); b=json.load(open("results/mistral/logprob_payload_audit_v0.json")); print(str(a["gate_pass"] and b["current_parser_pass"]).lower())')"
if [[ "$PROTO_PASS" != "true" ]]; then echo MISTRAL_PROTOCOL_STOP; exit 0; fi

# M2: four-policy development calibration, two isolated cells at a time.
DEV="$OUT/development_sessions_v0.jsonl"; DEV_OUT="$OUT/development_cells"
run_server_job dev-raw "$DEV" raw-order 2 0 8062 "$DEV_OUT" "$POLICY_HASH" & p0=$!
run_server_job dev-physical "$DEV" physical-cache-aware 2 1 8063 "$DEV_OUT" "$POLICY_HASH" & p1=$!
failed=0; wait "$p0" || failed=1; wait "$p1" || failed=1; [[ $failed -eq 0 ]] || exit 31
run_server_job dev-static "$DEV" static-dependency-layout 2 0 8064 "$DEV_OUT" "$POLICY_HASH" & p0=$!
run_server_job dev-contractkv "$DEV" contractkv-full 2 1 8065 "$DEV_OUT" "$POLICY_HASH" & p1=$!
failed=0; wait "$p0" || failed=1; wait "$p1" || failed=1; [[ $failed -eq 0 ]] || exit 32
"$PY" scripts/phaseM_future_turn_quality.py --partition development --sessions "$DEV" \
  --protocol-summary "$OUT/protocol_audit_summary_v0.json" \
  --cell "raw-order=$DEV_OUT/dev-raw.jsonl" --cell "physical-cache-aware=$DEV_OUT/dev-physical.jsonl" \
  --cell "static-dependency-layout=$DEV_OUT/dev-static.jsonl" --cell "contractkv-full=$DEV_OUT/dev-contractkv.jsonl" \
  --quality-output "$OUT/development_quality_v0.csv" --summary-output "$OUT/development_summary_v0.json" \
  --slo-output "$OUT/development_slo_v0.csv" --gate-output "$OUT/development_gate_v0.json"
DEV_PASS="$("$PY" -c 'import json;print(str(json.load(open("results/mistral/development_gate_v0.json"))["gate_pass"]).lower())')"
if [[ "$DEV_PASS" != "true" ]]; then echo MISTRAL_DEVELOPMENT_STOP; exit 0; fi

# M3: freeze once, then open the sealed heldout split exactly once.
"$PY" scripts/phaseM_freeze_policy.py --policy "$OUT/mistral_policy_v0.json" \
  --development-summary "$OUT/development_summary_v0.json" --development-gate "$OUT/development_gate_v0.json" \
  --output "$OUT/frozen_policy_v0.json"
FROZEN_HASH="$("$PY" -c 'import json;print(json.load(open("results/mistral/frozen_policy_v0.json"))["policy_hash"])')"
HELD="$OUT/heldout_sealed_sessions_v0.jsonl"; HELD_OUT="$OUT/heldout_cells"
run_server_job heldout-raw "$HELD" raw-order 2 0 8066 "$HELD_OUT" "$FROZEN_HASH" & p0=$!
run_server_job heldout-physical "$HELD" physical-cache-aware 2 1 8067 "$HELD_OUT" "$FROZEN_HASH" & p1=$!
failed=0; wait "$p0" || failed=1; wait "$p1" || failed=1; [[ $failed -eq 0 ]] || exit 33
run_server_job heldout-static "$HELD" static-dependency-layout 2 0 8068 "$HELD_OUT" "$FROZEN_HASH" & p0=$!
run_server_job heldout-contractkv "$HELD" contractkv-full 2 1 8069 "$HELD_OUT" "$FROZEN_HASH" & p1=$!
failed=0; wait "$p0" || failed=1; wait "$p1" || failed=1; [[ $failed -eq 0 ]] || exit 34
"$PY" scripts/phaseM_future_turn_quality.py --partition heldout --sessions "$HELD" \
  --cell "raw-order=$HELD_OUT/heldout-raw.jsonl" --cell "physical-cache-aware=$HELD_OUT/heldout-physical.jsonl" \
  --cell "static-dependency-layout=$HELD_OUT/heldout-static.jsonl" --cell "contractkv-full=$HELD_OUT/heldout-contractkv.jsonl" \
  --quality-output "$OUT/heldout_quality_v0.csv" --summary-output "$OUT/heldout_summary_v0.json" \
  --slo-output "$OUT/heldout_slo_v0.csv" --gate-output "$OUT/gate_v0.json"
HELD_PASS="$("$PY" -c 'import json;print(str(json.load(open("results/mistral/gate_v0.json"))["gate_pass"]).lower())')"
if [[ "$HELD_PASS" != "true" ]]; then echo MISTRAL_HELDOUT_STOP; exit 0; fi

# Only a successful c=2 heldout gate unlocks c=1/c=4 load curves.
for conc in 1 4; do
  run_server_job "load-c${conc}-raw" "$HELD" raw-order "$conc" 0 $((8070+conc)) "$OUT/load_extension_cells" "$FROZEN_HASH" & p0=$!
  run_server_job "load-c${conc}-contractkv" "$HELD" contractkv-full "$conc" 1 $((8075+conc)) "$OUT/load_extension_cells" "$FROZEN_HASH" & p1=$!
  failed=0; wait "$p0" || failed=1; wait "$p1" || failed=1; [[ $failed -eq 0 ]] || exit 35
done
echo MISTRAL_PROSPECTIVE_EXTENSION_COMPLETE
