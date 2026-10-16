#!/usr/bin/env bash
set -euo pipefail
ROOT="${ROOT:-/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv}"
DATA=/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9
PY=/home/user/miniconda3/envs/contractkv-cu128/bin/python
cd "$ROOT"
"$PY" - <<'PY'
import hashlib,json,subprocess
from pathlib import Path
for mode,count in [('closed',36),('arrival',54)]:
 root=Path(f'results/tsc_revision_r4/validation_{mode}_v1')
 audit=json.loads((root/'analysis/completion_audit_v1.json').read_text())
 archived=json.loads((root/'remote_archive_verification_v1.json').read_text())
 if not audit['execution_complete'] or audit['complete_cells']!=count or not archived['all_hashes_match']:
  raise RuntimeError('Complete and archive all original90 cells first')
receipt=json.loads(Path('results/tsc_revision_r4/input_fidelity_development_prerun_publication_v1.json').read_text())
if not receipt['public_remote_commit_verified'] or not receipt['before_first_new_input_forward']:
 raise RuntimeError('Verified public preregistration is required')
for condition in ('head','faithful'):
 root=Path(f'results/tsc_revision_r4/input_fidelity_development_{condition}_v1')
 if hashlib.sha256((root/'freeze.json').read_bytes()).hexdigest()!=receipt['freezes'][condition]:
  raise RuntimeError('Published prospective freeze changed')
 if list((root/'cells').glob('*/runtime_manifest.json')) or list((root/'cells').glob('*/raw.jsonl')):
  raise RuntimeError('Preserve all attempts; no implicit restart')
resident=subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader,nounits'],text=True).strip()
if resident: raise RuntimeError('GPU residents remain; do not interfere: '+resident)
PY
for condition in head faithful;do
  sha256sum -c "results/tsc_revision_r4/input_fidelity_development_${condition}_v1/source_checksums.sha256"
