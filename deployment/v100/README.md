# ContractKV V100 Scale-Up Workspace

This directory is the deployment package for the Volta scale-up study on the
PBS node `gpu2`. It is intentionally separate from the validated RTX 3090
environment: the cluster driver is `530.30.02`, so the target CUDA runtime is
12.1 (with 11.8 only as a fallback), not the existing CUDA 12.8 stack.

## Confirmed platform

- Login host: `manager` (RHEL 7.6, PBS 6.1.1).
- Compute target: `gpu2`, 8 x Tesla V100-PCIE-32GB, SM70, 36 CPU cores, about
  181 GiB available memory at the initial audit.
- Storage root: `/data/home/zhoubin/contractkv_v100`. The `/data` root itself
  is not user-writable.
- Queue: `GPUDefq`. The PBS template requests `gpu2` explicitly and exits if
  the scheduler allocates another node.

## Frozen research scope

The V100 extension is a scale and hardware-portability study, not a new
mechanism search:

1. Qwen3-32B, TP=4, FP16.
2. Mistral-Small-24B-Instruct-2501, TP=4, FP16.
3. Llama-3.1-70B-Instruct, TP=8 by default; evaluate PP=2 x TP=4 only if the
   preflight topology and NCCL smoke are unsatisfactory, then freeze one mode
   before qualification.

All timed cells use `float16`, prefix caching, 8192 max model length,
concurrency 2, output limit 96, stable-word limit 1500, three fresh repeats,
raw fallback, strict top-1 attestation, and no dynamic-suffix publication.
Raw and ContractKV must use the same backend, trace, GPU allocation, and PBS
job cache policy.

## Phase order

1. `00_preflight_gpu2.pbs`: driver, topology, CUDA, NCCL, shared-memory, and
   cache-path audit.
2. V100 anchor parity: Qwen3-8B TP=1 and Qwen3-14B TP=2 smoke, APC telemetry,
   PSTP PASS/ABORT, and a 10-session RULER pair.
3. Prospective qualification on the frozen development split.
4. Common 30-session RULER replay, three paired fresh repeats.
5. Sealed all-workflow replay, then selected service-template and safety cells.
6. Aggregate only after every predecessor succeeds through PBS `afterok`.

Do not begin a later phase when its predecessor has not produced its manifest
and gate report. Do not use CPU offload, quantization, DeepSeek/MoE variants,
or a changed trace to force a large-model result.

## Model destinations

```text
/data/home/zhoubin/contractkv_v100/models/qwen3-32b
/data/home/zhoubin/contractkv_v100/models/mistral-small-24b
/data/home/zhoubin/contractkv_v100/models/llama3.1-70b-instruct
```

Download on the login node or a download-appropriate PBS job, never into
`/home`. Keep `HF_HOME`, ModelScope cache, and all model files under the
workspace.

## Use

```bash
cd /data/home/zhoubin/contractkv_v100
bash code/contractkv/deployment/v100/bootstrap_v100_workspace.sh
qsub pbs/00_preflight_gpu2.pbs
```

After the preflight completes, inspect the generated manifest in
`results/preflight/`. The environment-install path must be selected from the
recorded cluster facts; do not copy the RTX 3090 CUDA 12.8 environment.

## What this package contains

- `code/contractkv/`: source, experiments, docs, tests, patch, and compact
  audited results from the current workstation artifact.
- `protocols/`: immutable V100 model and hardware protocol records.
- `pbs/`: job templates with node and cache isolation.
- `artifacts/`: an SHA-256 manifest for the transferred source bundle.

Large model weights, Hugging Face caches, raw server logs, generated outputs,
and per-request traces stay only on `/data` and are not part of Git.
