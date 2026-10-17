# ContractKV：零命中与物理驻留诊断

日期：2026-10-17。本轮实验已完成：全量CPU审计、三模型有界GPU机制探针及双端复算。未修改论文正文或正式Response Letter。

**结论：三个已知来源均直接重现了原生驻留回收导致的缺失命中；未发现支持修改CALC、PSTP或缓存身份实现的局部缺陷。本轮停止扩大GPU矩阵，保留原算法与全部不利记录。**

## 1. 本轮要回答的问题

保真主18实验中，已经获准编译的请求仍出现零/部分native prefix hit。不能把“行为资格有效”“PSTP已提交”“请求匹配该前缀”“物理KV当前驻留”“本次实际命中”视为同一件事。本轮沿这五个状态逐级核对；只有实证实现缺陷才触发修复及后续独立验证。

## 2. 全量CPU审计

输入为原保真主18中9个risk-tail cell，三模型各三次fresh-process重复，共5,400条业务请求，包含warm和future。对应原始输出、scheduler指标、认证请求/回复与runtime manifest均按实际request ID连接。原248项冻结代码/输入身份保持一致；另两个267/286项冻结也全部逐字节匹配。

| 模型 | 原记录异常 | 分布 | 已提交前缀缺口的token算术上限 |
|---|---:|---|---:|
| Llama-3.1-8B | 135零命中 | 三个HotpotQA来源；turn3/6/9各45 | 1,339,920 |
| Mistral-7B | 42零命中 | HotpotQA doc19；turn1/4/7为12/15/15 | 493,248 |
| Qwen3-8B | 12部分命中 | RepoBench VoucherVision；turn1，命中5,840/提交6,272 | 5,184 |

这些是三重复合计的前缀长度差，不是可保证恢复的GPU计算、时间或吞吐上界。

189条异常均可找到同波次后续完整命中peer，实际快照共享128–392个前缀物理块位置。实际客户端是先执行一对tenant完整十轮，再进入下一对；因此45/45/45不能推出连续十个tenant都miss，更不能证明缓存索引Bug。

全部compiled请求的稳定前缀Token IDs均匹配相应证书，提交长度为正且按16-token块对齐，认证请求的wire salt符合原policy hash与模板namespace。177条异常有此前完整命中的映射，首块backend hash一致；其余12条没有此前完整命中映射，不以推断补齐。旧业务wire/backend salt没有直接日志，CPU表中的业务salt明确标为冻结源码重建。

另对全部1,440条compiled业务逐一计算与认证payload的实际token LCP，均覆盖稳定前缀及提交边界，最小也超过提交长度39 tokens；首16个实际IDs无不一致。`LCP_supplement_v1/compiled_prompt_LCP_v1.csv`直接保留首16个IDs、LCP长度及salt来源，不能将物理缺失解释为这些已记录请求的前缀文本不匹配。

旧scheduler探针只在初次分配后、GPU步骤前记录，冷请求可能只暴露首128块。块有hash索引不等于该GPU步骤已经计算完成；这些快照也不足以恢复完整的驱逐历史。因此CPU结果支持“同波次先冷后热”，尚不能独立确定是正常回收还是发布/生命周期缺陷。

本地与远端独立重算：JSON对象全部相同，5,400行CSV逐字节相同。时间线SHA256为`ca6ca8b76a93bd6bde235227f5e1f67cf6225610ab1f51094109d5413031632c`。

## 3. 已冻结的最小GPU诊断

三个已观察来源各一个server cell：Llama/doc69、Mistral/doc19、Qwen/VoucherVision。每个重放前两对tenant完整十轮，并在第一次成功提交后插入两次串行、一次并发pair，在结尾再插入两次串行。上限138条业务、9次认证；冻结计划实际只有4次认证重放。无新来源、无margin放宽、无新驱逐策略。

使用原归档Prompt IDs、raw见证、候选路线、policy hash/salt，保留16K、FP16、max-num-seqs=2及0.88显存比例。固定IDs通过completion接口发送，wire回显IDs必须完全匹配；不重跑门禁决策。这是已知输入的机制实验，不能充作新的独立任务质量或原服务调度性能验证。

独立只读import hook调用原backend函数，记录实际lookup前salt、哈希及所有重复映射项，native eviction的旧hash/refcount/最后映射删除，认证发布的物理块映射及请求释放。原backend源码字节保持不变。同步日志开销使全部诊断计时不适合性能比较。

预注册Git提交：`245df96a54e93f8517125dab7ecdc38ecd148501`，已核对远端SHA后才启动模型。模型全部注册文件重新计算SHA256，未发现身份变化。

## 4. 参考依据与判定边界

