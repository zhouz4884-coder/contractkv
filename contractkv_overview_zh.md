# ContractKV：让 Agent 的“隐藏稳定上下文”真正变成可安全复用的 KV 前缀

> **一句话概括**：ContractKV 将依赖合法但缓存不友好的 Agent Prompt 编译为可复用布局，在真实 vLLM EngineCore 内验证其行为，并以事务方式只发布经过认证的稳定前缀。

## 30 秒介绍

现代 LLM Agent 的 Prompt 中往往包含大量长期不变的系统指令、代码库上下文、文档和历史事实，但动态 Tool Observation、用户问题和临时状态会插在这些稳定内容之前或中间。即使启用了 vLLM Automatic Prefix Caching，缓存系统也只能复用从 Token 0 开始完全相同的连续前缀，因此大量“语义稳定但位置不连续”的上下文仍会被每轮重复 Prefill。

ContractKV 的核心思想不是再造一个 KV Cache，而是让现有高性能 Prefix Cache **看到并安全复用原本被动态片段遮挡的稳定上下文**：

1. 将 Prompt 建模为 **Segment Dependency Graph**；
2. 编译出依赖合法、缓存友好的布局；
3. 在同一推理后端验证布局变化是否保持模型行为；
4. 只有验证通过，才事务化发布真实 Token LCP 内、Block-aligned 的稳定前缀；
5. 任意失败、超时、取消、策略不匹配或证书过期，均 Fail-closed 回退 Raw Order。

---

# 核心结果：不是“快一点”，而是改变了系统排队状态

## Qwen3-8B：主系统结果

在已经开启 vLLM Automatic Prefix Caching 的生产级基线上，ContractKV 仍然取得：

| 指标 | 结果 |
|---|---:|
| 总 New-Prefill Work | **降低 59.13%** |
| Net Mean TTFT，Concurrency 1 | **降低 35.99%** |
| Net Mean TTFT，Concurrency 2 | **降低 41.66%** |
| Net Mean TTFT，Concurrency 4 | **降低 39.56%** |
| 1000 ms SLO Goodput，Concurrency 1 | **1.75×** |
| 1000 ms SLO Goodput，Concurrency 2 | **4.93×** |
| 1000 ms SLO Goodput，Concurrency 4 | **6.39×** |
| Certified Stable-Prefix Physical Reuse | **99.98%** |
| Dynamic-Suffix Reuse | **0 Tokens** |
| Completion Rate | **100%** |
| Task-Quality Violation | **0%** |

其中，饱和负载下的 SLO-compliant request rate 从 **0.115 req/s 提升至 0.736 req/s**。这不是把 539% 简单包装成“容量提升”，而是一个清晰的系统现象：在排队拐点附近，减少 Prefill Work 会产生非线性的 SLO Goodput 放大。

## Mistral-7B-Instruct-v0.3：前瞻性跨模型验证

Mistral 不是事后挑选的成功样本。模型身份、数据切分、开发门禁、Held-out 门禁、Verifier 和停止规则均在打开封存测试集之前冻结。

50 个 Sealed Held-out Sessions、450 个 Future Requests 的结果：

| 指标 | 结果 |
|---|---:|
| Completion | **450/450，100%** |
| Safe Certificate Coverage | **25/50，50%** |
| Unsafe Certified Sessions | **0** |
| Future-Turn Quality Violations | **0** |
| 最大质量下降 | **0.02，低于 0.03 门限** |
| New-Prefill Reduction | **39.46%** |
| Net Mean TTFT Reduction | **32.32%** |
| Certified Stable-Prefix Reuse | **99.96%** |
| Dynamic-Suffix Reuse | **0 Tokens** |

负载扩展中：

- Concurrency 1：Mean TTFT **降低 35.83%**；
- Concurrency 4：Mean TTFT **降低 36.46%**，p95 从 **4032.99 ms 降至 3179.88 ms**；
- 两档 New-Prefill Reduction 均保持 **39.46%**。

这证明 ContractKV 不是 Qwen-only 优化。

## Llama-3.1-8B：负结果揭示了证书作用域，而不是缓存机制失败

Llama 上，底层机制仍然有效：

