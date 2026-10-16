# 输入保真与成本修复：原始文献核对

核对日期：2026-10-16。用途是实验设计与工程判断，未修改正文或参考文献表。学术检索 MCP 本会话未提供，改用正式会议、ACL Anthology 与作者来源核对。下列为已核对的原始来源，未以搜索摘要替代本系统实测。

| 工作与正式来源 | 可以借鉴的内容 | 对 ContractKV 的边界 |
| --- | --- | --- |
| [Vidur: A Large-Scale Simulation Framework for LLM Inference，MLSys 2024](https://proceedings.mlsys.org/paper_files/paper/2024/hash/b74a8de47d2b3c928360e0a011f48351-Abstract-Conference.html) | 使用实验 profiling 与预测模型组合，区分执行配置和成本来源。提示我们先检查实际长度、缓存读和执行形状，再决定简单公式是否足够。 | 不移植完整模拟器；本系统少量 DEV 分位数不是 Vidur 精度复现，也不是硬尾延迟保证。 |
| [RepoBench: Benchmarking Repository-Level Code Auto-Completion Systems，ICLR 2024](https://proceedings.iclr.cc/paper_files/paper/2024/hash/d191ba4c8923ed8fd8935b7c98658b5f-Abstract-Conference.html) | RepoBench-C 依据跨文件与文件内上下文预测下一行，应保留代码前缀和格式。 | 下一行未必构成独立 AST 语句；但这不证明全部既有语法拒绝错误。当前主验证保持原准入，不取消保护。 |
| [Parrot: Efficient Serving of LLM-based Applications with Semantic Variable，OSDI 2024](https://www.usenix.org/conference/osdi24/presentation/lin-chaofan) | 应用级输入/输出变量暴露数据依赖，使服务端能理解跨请求工作流。可支持审计 CALC 前的真实任务结构与依赖。 | 不证明 ContractKV 的重排行为等价、授权安全、原 Table I 数字或生产模板频率。 |
| [Taming Throughput-Latency Tradeoff in LLM Inference with Sarathi-Serve，OSDI 2024](https://www.usenix.org/conference/osdi24/presentation/agrawal) | 长 prefill 与 decode 的混合服务会形成吞吐和延迟取舍，应关注其他请求受到的阻塞。 | 当前两请求 wave 中的同步注册等待有自己的账本证据；不把它全归为同一种 GPU 干扰，也不移植 chunked-prefill 调度器。 |
| [LongBench: A Bilingual, Multitask Benchmark for Long Context Understanding，ACL 2024](https://aclanthology.org/2024.acl-long.172/) | 长任务评测需要保留任务信息和任务类别；本轮裁剪必须与答案位置、模型分数无关。 | 论文任务定义不自动批准我们的裁剪器。具体保真度依靠原文片段、关键字段、实际 Prompt IDs 和 omission 账本验证。 |
| [Prompt Cache: Modular Attention Reuse for Low-Latency Inference，MLSys 2024](https://proceedings.mlsys.org/paper_files/paper/2024/hash/a66caa1703fe34705a4368c3014c1966-Abstract-Conference.html) | 显式 schema 描述可复用 prompt 模块，说明模块身份与复用结构需要明确。 | ContractKV 不将模块化缓存本身都视为新贡献；资格、授权与事务发布需分别给证据。 |
| [Preble: Efficient Distributed Prompt Scheduling for LLM Serving，ICLR 2025](https://proceedings.iclr.cc/paper_files/paper/2025/hash/5bc342f48de8264779952fac378f96dc-Abstract-Conference.html) | KV 复用 locality 和计算负载需共同考虑，不能只按逻辑共享量预测服务收益。 | 不实现分布式调度。已发布前缀 hash 也不等于当前完整驻留；我们只报告实际命中与未证实原因。 |

## 对当前工程决策的实际影响

1. 输入协议保真先独立验证，成本适配不混入原版对照。
2. profiling 至少区分条件 GPU RPC、完整 controller 和概率加权前置期望成本；它们不能混比。
3. 同时审计长输入的成本低估与旧收益 token cap。单独增加成本乘子可能损失有效覆盖。
4. 无法确认完整驻留时不能直接使用最乐观 warm 成本。选取保守估计的覆盖损失必须实测。
5. 保留正式验证的来源隔离。所有成本规则只依据此前已观察 DEV；新六来源输出不用于调参。
6. 这些文献没有提供本项目“质量完美”“全部 L0 波动与策略无关”或“原 Table I 必然仍为 80%/3%”的证明。