[vLLM 0.10.2原生APC设计](https://docs.vllm.ai/en/v0.10.2/design/prefix_caching.html)说明，free queue中也包含有缓存hash、refcount为零的回收候选；分配队头块时会删除旧映射。命中块先touch，避免在当前分配中被回收。因此“free blocks仍很多”不能直接证明已提交前缀不应被驱逐。本轮以真实backend事件判因，文档和数量预算只用于提出可检验假设。

若实际salt/链一致，提交后连续使用可命中，而间隔raw工作后出现最后hash映射被native分配回收、随后lookup前确实不存在，则支持原生驻留/复用距离限制。若映射仍完整存在却不命中、相同授权业务使用不同salt，或发布后错误删除，则需进入局部实现修复。三个已知来源即使都支持前一种机制，也不能证明所有历史异常逐案均由同一原因产生。

## 5. GPU结果与最终分支

实际完成3个server cell、138条业务和4次认证，4次均通过原margin/EOS/PSTP检查。全部138条server回显Prompt IDs独立匹配冻结计划，全部138条输出IDs与各自旧归档相同；这仍只是已知来源的诊断复现，不增加held-out质量评估的独立分母。

| 模型 | compiled探针数 | 完整/零/部分命中 | 提交后立即复用控制 | 缺口的直接native驱逐证据 |
|---|---:|---:|---:|---:|
| Llama | 20 | 14 / 6 / 0 | 4/4完整 | 6/6 |
| Mistral | 16 | 10 / 6 / 0 | 4/4完整 | 6/6 |
| Qwen | 26 | 25 / 0 / 1 | 4/4完整 | 1/1 |

62条compiled中共有13次缺失命中。原波次重放分别贡献Llama 6、Mistral 5、Qwen 1次；Mistral另有1次来自末尾两轮raw之后的首次serial，后一次serial立即命中15,680 tokens。该控制没有删除。Llama及Qwen结尾两次serial均完整命中。

13次缺口都同时满足：实际backend salt与原namespace/policy一致；当前请求的提交前缀hash链与本进程认证发布一致；相应缺块在lookup前没有任何匹配映射；此前原生`_maybe_evict_cached_block`删除了该hash最后一个映射，删除时refcount=0。累计记录67,000个原生回收事件，均为refcount=0。没有观察到“正确映射仍驻留却未被查到”的反例。

Llama示例：c0-t2 raw请求在seq2583回收已提交前缀首块唯一映射；c0-t3 compiled在seq3566查找时首块为空，而资格registry仍保留690个边界。冷请求重新计算后，同波peer得到完整前缀命中。

Qwen重现5,840/6,272-token命中，缺口从第365号块开始（按0起算），不是首16个Token或salt不匹配。证书与请求链一致，缺口处的映射被native回收。它与整段零命中是同一生命周期机制的不同位置表现。

实际pool由相同0.88配置自动profiling得到，Llama与历史cell有1块差异（2,420对2,419）。因此这是机制验证，不是严格固定容量的服务性能复现。backend首parent hash还可能逐进程随机初始化；所有commit/lookup/eviction链只在同一进程内连接，不跨进程比较hex字符串。

**最终决定：不做生产算法补丁、不放宽scope/margin、不增加pinning/驱逐调度器，也不启动条件性的27单元修复验证。** 本轮建立了缺失的可审计观测链，支持正常驻留/复用距离解释；未满足“证实局部实现Bug后扩矩阵”的触发条件。资格有效不保证对应物理KV永久驻留。

这不证明189条历史异常逐案均由同一原因产生：旧记录没有完整eviction事件，本轮只对三个已知来源重放直接判因。也不证明当前回收策略没有优化空间，只是不将容量/调度优化包装成原系统Bug修复。

原主18的1.619/1.109/1.070×完整wall倍率已经包含实际miss及重算成本。本轮没有新的性能修复对照，不能凭token缺口将它们上调，更不能宣称1.25–1.40×的修复目标已经达到。原p99代价、成本适配负结果、L0归因限制和历史Table I来源缺口保持原记录。

所有GPU server已清理，复核时两卡无compute进程。首次封存误依赖已被正常cleanup删除的PID文件而中止；部分zip及失败说明保留，完整封存改为v2，不重跑GPU、不覆盖原始事件。

## 6. 可复核产物

- `results/tsc_revision_residency_20261017/cpu_audit_v1/residency_identity_timeline.csv`：5,400条请求时间线。
- `results/tsc_revision_residency_20261017/cpu_audit_v1/residency_identity_audit_v1.json`：全部189条异常的证书、时序和peer证据。
- `results/tsc_revision_residency_20261017/independent_CPU_match_v1.json`：双端CPU重算核验。
- `results/tsc_revision_residency_20261017/probe_plan_v1.json`和`probe_freeze_v1.json`：有界探针协议及源码身份。
- `results/tsc_revision_residency_20261017/probe_analysis_v1/compiled_probe_trace.csv`：62条compiled的lookup/commit/eviction连接。
- `results/tsc_revision_residency_20261017/probe_analysis_v1/probe_mechanism_results_v1.json`：三模型完整结果、逐文件SHA及限制。
- `results/tsc_revision_residency_20261017/probe_archive_manifest_v2.json`和`probe_archive_v2.zip`：完整原始事件、实际输出、runtime和server日志。
- `docs/tsc_revision_residency_execution_20261017_zh.md`：自主决策与分支记录。
