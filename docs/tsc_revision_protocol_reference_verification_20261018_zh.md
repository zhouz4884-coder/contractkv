# ContractKV：本轮测量与任务定义的三篇文献核对

核对日期：2026-10-18。使用 `nature-academic-search` 的citation-verification流程。该MCP服务未挂载，采用公开arXiv Atom API与会议官方页面交叉核对；API预检3/3可达。三个逻辑文献均核实标题、作者及正式会议信息，未发现条目身份冲突。原始API响应与SHA保存在 `results/tsc_final_existing_evidence_CPU_20261018/reference_verification_v1/`。不涉及新增GPU请求。

| 文献 | 核实结果 | 对当前工作的直接作用 |
| --- | --- | --- |
| RepoBench: Benchmarking Repository-Level Code Auto-Completion Systems；Tianyang Liu、Canwen Xu、Julian McAuley | verified；ICLR 2024；arXiv:2306.03091v2（预印本始于2023年，与正式会议年份分开） | 原始任务包含使用跨文件与文件内上下文预测下一行代码。由此需要保留真实CODE_PREFIX，并将合成Python赋值题与真实下一行补全分开统计。来源：[ICLR官方论文页](https://proceedings.iclr.cc/paper_files/paper/2024/hash/d191ba4c8923ed8fd8935b7c98658b5f-Abstract-Conference.html)。 |
| Vidur: A Large-Scale Simulation Framework for LLM Inference；Amey Agrawal等 | verified；MLSys 2024（Proceedings of Machine Learning and Systems 6）；arXiv:2405.05465v2 | 其模型结合执行profiling与预测建模，关注运行配置和工作负载。可借鉴按实际执行形状测量的原则，为Raw-only标定提供方法依据；本项目成本数字由自己的冻结GPU运行产生。来源：[MLSys官方论文页](https://proceedings.mlsys.org/paper_files/paper/2024/hash/b74a8de47d2b3c928360e0a011f48351-Abstract-Conference.html)。 |
| Parrot: Efficient Serving of LLM-based Applications with Semantic Variable；Chaofan Lin等 | verified；OSDI 2024；929–945页；arXiv:2405.19888v1 | 以应用输入/输出变量显露跨请求数据流，支持在服务层讨论请求关联。可用于解释为何需要应用级结构信息；ContractKV的布局资格、状态可见性和成本仍须由自己的实验支持。来源：[USENIX官方论文页](https://www.usenix.org/conference/osdi24/presentation/lin-chaofan)。 |

## 本轮采用的范围

1. **任务保真。** RepoBench-C的next-line定义不能直接推导出“答案必须是独立可解析的一条Python语句”。当前生产式对照仍保持原冻结的`one_python_statement`规则；若它排除了合法片段，应作为已声明输出契约的覆盖限制记录。真实RepoBench机制补充保留该guard，分别报告格式准入与行为认证。
2. **测量。** Raw-only先标定真实两张3090上的执行区间，再冻结load/SLO和正式配对。Vidur的仿真结果、误差及加速数字不进入ContractKV的实测表格；当前收益门禁也不因这份文献核对而变化。
3. **贡献表达。** Parrot支持“应用依赖值得暴露给服务层”这个研究背景。仅依据其摘要不能断言它实现或缺少ContractKV的某个具体安全机制；本文不把这次三篇条目核对当作完整prior-art排查或baseline复现。四项机制的必要性应对应自己的合法重排反例、真实准入、PSTP提交及模板摊销记录。

当前前三批冻结文件、模型、输入、门槛、scope、评分及GPU队列均未改变。文献核对用于记录方法依据和比较边界，正式论文与Response Letter继续后置。
