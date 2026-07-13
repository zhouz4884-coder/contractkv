# Submission Experiment Diagnostics

## Method-level finding

The original Llama failure was a certificate-contract error: a Turn-0
attestation was reused after the observation state changed. Fresh re-attestation
rejected ten of eleven reproducible bad rows, and the remaining drop did not
reproduce. The corrected design freezes qualification from development only and
fails closed outside the qualified model-task-layout scope.

## Engineering faults found and excluded

- An asynchronous result row inherited another future's `scope_errors`. The
  repair changes telemetry only and records before/after hashes; executed policy,
  timing, prefix metrics, and outputs are unchanged.
- The first SGLang launch expanded a `local` shell variable before assignment.
- Absolute Python invocation omitted the conda environment's `ninja` from PATH.
- The host CUDA toolkit is 11.2 although the isolated Torch wheel is cu126;
  FlashInfer JIT therefore lacked a compatible `cuda_fp8.h`. Every valid SGLang
  cell uses the same Triton attention and PyTorch sampling backend with
  RadixAttention enabled.
- A stale watcher launched a duplicate external replay, and forced parent-only
  termination left an orphan scheduler. All partial files were discarded. The
  final runner holds a single-driver `flock` and terminates an isolated process
  group per fresh server cell.
- Updating the shell runner while its first process was still reading the file
  corrupted that process's tail parse after Qwen completed. A strict resumable
  cell gate now skips only 500-row, 450-future-request, fully completed cells;
  the repaired runner resumed at Mistral without overwriting Qwen evidence.
- The isolated SGLang environment initially lacked `protobuf`, which the
  Mistral tokenizer requires. The dependency is pinned in the conda-first
  installer; no model or result code changed.
- The per-cell `mean_newly_allocated_blocks` diagnostic used a request-lifetime
  maximum that included decode growth. The final memory table reconstructs
  initial prompt allocation from effective unique minus reused blocks, and the
  reproduction code now reads the initial scheduler event directly. Physical
  IDs, same-snapshot refcounts, block-pool high-water, TTFT, and outputs were
  unaffected.

These are environment, orchestration, or telemetry bugs. None of their partial
outputs enters a summarized result or paper artifact.
