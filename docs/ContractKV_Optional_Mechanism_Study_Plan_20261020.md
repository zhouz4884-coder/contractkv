# 附录候选：融合认证与可撤销驻留的有界机制实验

审稿优先级门槛已通过：`ContractKV_Reviewer_Priority_Audit_20261020.md`。没有发现尚需执行的审稿 GPU 单元，本实验独立于返修必做清单，不增加论文贡献项，默认只作为附录候选。

## 问题与冻结比较

1. 同一个候选先自由生成、再 teacher-force 是否存在可消除的重复计算？融合路径只从 **实际 Candidate decode** 收集 token、rank、top-2 logprob 和 EOS，仍通过原 native margin/PSTP 检查，且在释放 KV 之前决定是否发布。
2. 已获证前缀为何在跨来源访问后变冷？记录真实块池容量、分配时被驱逐的 hash、优先保留预算、实际 native hit；不是从证书存在推断驻留。
3. 若有收益，多少只是普通缓存替换策略的效果？Raw 使用相同预算、TTL、可回收机制作为对照。

六臂：Raw、当前 Strict、单次 TF-only、Fused、Fused+Residency、Raw+Residency。TF-only 明确缺少资格建立时的 Candidate 自由生成证明，仅作探索对照；后续自由生成对比不能删除失败。

两模型 Qwen3-8B/Mistral-7B；全部复用此前已经打开的四个原验证来源，**现在作为已知开发诊断来源使用**，不再称作独立于本优化的 held-out。包括三个 QA 来源的 12 个模型/tenant 条件和原 Repo L0 控制，保留已有成功与拒绝。

每臂/模型一个 fresh server，共 **最多 12 cells、384 业务请求**；每个精确条件访问四次。两个模型在各自固定 GPU 上执行，同模型六臂使用相同内容、固定轮转、窗口、预算、授权域及精确 scope。Qwen/Mistral 物理 pool 固定 1940/3550 blocks，16K、并发上限2，QA128/Repo384、greedy、seed14014。

所有在线准备、首次 Raw、资格/失败、日志/检查、排空计入直接 wall。模型加载在测量之外。它是串行闭环机制实验，不是开放到达 SLO 容量；原先八次访问的结果不能与本次四次访问直接相除。

## 驻留策略与安全边界

只给 free queue 中的 cached block 可撤销优先级：总预算为 pool 可用块数的 75%，分组 FIFO、120s TTL；分配压力下仍可回收，不修改 ref_cnt，不制造永不结束请求，不预取。Raw 控制使用同一策略保留普通完成请求的 prompt 前缀。该简单策略不作为新的算法贡献。

新 native 原型只进入本 study 的隔离 runtime，默认服务源码不改。模型/分词器身份沿用已登记完整 SHA，并检查当前全部 asset size/mtime；新的 runtime revision 单独绑定到本次真实源码清单，不能冒充旧运行时。

六项 CPU 检查先验证真实行索引、EOS/缺失失败、优先级可撤销、引用计数不变和容量不隐藏；这些不是 GPU 成果。GPU 后逐业务核实际 IDs、EOS、评分、认证费用、发布和 native hit。仅一个进程/臂，不构造性能 CI 或未见来源泛化结论。

## 预定停止条件

预定 12 cells 结束即停止，不按收益换来源、重调 margin、延长复用或挑好模型。若原型存在行为/EOS/发布不变量违反，则分支 NO-GO；若基础设施/接口失败，保留原日志，先分析能否在不改变科研规则下作单列兼容修复。不能以去掉校验使原型通过。

只有本轮机制证据同时支持完整行为、成本和实际命中改善，才值得以后另冻新来源验证；本轮不自动追加正式服务矩阵，也不把未独立验证的好数字放进正文。

实现参考是固定版本的 [vLLM 0.10.2 BlockPool](https://docs.vllm.ai/en/v0.10.2/api/vllm/v1/core/block_pool.html)、[sample logprobs](https://docs.vllm.ai/en/v0.10.2/api/vllm/logprobs.html) 与 [输出行结构](https://docs.vllm.ai/en/v0.10.2/api/vllm/v1/outputs.html)，实际兼容性以本机隔离源码和 GPU 证据为准。
