#!/usr/bin/env bash
set -euo pipefail
ROOT="${ROOT:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv}"
DATA=/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9
PY=/home/user/miniconda3/envs/contractkv-cu128/bin/python
cd "$ROOT"
"$PY" - <<'PY'
import hashlib,json,subprocess
from pathlib import Path
root=Path('results/tsc_revision_r4/cost_adaptation_validation_v1')
dev=Path('results/tsc_revision_r4/cost_adaptation_development_v1')
assert json.loads((dev/'fixed_DEV_decision_v1.json').read_text())['all_prespecified_DEV_checks_pass']
assert json.loads((dev/'agent_all_business_review_v1.json').read_text())['allow_conditional_independent_nine']
assert json.loads((root/'independent_remote_CPU_preflight_v1.json').read_text())['native_and_copied_tokenizer_window_checks_exact']
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
receipt=json.loads((root/'pre_forward_publication_v1.json').read_text())
assert receipt['public_remote_commit_verified'] and receipt['before_first_this_study_forward']
assert receipt['freeze_sha256']==sha(root/'freeze.json')
primary=Path('results/tsc_revision_r4/input_fidelity_validation_v1')
assert json.loads((primary/'remote_archive_verification_v1.json').read_text())['all_hashes_match']
assert json.loads((primary/'local_independent_recompute_v1.json').read_text())['independent_local_recomputation_complete']
assert json.loads((primary/'analysis/completion_audit_v1.json').read_text())['complete_cells']==18
assert not list((root/'cells').glob('*/runtime_manifest.json')) and not list((root/'cells').glob('*/raw.jsonl'))
freeze=json.loads((root/'freeze.json').read_text())
for item in freeze['files']:
 assert sha(item['path'])==item['sha256']
 assert sha(root/'source_snapshot'/item['path'])==item['sha256']
assert not subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader,nounits'],text=True).strip()
registry=json.loads(Path('results/tsc_revision_r4/model_registry_v1.json').read_text())
checked=[]
for model in registry['models']:
 if model['model']!='Qwen3-8B':continue
 for item in model['files']:
  path=Path(model['model_path'])/item['file']
  assert path.stat().st_size==item['bytes'] and sha(path)==item['sha256'],str(path)
  checked.append({'model':model['model'],'file':item['file'],'sha256':item['sha256']})
with (root/'pre_forward_full_model_hash_recheck_v1.json').open('x') as stream:
 json.dump({'all_registered_files_hash_match':True,'files':checked,'no_model_forward_yet':True},stream,indent=2);stream.write('\n')