done
export PYTHONPATH="$ROOT/third_party/vllm-contractkv-tsc-r2-margin:$ROOT" PYTHON_BIN="$PY" VLLM_USE_V1=1
export TMPDIR="$DATA/tmp/contractkv-r1r" HF_HOME="$DATA/datasets/hf_cache"
export CONTRACTKV_MIN_CANDIDATE_MARGIN=-1000000000 CONTRACTKV_MAX_DEGRADATION=1000000000
export CONTRACTKV_SHADOW_CHUNK_TOKENS=128 CONTRACTKV_SHADOW_ROUND_TOKENS=128
export CONTRACTKV_PREFIX_METRICS=1 CONTRACTKV_PREFIX_INITIAL_ONLY=1
unset CONTRACTKV_R2_EXECUTION_TRACE CONTRACTKV_R2_VERIFY_TRACE
export EXTRA_VLLM_ARGS="--enable-prefix-caching --host 127.0.0.1" VLLM_STARTUP_POLLS=360
mkdir -p logs/tsc_revision_r4
snapshot=logs/tsc_revision_r4/input_fidelity_development_launcher_snapshot_v1.sh
[[ ! -e "$snapshot" ]] || exit 41
cp scripts/run_tsc_revision_r4_fidelity_development.sh "$snapshot"
run_cell() (
  condition=$1 policy=$2
  studyroot="results/tsc_revision_r4/input_fidelity_development_${condition}_v1"
  cell="template-fanout_qwen_${policy}_r1";base="$ROOT/$studyroot/cells/$cell";port=9930
  mkdir -p "$base";[[ ! -e "$base/raw.jsonl" && ! -e "$base/runtime_manifest.json" ]] || exit 41
  sessions="results/tsc_revision_r4/input_fidelity_development_inputs_v2/development_old_head_sessions_v2.jsonl"
  generation=configs/tsc_revision_r4_input_fidelity_head_generation_v1.json
  client=scripts/tsc_revision_r4_live.py;extra=()
  if [[ "$condition" == faithful ]];then
    sessions="results/tsc_revision_r4/input_fidelity_development_inputs_v2/development_faithful_sessions_v2.jsonl"
    generation=configs/tsc_revision_r4_input_fidelity_preserved_generation_v1.json
    client=scripts/tsc_revision_r4_fidelity_live.py
    extra=(--input-adapter-record "$base/input_adapter_execution_v1.json")
  fi
  export CONTRACTKV_POLICY_HASH="$(sha256sum "$studyroot/freeze.json" | awk '{print $1}')"
  export CONTRACTKV_MIN_RAW_TOKEN_MARGIN=-inf CONTRACTKV_MIN_CANDIDATE_TOKEN_MARGIN=-inf
  if [[ "$policy" != raw-order ]];then export CONTRACTKV_MIN_RAW_TOKEN_MARGIN=.0625 CONTRACTKV_MIN_CANDIDATE_TOKEN_MARGIN=.125;fi
  export CONTRACTKV_PREFIX_METRICS_LOG="$base/metrics.jsonl"
  export VLLM_CACHE_ROOT="$ROOT/cache/tsc_revision_r4/fidelity-development-$condition-$cell/vllm"
  export TRITON_CACHE_DIR="$ROOT/cache/tsc_revision_r4/fidelity-development-$condition-$cell/triton"
  export TORCHINDUCTOR_CACHE_DIR="$ROOT/cache/tsc_revision_r4/fidelity-development-$condition-$cell/inductor"
  "$PY" scripts/tsc_revision_r2_runtime_manifest_v2.py --root "$ROOT" --model "$DATA/models/Qwen3-8B" --gpu 0 --freeze "$studyroot/freeze.json" --registry results/tsc_revision_r4/model_registry_v1.json --sessions "$sessions" --cell "$cell" --output "$base/runtime_manifest.json"
  cleanup() { bash scripts/stop_vllm_server.sh --pid-path "$base/server.pid" --port "$port" || true; }
  trap cleanup EXIT
  bash scripts/run_vllm_server.sh --phase "fidelity-development-$condition-$cell" --model-path "$DATA/models/Qwen3-8B" --served-model-name qwen3-8b --port "$port" --gpu-ids 0 --tensor-parallel-size 1 --dtype float16 --max-model-len 16384 --max-num-seqs 2 --gpu-memory-utilization .88 --log-path "$ROOT/logs/tsc_revision_r4/fidelity_development_${condition}_${cell}_server.log" --pid-path "$base/server.pid"
  "$PY" scripts/tsc_revision_r2_prefix_smoke_logged.py --base-url "http://127.0.0.1:$port/v1" --model qwen3-8b --policy-hash "$CONTRACTKV_POLICY_HASH" --repeats 1 --output "$base/pre_measurement_control.jsonl" --evidence "$base/pre_measurement_full_ids.jsonl"
  "$PY" "$client" --protocol "$generation" --catalog results/tsc_revision_r4/development_fit_v3/calibration_v1.json --previous-catalog configs/tsc_revision_r3_catalog_v1.json --profile balanced --sessions "$sessions" --model qwen3-8b --model-identity Qwen3-8B --study template-fanout --policy "$policy" --base-url "http://127.0.0.1:$port/v1" --cell-id "$cell" --policy-hash "$CONTRACTKV_POLICY_HASH" --repeat 1 --tenants-per-template 10 --output "$base/raw.jsonl" --summary "$base/summary.json" --metrics-events "$base/metrics.jsonl" "${extra[@]}"
  echo "TASK_FIDELITY_DEV_CELL_COMPLETE $condition $cell"
)
run_cell head raw-order
run_cell faithful risk-tail
run_cell faithful raw-order
run_cell head risk-tail
for condition in head faithful;do
  base="results/tsc_revision_r4/input_fidelity_development_${condition}_v1"
  auditor=scripts/tsc_revision_r4_live_summary.py
  if [[ "$condition" == faithful ]];then auditor=scripts/tsc_revision_r4_fidelity_summary.py;fi
  "$PY" "$auditor" --root "$base" --output "$base/analysis"
  "$PY" scripts/tsc_revision_r4_strata_calibration.py --root "$base" --output "$base/analysis"
  "$PY" scripts/tsc_revision_r4_output_length_audit.py --root "$base" --output "$base/analysis/output_length_audit_v1.json"
  "$PY" scripts/tsc_revision_r4_package_fidelity.py --root . --study "input_fidelity_development_${condition}_v1"
  "$PY" scripts/tsc_revision_split_raw_archive.py --archive "$base/input_fidelity_development_${condition}_v1_raw_evidence_v1.tar.gz"
  "$PY" scripts/tsc_revision_verify_archive.py --root "$base" --archive "$base/input_fidelity_development_${condition}_v1_raw_evidence_v1.tar.gz" --output "$base/remote_archive_verification_v1.json"
done
echo TASK_FIDELITY_KNOWN_SOURCE_FOUR_GRID_COMPLETE_AND_ARCHIVED
