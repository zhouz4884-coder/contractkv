# V100 Three-Model Scale-Up: Platform Audit

## Scope

This audit gates the frozen three-model ContractKV scale-up protocol on the
`gpu2` PBS node before any qualification or held-out serving result is claimed.
The target matrix is Qwen3-32B (TP=4), Mistral-Small-24B-Instruct-2501 (TP=4),
and Llama-3.1-70B-Instruct (TP=8), all in FP16 with the ContractKV-patched
vLLM source release `0.10.2`.

## Confirmed platform facts

PBS job `177794.manager` ran on `gpu2` and recorded:

| Check | Result |
|---|---|
| GPUs | 8 x Tesla V100-PCIE-32GB |
| Compute capability | 7.0 |
| Driver / advertised CUDA | 530.30.02 / 12.1 |
| Python | 3.10.6 |
| PyTorch / CUDA runtime | 2.4.1 / 12.1 |
| `torch.cuda.is_available()` | `true` |
| Visible CUDA devices | 8 |

All three target model directories passed strict local integrity checks: a
configuration, tokenizer, generation configuration, weight index, and every
indexed shard are present. This is an artifact-readiness statement only; it is
not a model-serving result.

## vLLM 0.10.2 gate

The exact patched source release declares `torch == 2.8.0` in both its build
requirements and CUDA requirements. The V100 runtime is deliberately pinned to
the driver-compatible `torch 2.4.1 + CUDA 12.1` stack. A source-install probe
was executed in an isolated PBS job so it could not contaminate the persistent
runtime or any later experiment.

The source build reached the native-extension stage and then stopped because
the node exposes neither `nvcc` nor a usable CMake executable. The host
toolchain is GCC 4.8.5 and CMake 2.8.12, whereas vLLM 0.10.2 requires
`cmake >= 3.26.1`; no CUDA compiler is installed on the node. A binary-only
dependency-resolution probe also cannot complete against the configured mirror
because it has no compatible `blake3` wheel. Even if that mirror gap were
removed, the frozen vLLM source requires `torch==2.8.0`, which does not match
the driver-compatible CUDA-12.1 PyTorch runtime.

This is a platform/toolchain gate, not a ContractKV implementation failure. No
source downgrade, model quantization, CPU offload, or unfrozen policy
substitution is permitted as a workaround.

## Consequence for the frozen experiment

The three-model qualification and held-out matrix may begin only after one of
the following reproducible paths succeeds:

1. the cluster provides a CUDA 12.1-capable build toolchain plus a
   `torch==2.8.0` build compiled for this driver and `sm_70`; or
2. the GPU driver is upgraded to the CUDA generation required by the official
   PyTorch 2.8/vLLM 0.10.2 binary stack, followed by a fresh preflight and
   vLLM server smoke test.

Until then, the workspace contains the complete frozen protocol, source patch,
models, strict integrity report, and machine-readable compatibility evidence,
but no performance claim from this V100 platform.

## Evidence locations on the cluster

- `/data/home/zhoubin/contractkv_v100/results/preflight/177794.manager/python_gpu_probe.txt`
- `/data/home/zhoubin/contractkv_v100/results/preflight/model_integrity_latest.csv`
- `/data/home/zhoubin/contractkv_v100/results/preflight/177800.manager-vllm-compat/`
- `/data/home/zhoubin/contractkv_v100/pbs/02_vllm_v100_compat_probe.pbs`