PY
export PYTHONPATH="$ROOT/third_party/vllm-contractkv-tsc-r2-margin:$ROOT" PYTHON_BIN="$PY" VLLM_USE_V1=1
export TMPDIR="$DATA/tmp/contractkv-r1r" HF_HOME="$DATA/datasets/hf_cache"
export CONTRACTKV_MIN_CANDIDATE_MARGIN=-1000000000 CONTRACTKV_MAX_DEGRADATION=1000000000
export CONTRACTKV_SHADOW_CHUNK_TOKENS=128 CONTRACTKV_SHADOW_ROUND_TOKENS=128
export CONTRACTKV_PREFIX_METRICS=1 CONTRACTKV_PREFIX_INITIAL_ONLY=1
unset CONTRACTKV_R2_EXECUTION_TRACE CONTRACTKV_R2_VERIFY_TRACE
export EXTRA_VLLM_ARGS="--enable-prefix-caching --host 127.0.0.1" VLLM_STARTUP_POLLS=360
mkdir -p logs/tsc_revision_r4
snapshot=logs/tsc_revision_r4/cost_adaptation_validation_launcher_snapshot_v1.sh
[[ ! -e "$snapshot" ]] || exit 41
cp scripts/run_tsc_revision_r4_cost_validation_v1.sh "$snapshot"
run_cell() (
  alias=$1 repeat=$2 policy=$3 lane=$4
  case "$alias" in
    qwen) model=Qwen3-8B;served=qwen3-8b;identity=Qwen3-8B;;
    mistral) model=Mistral-7B-Instruct-v0.3;served=mistral-7b;identity=Mistral-7B-Instruct-v0.3;;
    llama) model=Llama-3.1-8B-Instruct;served=llama-3.1-8b;identity=Llama-3.1-8B-Instruct;;
    *) exit 42;;
  esac
  studyroot=results/tsc_revision_r4/cost_adaptation_validation_v1
  cell="template-fanout_${alias}_${policy}_r${repeat}";base="$ROOT/$studyroot/cells/$cell";port=$((9960+lane))
  mkdir -p "$base";[[ ! -e "$base/raw.jsonl" && ! -e "$base/runtime_manifest.json" ]] || exit 41
  sessions=results/tsc_revision_r4/cost_adaptation_validation_inputs_v1/faithful_selected_sessions_v1.jsonl
  export CONTRACTKV_POLICY_HASH="$(sha256sum "$studyroot/freeze.json" | awk '{print $1}')"
  export CONTRACTKV_MIN_RAW_TOKEN_MARGIN=-inf CONTRACTKV_MIN_CANDIDATE_TOKEN_MARGIN=-inf
  if [[ "$policy" != raw-order ]];then export CONTRACTKV_MIN_RAW_TOKEN_MARGIN=.0625 CONTRACTKV_MIN_CANDIDATE_TOKEN_MARGIN=.125;fi
  export CONTRACTKV_PREFIX_METRICS_LOG="$base/metrics.jsonl"
  export VLLM_CACHE_ROOT="$ROOT/cache/tsc_revision_r4/cost-validation-$cell/vllm"
  export TRITON_CACHE_DIR="$ROOT/cache/tsc_revision_r4/cost-validation-$cell/triton"
  export TORCHINDUCTOR_CACHE_DIR="$ROOT/cache/tsc_revision_r4/cost-validation-$cell/inductor"
  "$PY" scripts/tsc_revision_r2_runtime_manifest_v2.py --root "$ROOT" --model "$DATA/models/$model" --gpu "$lane" --freeze "$studyroot/freeze.json" --registry results/tsc_revision_r4/model_registry_v1.json --sessions "$sessions" --cell "$cell" --output "$base/runtime_manifest.json"
  cleanup() { bash scripts/stop_vllm_server.sh --pid-path "$base/server.pid" --port "$port" || true; }
  trap cleanup EXIT
  bash scripts/run_vllm_server.sh --phase "cost-validation-$cell" --model-path "$DATA/models/$model" --served-model-name "$served" --port "$port" --gpu-ids "$lane" --tensor-parallel-size 1 --dtype float16 --max-model-len 16384 --max-num-seqs 2 --gpu-memory-utilization .88 --log-path "$ROOT/logs/tsc_revision_r4/cost_validation_v1_${cell}_server.log" --pid-path "$base/server.pid"
  "$PY" scripts/tsc_revision_r2_prefix_smoke_logged.py --base-url "http://127.0.0.1:$port/v1" --model "$served" --policy-hash "$CONTRACTKV_POLICY_HASH" --repeats 1 --output "$base/pre_measurement_control.jsonl" --evidence "$base/pre_measurement_full_ids.jsonl"
  "$PY" scripts/tsc_revision_r4_cost_study_live_v1.py --protocol configs/tsc_revision_r4_input_fidelity_preserved_generation_v1.json --catalog results/tsc_revision_r4/development_fit_v3/calibration_v1.json --previous-catalog configs/tsc_revision_r3_catalog_v1.json --profile balanced --cost-profile results/tsc_revision_r4/development_cost_profile_candidate_v1.json --sessions "$sessions" --model "$served" --model-identity "$identity" --study template-fanout --policy "$policy" --base-url "http://127.0.0.1:$port/v1" --cell-id "$cell" --policy-hash "$CONTRACTKV_POLICY_HASH" --repeat "$repeat" --tenants-per-template 10 --output "$base/raw.jsonl" --summary "$base/summary.json" --metrics-events "$base/metrics.jsonl" --input-adapter-record "$base/input_adapter_execution_v1.json"
  echo "FIDELITY_INDEPENDENT_CELL_COMPLETE $cell lane=$lane"
)
run_lane() {
 lane=$1
 for repeat in 1 2 3;do
  [[ $(((repeat-1)%2)) -eq $lane ]] || continue
  case "$repeat" in
   1) policies="raw-order cost-adapted risk-tail";;
   2) policies="risk-tail raw-order cost-adapted";;
   3) policies="cost-adapted risk-tail raw-order";;
  esac
  for policy in $policies;do run_cell qwen "$repeat" "$policy" "$lane";done
 done
}
run_lane 0 > logs/tsc_revision_r4/cost_validation_v1_lane0.log 2>&1 & lane0=$!
run_lane 1 > logs/tsc_revision_r4/cost_validation_v1_lane1.log 2>&1 & lane1=$!
set +e
wait "$lane0";code0=$?
wait "$lane1";code1=$?
set -e
[[ $code0 -eq 0 && $code1 -eq 0 ]] || exit 50
echo COST_ADAPTATION_INDEPENDENT_NINE_COMPLETE
