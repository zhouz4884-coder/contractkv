#!/usr/bin/env bash
set -euo pipefail
ROOT=/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv
DATA=/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9
PY=/home/user/miniconda3/envs/contractkv-cu128/bin/python
cd "$ROOT"
study=results/tsc_revision_residency_20261017
"$PY" - <<'PY'
import hashlib,json,subprocess
from pathlib import Path
p=Path('results/tsc_revision_residency_20261017')
sha=lambda f:hashlib.sha256(Path(f).read_bytes()).hexdigest()
f=json.loads((p/'probe_freeze_v1.json').read_text())
receipt=json.loads((p/'probe_pre_forward_publication_v1.json').read_text())
assert receipt['before_first_probe_forward'] and receipt['remote_commit_verified']
assert receipt['freeze_sha256']==sha(p/'probe_freeze_v1.json')
for x in f['files']: assert sha(x['path'])==x['sha256'],x['path']
assert not list((p/'probe_cells_v1').glob('*/responses.jsonl'))
assert not subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader,nounits'],text=True).strip()
checks=[]
for m in json.loads(Path('results/tsc_revision_r4/model_registry_v1.json').read_text())['models']:
 for x in m['files']:
  q=Path(m['model_path'])/x['file'];assert q.stat().st_size==x['bytes'] and sha(q)==x['sha256']
  checks.append({'model':m['model'],'file':x['file'],'sha256':x['sha256']})
for x in json.loads(Path('results/tsc_revision_r4/input_fidelity_validation_v1/freeze.json').read_text())['files']:
 assert sha(x['path'])==x['sha256'],x['path']
with (p/'probe_pre_forward_integrity_v1.json').open('x') as out:
 json.dump({'model_files':checks,'primary248_source_bytes_match':True,
            'gpu_snapshot':subprocess.check_output(['nvidia-smi','--query-gpu=index,name,uuid,memory.used','--format=csv'],text=True)},out,indent=2)
PY
export PYTHON_BIN="$PY" VLLM_USE_V1=1
export PYTHONPATH="$ROOT/scripts/tsc_residency_trace_v1:$ROOT/third_party/vllm-contractkv-tsc-r2-margin:$ROOT"
export TMPDIR="$DATA/tmp/contractkv-r1r" HF_HOME="$DATA/datasets/hf_cache"
export CONTRACTKV_POLICY_HASH=20c10422e075df1e855665668d94d4df408ee664571738a035c1ef60564faf5f
export CONTRACTKV_MIN_CANDIDATE_MARGIN=-1000000000 CONTRACTKV_MAX_DEGRADATION=1000000000
export CONTRACTKV_MIN_RAW_TOKEN_MARGIN=.0625 CONTRACTKV_MIN_CANDIDATE_TOKEN_MARGIN=.125
export CONTRACTKV_SHADOW_CHUNK_TOKENS=128 CONTRACTKV_SHADOW_ROUND_TOKENS=128
export CONTRACTKV_PREFIX_METRICS=1 CONTRACTKV_PREFIX_INITIAL_ONLY=1
unset CONTRACTKV_R2_EXECUTION_TRACE CONTRACTKV_R2_VERIFY_TRACE
export EXTRA_VLLM_ARGS="--enable-prefix-caching --host 127.0.0.1" VLLM_STARTUP_POLLS=360
run_cell() (
 alias=$1
 case "$alias" in
  llama) model=Llama-3.1-8B-Instruct;served=llama-3.1-8b;;
  mistral) model=Mistral-7B-Instruct-v0.3;served=mistral-7b;;
  qwen) model=Qwen3-8B;served=qwen3-8b;;
 esac
 base="$ROOT/$study/probe_cells_v1/$alias";mkdir -p "$base"
 [[ ! -e "$base/runtime_manifest.json" && ! -e "$base/responses.jsonl" ]] || exit 41
 export CONTRACTKV_PREFIX_METRICS_LOG="$base/metrics.jsonl"
 export CONTRACTKV_RESIDENCY_TRACE="$base/backend_trace.jsonl"
 export VLLM_CACHE_ROOT="$ROOT/cache/tsc_revision_residency_20261017/$alias/vllm"
 export TRITON_CACHE_DIR="$ROOT/cache/tsc_revision_residency_20261017/$alias/triton"
 export TORCHINDUCTOR_CACHE_DIR="$ROOT/cache/tsc_revision_residency_20261017/$alias/inductor"
 "$PY" scripts/tsc_revision_r2_runtime_manifest_v2.py --root "$ROOT" --model "$DATA/models/$model" --gpu 0 --freeze results/tsc_revision_r4/input_fidelity_validation_v1/freeze.json --registry results/tsc_revision_r4/model_registry_v1.json --sessions "$study/probe_plan_v1.json" --cell "residency-$alias" --output "$base/runtime_manifest.json"
 cleanup() { bash scripts/stop_vllm_server.sh --pid-path "$base/server.pid" --port 9960 || true; }
 trap cleanup EXIT
 bash scripts/run_vllm_server.sh --phase "residency-$alias" --model-path "$DATA/models/$model" --served-model-name "$served" --port 9960 --gpu-ids 0 --tensor-parallel-size 1 --dtype float16 --max-model-len 16384 --max-num-seqs 2 --gpu-memory-utilization .88 --log-path "$base/server.log" --pid-path "$base/server.pid"
 "$PY" scripts/tsc_revision_residency_probe_v1.py --plan "$study/probe_plan_v1.json" --alias "$alias" --url http://127.0.0.1:9960 --output "$base/responses.jsonl"
 echo "RESIDENCY_DIAGNOSTIC_CELL_COMPLETE $alias"
)
for alias in llama mistral qwen;do run_cell "$alias";done
echo RESIDENCY_DIAGNOSTIC3_COMPLETE