- New-Prefill Work **降低 30.66%**；
- Mean TTFT **降低 26.68%**；
- Certified Prefix Reuse **99.924%**；
- Dynamic-Suffix Reuse **0 Tokens**。

最初的失败来自证书思想中的时间作用域错误：系统把 Turn 0 的验证结果当成整个 Session 的安全证明。当后续 Tool Observation 改变时，旧证书已经失效，却没有重新验证。

对 11 条可复现问题请求进行 Fresh Recertification：

- **10 条被严格 Verifier 拒绝或判定 INCOMPLETE**；
- **1 条未复现原质量下降**；
- **Fresh Verifier PASS + Quality Bad = 0**。

因此，准确诊断是 **Stale Certificate Scope**，而不是 RoPE、Tokenizer、Llama 架构或 vLLM Prefix Cache 失效。

最终抽象是：

> ContractKV 提供模型无关的事务化 KV/Cache Substrate；安全发布由绑定 Model、Task、Layout 和 Observation State 的 Scoped Behavioral Certificate 控制。

---

# 四项核心创新

## 1. Dependency-Constrained Cache-Aware Layout Compiler

现有 Prefix Cache 只能利用已经存在的相同 Token Prefix。ContractKV 首先解决“Prefix 从哪里来”的问题：

- 将 System Prompt、稳定上下文、Tool Observation、Query、History 等建模为带依赖的 Typed Segments；
- 只在依赖约束允许的拓扑序中搜索；
- 查询真实 Physical Prefix-Cache Residency；
- 选择能最大化可复用稳定前缀、同时不违反语义依赖的布局。

这不是任意重排，也不是静态 Canonicalization，而是 **Semantic Legality 与 Physical Cache State 的联合编译**。

## 2. In-Engine Compact Behavioral Verification

布局合法不代表模型行为一定不变。ContractKV 在同一 vLLM 后端中，对 Raw Answer Token Path 进行 Teacher-Forced Strict Top-1 Attestation。

为了避免完整 Prompt-Logprob 数据穿过前端控制面，ContractKV 在 vLLM 0.10.2 中实现 Source-Level Compact Verifier Channel：

| 指标 | Full Prompt-Logprob | Compact Result |
|---|---:|---:|
| HTTP Payload | 831,262 Bytes | 平均 387 Bytes |
| EngineCore Compact Object | — | 最大 231 Bytes |
| Egress Reduction | — | **2,147.96×** |

实现复用现有 EngineCore/ZMQ 通道，没有新增 Socket，并通过：

- Normal API Regression：**200/200**；
- Sequential Compact Lifecycle：**100/100**；
- Concurrent Lifecycle：**20/20**；
- Timeout、Cancel、Disconnect、Shutdown 后 **0 Future Leak**。

## 3. Prefix-Selective Transactional Promotion

Verifier 不是日志工具，而是 Cache Publication 的事务提交条件。

只有当 VerifyReport 为 PASS 且 Model、Policy、Layout、Prefix 和 Scope 身份一致时，系统才提交：

\[
C = B\left\lfloor\frac{\min(L_{stable},L_{computed})}{B}\right\rfloor
\]

其中 \(B\) 是 KV Block Size。该规则保证只发布：

- 真实 Token LCP 内的前缀；
- 完整 KV Blocks；
- 稳定 Segment 对应的部分。

FAIL、INCOMPLETE、Policy Mismatch、Timeout、Cancel 和 Disconnect 均满足：

\[
\Delta \text{Global Cache Visibility}=0
\]

因此，ContractKV 不会把未经验证的 Candidate State 泄漏到未来请求。

## 4. Scoped Behavioral Certificate

Llama 的因果审计揭示了一个重要系统规律：

\[
\text{Current-Turn Attestation}\not\Rightarrow\text{All-Future-Turn Safety}
\]

证书必须显式绑定：

- Model Identity；
- Policy Identity；
- Layout Hash；
- Stable-Prefix Hash；
- Task Family；
- Observation/Dependency State；
- Validity Mode。

相关状态改变时，证书失效；无法重新认证时，系统 Fail-closed 回退 Raw Order。这个边界使 ContractKV 从“经验缓存技巧”提升为一个具有明确安全作用域的 Serving Control Plane。

---

# 为什么现有系统还不够

