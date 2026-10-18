#!/usr/bin/env bash
set -euo pipefail
DATA=/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9
ROOT="$DATA/VLAtest/contractkv"
PY=/home/user/miniconda3/envs/contractkv-cu128/bin/python
STUDY="$ROOT/results/tsc_tableI_remeasurement_20261018"
cd "$ROOT"
export PYTHONPATH="$DATA/env_overlays/contractkv-tableI-native-20261018-v1:$ROOT"
export VLLM_USE_V1=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 TOKENIZERS_PARALLELISM=false
export HF_HOME="$DATA/datasets/hf_cache" TMPDIR="$DATA/tmp/contractkv-r1r"
unset CONTRACTKV_PREFIX_METRICS CONTRACTKV_PREFIX_INITIAL_ONLY CONTRACTKV_PREFIX_METRICS_LOG
unset CONTRACTKV_R2_EXECUTION_TRACE CONTRACTKV_R2_VERIFY_TRACE
"$PY" - "$STUDY" <<'PY'
from pathlib import Path
import json,subprocess,time
root=Path(__import__('sys').argv[1])
apps=subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader,nounits'],text=True)
assert not apps.strip(), 'GPU resources changed before launch'
snapshot=subprocess.check_output(['nvidia-smi','--query-gpu=index,name,uuid,memory.used','--format=csv,noheader'],text=True)
with (root/'launch_resource_snapshot_v1.json').open('x') as f:
 json.dump({'epoch':time.time(),'GPU_inventory':snapshot,'GPU_compute_processes_before_launch':apps},f,indent=2)
PY
run_repeat() {
 local rep=$1 lane=$2
 export CUDA_VISIBLE_DEVICES="$lane"
 export VLLM_CACHE_ROOT="$DATA/cache/tableI-native-20261018-r$rep/vllm"
 export TRITON_CACHE_DIR="$DATA/cache/tableI-native-20261018-r$rep/triton"
 export TORCHINDUCTOR_CACHE_DIR="$DATA/cache/tableI-native-20261018-r$rep/inductor"
 "$PY" -B scripts/tsc_tableI_survey_worker_v1.py --root "$STUDY" --repeat "$rep" --gpu "$lane" > "$STUDY/worker_r$rep.log" 2>&1
}
( run_repeat 1 0; run_repeat 3 0 ) & lane0=$!
( run_repeat 2 1 ) & lane1=$!
status0=0;status1=0
wait "$lane0" || status0=$?
wait "$lane1" || status1=$?
if [[ "$status0" != 0 || "$status1" != 0 ]];then
 echo "PRESERVE_FAILURE lane0=$status0 lane1=$status1";exit 31
fi
unset CUDA_VISIBLE_DEVICES
"$PY" -B scripts/tsc_tableI_analyze_survey_v1.py --root "$STUDY" --tokenizer "$DATA/models/Qwen3-8B" > "$STUDY/analysis.log" 2>&1
echo TABLEI_NATIVE_SURVEY_COMPLETE
