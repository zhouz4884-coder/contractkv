# 原 Table III 完整成本复测：执行记录与入口

状态：**输入和计时方案已冻结，GPU 尚未执行**。用户已明确选择等 RevBatch 结束后再运行，不得终止、抢占或混跑其他任务。

## 目的与界限

原请求日志已复现四配置的原报告，但历史失败/异常耗时缺失，不能靠统计推算补成真实测量。本次使用原冻结任务 ID、历史客户端源码及原策略进行新的配对复测。它是新增计时证据，不是恢复旧时间戳，也不是新的 source-disjoint 泛化实验。

固定四配置、三次独立重复、Raw/Contract 两路，共 24 个 fresh server cell、4,725 个未来配对。优先 Llama，然后 Qwen8B、Mistral、Qwen14B TP2。不得因为吞吐、覆盖、质量结果不佳而增删来源或改档位、margin、评分、输入预算。

## 已完成

- `protocol_v1.json`：四配置、输入、源码、进程顺序、成本口径和停止规则。
- `source_snapshot/`：Git `dcfa7d2` 对应完整提交的 scripts/configs/patches，356 个文件逐字节 SHA。
- `inputs/`：从旧服务器只读取得的四组原 session 和两个资格 manifest，共六文件。
- `frozen_cohort_CPU_check_v1.json`：每次重复的 1,575 个未来键与原日志完全对应；1,750 个 raw render 重复构造一致。旧完整 Prompt IDs 缺失，故尚不能声称历史逐 token 身份完全一致。
- `instrumentation_CPU_check_v1.json`：PASS/FAIL/异常三条控制路径全部进入 finally 计时，原 toy 决策未变化；两份历史驱动的 AST 改写可编译。这是 CPU 控制流检查，不是模型或性能结果。
- `freeze_v1.json`：以上协议和执行补丁的冻结 SHA。

## 执行前必须做的检查

1. 阅读 `docs/tsc_revision_remaining_work_audit_20261018_zh.md` 和当前远程 GPU 状态。两张设备应是 GPU-ef01d441-985f-50b3-6e64-5d4c3e2def3a、GPU-a696ce9a-7137-cf6f-b4d3-deb992a72f28。仍有无关 compute PID 时退出本次检查，不启动测量、不杀进程。
2. 用现有本机 Credential Manager helper 连接 `user@10.15.1.57:2222`。不要打印或复制凭据。远程工作区在 `/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv`；所有副本、环境、缓存、日志均放该 8TB 卷。
3. 校验 `freeze_v1.json`、全部输入和 snapshot SHA。准备独立的 replay 目录；禁止覆盖历史结果或部分续跑。
4. 新测量前重新检查四模型 tokenizer/config/所有 safetensors shard 的完整性和 SHA。前三模型与 `results/tsc_revision_r4/model_registry_v1.json` 对照；14B 要核对 index 所列八分片并在首个测量前登记完整 SHA，不能把缺失的旧模型 hash 称为已经恢复。
5. 对保留的 vLLM 分支建立独立、只供本实验使用的副本与源码清单。Qwen 原分支为 `third_party/vllm-contractkv`，其余原分支为 `third_party/vllm-contractkv-phase19c`。不得在共享分支上安装/卸载 hook。需核查现有分支相对历史补丁的兼容性；若不能证明是纯计时改动，先完成有记录的兼容性检查，不能直接宣称 July 执行逐字节复现。
6. 原驱动、候选、预算和 scope 不变。Llama manifest 指定 16 pieces、L0/1/2/3=0/.25/.75/1；不要采用 shell 中另一版本的默认 ladder。Qwen14B 原 stable-word-limit 是 2600，不能误用另一项独立成本实验的 1500。
7. 预检实际 tokenizer 的所有 turn/候选长度，检查窗口和 EOS 余量。预检失败不能静默裁剪或删来源，须独立记录诊断。

## 计时入口

新增入口 `scripts/tsc_tableIII_instrument_frozen_client_v1.py` 在内存 AST 中仅给 canary/controller 循环加 try/finally 计时，并给 raw-reference、每次 compact verification 加异常也保留的计时。历史源码文件本身不改。

Linux 调用形式如下，实际 args 必须从 `protocol_v1.json` 及 snapshot 的原 runner 提取并保存至 cell manifest：

```text
<python> scripts/tsc_tableIII_instrument_frozen_client_v1.py
  --snapshot-root <frozen-source-root>
  --module phase19b_end_to_end_live
  --audit-dir <new-cell/audit>
  -- <all original frozen driver arguments>
```

Llama 用 `phase22_llama_broad_live`。需再完成隔离 server orchestration；目前**没有已经跑起来的 GPU worker**。在未核查 runtime 和 input shapes 前，不得把该入口的 CPU 可编译称为完整 live runner 已验收。

原 CLI slack 若参与策略/scope，保留原值，避免改变方法；在输出计账时设 slack=0，并另外直接报告完整 client wall。不能再用 `verification_ms=0` 代替失败控制器费用。记录每次成功/拒绝/异常、raw/reference、token 准备、RPC、完整 controller 和完整服务 wall；三次新鲜进程，不按结果提前停止。

## 分析与验收

- 所有预定 cell、请求、失败均计入；主表按同一模型/进程/样本键配对。
- 分别报告完整 wall 吞吐、业务 TTFT、全部 controller 成本摊销的零 slack 均值，及原 residual-RPC 分解；不混称同一指标。
- 核对控制器次数、每次下降尝试计时、异常计时是否完备，确认不再发生原 Llama 33 次丢失问题。
- 计时复测与旧 37.81/44.69/31.72/29.41% 并列保留；旧记录的上界/缺口仍如实存在，不能覆盖历史文件。
- 若新结果没有收益，也先保留并分析实际成本/覆盖/输出长度；不得为追回旧数字重新选样本或调阈值。
- 实验完成后再决定正文表格与边界怎么更新。当前正文草稿保存在另一审计目录的 patch 中，未发布新 PDF，Response Letter 未开始。

## 资源快照

本轮预检两卡分别由 RevBatch 环境的 PID 91393/91394 占用，快照见 `results/tsc_revision_remaining_audit_20261018/legacy_replay_preflight_v1.json`。该 PID/显存信息会过时，执行前必须刷新，不能仅据旧 PID 是否消失判断 GPU 已可独占。