## vLLM APC / Radix Cache 的能力边界

现有 APC 或 Radix Cache 擅长回答：

> 当前请求与历史请求有多少完全相同的 Token Prefix？

ContractKV 解决的是更前置的问题：

> Agent Prompt 中明明存在大量稳定内容，为什么它们不是 Prefix？能否在不改变任务行为的前提下，把它们变成 Prefix？

因此二者不是替代关系：

- vLLM/SGLang 提供高性能 Prefix Storage 与 Lookup；
- ContractKV 提供 Dependency-Aware Layout、Behavioral Attestation 和 Transactional Publication。

ContractKV 可以看作现有 Prefix-Cache Runtime 之上的 **Semantic-to-Physical Compilation and Safety Layer**。

---

# 实验规模与证据链

当前冻结证据包括：

- Unified Dataset Pool：**1,300 Samples**；
- LongBench：600；RULER：200；RepoBench：500；
- Live-Serving Partition：761；
- Frozen Qwen Quality Pool：734 Candidates，734/734 Identity Auditable；
- Qwen Phase 19B：50 Sessions、10 Turns、4 Policies、3 Load Tiers，**6,000 Records**；
- Mistral：25 Development Sessions + 50 Sealed Held-out Sessions；
- Llama：50 Held-out Sessions + 11 条 Fresh Future-Turn Causal Audits；
- Real vLLM V1 Source-Level Integration、Physical Block IDs、Prefix Hits、Refcounts 与 Transaction Traces。

Qwen 冻结质量池中：

- 28 个 Fresh Unsafe Candidates 全部拒绝；
- Held-out Safe Coverage：71.98%；
- Stale Label、Identity Mismatch、Unexplained Join Mismatch 均为 0。

---

# 最强的一页式结论

> **ContractKV 不是另一个 Prefix Cache。**它将语义依赖合法但缓存不友好的 Agent Prompt 编译成可复用布局，在真实 Serving Engine 内验证行为，并以事务方式只发布经过认证的稳定前缀。

最具代表性的数字：

- **59.13%** less new-prefill work；
- **41.66%** lower net mean TTFT；
- **6.39×** 1000 ms SLO-compliant goodput near saturation；
- **2,147.96×** smaller verifier egress；
- **99.98%** certified physical prefix reuse；
- **0** dynamic-suffix tokens published；
- Qwen 与 Mistral 两个模型族通过安全与性能门禁；
- Llama 负结果被定位为 stale certificate scope，fresh verifier 对所有可复现坏请求均未错误放行。

## 推荐论文定位

**ContractKV: Scoped Behavioral Certificates for Transactional Prefix Reuse in Agentic LLM Serving**

推荐主张：

> ContractKV compiles dependency-valid agent prompts into cache-friendly layouts, verifies their behavior inside the serving engine, and transactionally publishes only scoped, certified stable prefixes.

推荐跨模型结论：

> The transactional serving substrate transfers across Qwen, Mistral, and Llama, while behavioral certificate validity must be explicitly scoped to model, task, layout, and observation state.

---

# Claim Boundary

本文不声称：

- 一次 Turn 0 认证可永久覆盖整个动态 Session；
- 所有模型和所有任务都具有相同的 Certificate Coverage；
- SLO Goodput 的 6.39× 等同于最大稳定容量提升 6.39×；
- New-Prefill Reduction 自动等价于相同比例的峰值显存降低。

本文建立的是：

1. 稳定内容可以通过依赖合法布局转换为真实可复用前缀；
2. 行为验证可以低干扰地集成进 Serving Engine；
3. 未验证状态不会污染全局 KV Cache；
4. Scoped Certificate 可以将模型相关的准入策略与模型无关的事务化 Cache Substrate 解耦；
5. 在 Qwen 和 Mistral 上，该设计带来显著端到端收益，并保持冻结质量门禁。

---

## Evidence Index

主要冻结报告：

- `docs/phase18_compact_egress_report.md`
- `docs/phase19b_task_bearing_end_to_end_report.md`
- `docs/phase20a_submission_quality_report.md`
- `docs/phase21a_certificate_scope_report.md`
- `docs/mistral_prospective_generalization_report.md`
- `docs/phase21_generalization_closeout.md`
