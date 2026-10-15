# ContractKV 大修补强实验闭环报告

本报告覆盖原有七项补强要求，以及针对 R1 新发现问题的 query 范围修复。实验执行完成与科学目标是否达到分开判定；原投稿稿件没有被本实验包覆盖，修稿和逐条回复属于后续工作。

## 执行与证据

- 原 R1：78/78 个 live 单元、25,650 次未来请求；本机复核通过，归档 423 个成员逐项哈希匹配。
- 新修复验证：45/45 个单元、28,350 次未来生成；三模型、五任务族、三次 fresh-process 重复。
- 长输出受控补测：9/9 个单元、135 次真实生成，其中 27 次 raw 参考和 108 次 raw/policy 未来生成。
- 新验证质量配对 16,200 对，其中编译路由 8,595 对；scope-invalid admission=0，拒绝后发布 token=0。
- 运行前冻结输入、代码和 backend 哈希；所有首次 raw、失败尝试与回退均保留。CPU 检查、机制控制、真实业务生成分别标注。

## 修复方法与实际质量

新 query 首次出现时先服务 raw，并用这次真实业务输出提供参考；随后只有该 query 自身通过验证的布局才可复用。验证器可以读取同 namespace/policy 中此前已批准、且仍实际驻留的稳定前缀；答案及 EOS 行仍全部检查。仅提取需要的 logprob 行，Transformer/KV 计算没有被省略成代理量。

这是受控修复变体：继承 family 最大级别并统一下降，检查答案/EOS 的 rank-one membership；辅助 margin/degradation 阈值设为宽界，未执行原论文的完整收益门禁。query-full 指全上下文验证计算，不代表复现原方法全部策略。因此新结果不替换原投稿的全工作流主表。

这也是保守的 query-catalog 模式：认证工作随不同 exact query 作用域的数量增长。fan-out 有意让多个 tenant 复用相同 benchmark 问题，不能据此推断生产中的重复 query 比例、任意新 query 的 O(1) 认证，或唯一 query 流上的收益；它与原投稿已资格化模板及其授权轨迹的结果分开解释。

以下总体分母同时包含首次 raw、冻结 L0 和验证失败回退。不同策略和两个场景有相关来源，不能把这些配对当成互相独立的样本。

| 场景 | 模型 | 策略 | 配对 | 编译 | token 分歧 总体/编译 | 下降>0.03 总体/编译 | 编译最大分数下降 | 平均分 raw→策略 |
|---|---|---|---|---|---|---|---|---|
| single-session | Llama-3.1-8B-Instruct | query-full | 1350 | 474 | 31/12 | 3/0 | 0.00000 | 0.34967→0.34969 |
| single-session | Llama-3.1-8B-Instruct | query-prefix | 1350 | 474 | 42/12 | 4/0 | 0.00000 | 0.34967→0.34973 |
| single-session | Mistral-7B-Instruct-v0.3 | query-full | 1350 | 483 | 39/4 | 0/0 | 0.00570 | 0.32648→0.32671 |
| single-session | Mistral-7B-Instruct-v0.3 | query-prefix | 1350 | 483 | 40/2 | 0/0 | 0.00570 | 0.32648→0.32672 |
| single-session | Qwen3-8B | query-full | 1350 | 852 | 41/33 | 1/0 | 0.01587 | 0.32840→0.33027 |
| single-session | Qwen3-8B | query-prefix | 1350 | 849 | 42/33 | 2/0 | 0.01587 | 0.32840→0.33072 |
| template-fanout | Llama-3.1-8B-Instruct | query-prefix | 2700 | 1374 | 62/49 | 2/1 | 0.07260 | 0.35862→0.35869 |
| template-fanout | Mistral-7B-Instruct-v0.3 | query-prefix | 2700 | 1374 | 45/14 | 6/1 | 0.07619 | 0.29663→0.29652 |
| template-fanout | Qwen3-8B | query-prefix | 2700 | 2232 | 45/0 | 0/0 | 0.00000 | 0.34541→0.34541 |

本次新样本仍有 2/8,595 个已编译配对超过 0.03 的任务分数下降。修复没有闭合全体行为风险，失败案例与来源簇必须继续保留。

总体超过阈值的下降为 18/16,200；raw 路由上的事件也计入总体。分组案例与 raw 重复对照用于判断波动，不能仅因走 raw 就删除或直接免除因果责任。

对于已编译退化，诊断还核对未来输出是否与当初 raw 见证逐 token 一致。如果一致，说明证据可能只覆盖了当时的输出路径，不能据此证明不同私有元数据或批形状下的未来 raw 输出也相同。独立重复是否稳定、metadata 变化是否起作用，必须由相同输入的控制判定；单条退化不被直接归结为实现错误，也不被直接免除为数值噪声。

| 场景 | 模型 | 重复 | session/turn | 分数raw→编译 | 首次分歧token | 与见证token一致 | raw重复数 [分数范围] |
|---|---|---|---|---|---|---|---|
| template-fanout | Llama-3.1-8B-Instruct | 3 | r1r-heldout_sealed-3c2e1be3687e6af0-tenant00/t4 | 0.21053→0.13793 | 12 | False | 3 [0.21053, 0.21053] |
| template-fanout | Mistral-7B-Instruct-v0.3 | 1 | r1r-heldout_sealed-4dbe35777b43b963-tenant08/t9 | 0.14286→0.06667 | 22 | True | 3 [0.06667, 0.14286] |

相同冻结输入的 raw 重复若存在较大分数变化，只说明对照本身也有波动；原配对退化仍计入分母和失败数。重复请求、tenant 和来源之间的相关性不被转换成独立失败概率。完整输出文字与来源位于 material_drop_cases_v1.csv。

其中 1 个编译退化案例的三次 raw 分数和 token IDs 都稳定，不能用 raw 对照波动解释。不同重复的首次业务见证及获准级别也可能不同；逐案 CSV 保留 candidate_repeat_levels/scores，不能把这些重复假定为同一候选布局的三次控制。query 绑定仍未证明所声明 metadata 变化下的未来路径不变。后续需固定完整 prompt、GPU/批形状与 cold/read 状态，区分未来输入作用域、数值轨迹和实现问题；本次没有据此修改已观察到的 held-out 门禁。

| 场景 | 模型 | raw重复比较 | token分歧 | 分数绝对差>0.03 |
|---|---|---|---|---|
| single-session | Qwen3-8B | 1350 | 14 | 4 |
| single-session | Mistral-7B-Instruct-v0.3 | 1350 | 42 | 4 |
| single-session | Llama-3.1-8B-Instruct | 1350 | 32 | 8 |
| template-fanout | Qwen3-8B | 2700 | 34 | 0 |
| template-fanout | Mistral-7B-Instruct-v0.3 | 2700 | 49 | 10 |
| template-fanout | Llama-3.1-8B-Instruct | 2700 | 34 | 6 |

## 全成本与真实计时

单 session 与模板 fan-out 分开报告。fan-out 为十个模板、每模板十个 tenant session，并发仍为 2；这是闭环重放，不是 100 个同时活跃请求或开放环容量测量。完整 wall 包括 warm 业务、首次 raw、失败验证、准备和等待，不减去假想 tool slack。服务启动和独立预控制在各策略中同等排除。

readiness TTFT 从两请求 cohort 的上一 wave 完成屏障开始计时，包含其后的验证和派发等待；它没有测量各 tenant 在更早独立完成时即可就绪的延迟。完整 wall 保留了这些屏障等待。

| 场景 | 模型 | 策略 | wave-ready均值 ms raw→策略 | 降低% [来源簇95%CI] | 完整wall吞吐 req/s raw→策略 | 倍率 [三重复min,max] |
|---|---|---|---|---|---|---|
| single-session | Qwen3-8B | query-full | 1066.8→1373.8 | -28.77 [-40.09, -17.30] | 0.814→0.742 | 0.911 [0.908, 0.917] |
| single-session | Qwen3-8B | query-prefix | 1066.8→1056.6 | 0.96 [-11.91, 13.72] | 0.814→0.842 | 1.034 [1.031, 1.039] |
| single-session | Mistral-7B-Instruct-v0.3 | query-full | 1176.7→1377.4 | -17.06 [-25.79, -9.56] | 0.541→0.519 | 0.959 [0.957, 0.960] |
| single-session | Mistral-7B-Instruct-v0.3 | query-prefix | 1176.7→1200.1 | -1.99 [-8.52, 4.16] | 0.541→0.542 | 1.002 [0.998, 1.005] |
| single-session | Llama-3.1-8B-Instruct | query-full | 1040.5→1143.6 | -9.91 [-17.19, -2.99] | 0.571→0.554 | 0.970 [0.966, 0.972] |
| single-session | Llama-3.1-8B-Instruct | query-prefix | 1040.5→1055.4 | -1.43 [-8.28, 5.30] | 0.571→0.569 | 0.997 [0.992, 1.002] |
| template-fanout | Qwen3-8B | query-prefix | 1044.4→319.3 | 69.43 [47.91, 84.63] | 1.140→2.407 | 2.111 [2.109, 2.115] |
| template-fanout | Mistral-7B-Instruct-v0.3 | query-prefix | 1158.7→847.8 | 26.83 [11.09, 48.00] | 0.763→0.905 | 1.185 [1.180, 1.189] |
| template-fanout | Llama-3.1-8B-Instruct | query-prefix | 1013.6→740.1 | 26.98 [10.80, 47.94] | 0.962→1.149 | 1.195 [1.188, 1.199] |

置信区间对配对重复及来源模板重采样，tenant 和未来轮次保留在来源簇内；模型为固定模型，不能解释成模型总体预测区间。完整 wall 不被虚构拆成独立的每来源 wall，因此吞吐另报三次真实重复的范围。

| 场景 | 模型 | 策略 | 冻结GPU lane | raw/策略重复数 | 同lane吞吐倍率 |
|---|---|---|---|---|---|
| single-session | Llama-3.1-8B-Instruct | query-full | 0 | 3/1 | 0.971 |
| single-session | Llama-3.1-8B-Instruct | query-prefix | 0 | 3/1 | 0.995 |
| single-session | Mistral-7B-Instruct-v0.3 | query-full | 1 | 3/1 | 0.960 |
| single-session | Mistral-7B-Instruct-v0.3 | query-prefix | 1 | 3/1 | 0.993 |
| single-session | Qwen3-8B | query-full | 0 | 3/1 | 0.915 |
| single-session | Qwen3-8B | query-prefix | 0 | 3/1 | 1.033 |
| template-fanout | Llama-3.1-8B-Instruct | query-prefix | 0 | 2/1 | 1.188 |
| template-fanout | Llama-3.1-8B-Instruct | query-prefix | 1 | 1/2 | 1.203 |
| template-fanout | Mistral-7B-Instruct-v0.3 | query-prefix | 0 | 1/2 | 1.182 |
| template-fanout | Mistral-7B-Instruct-v0.3 | query-prefix | 1 | 2/1 | 1.185 |
| template-fanout | Qwen3-8B | query-prefix | 0 | 2/1 | 2.097 |
| template-fanout | Qwen3-8B | query-prefix | 1 | 1/2 | 2.127 |

GPU lane 根据实际执行的冻结 launcher 任务序号恢复，并由每单元硬件快照提供运行背景；它不是另一套独立 device profiler。部分主配对跨两张3090，同lane表额外核对小幅收益是否可能来自硬件分配。每组重复数量较少且不等，不替代主估计，也不被包装成新的随机试验。

| 场景 | 模型 | 策略 | wave-ready p99 ms raw→策略 | 后端请求 p99 ms raw→策略 |
|---|---|---|---|---|
| single-session | Qwen3-8B | query-full | 2077.0→6979.1 | 2067.2→1941.6 |
| single-session | Qwen3-8B | query-prefix | 2077.0→6161.3 | 2067.2→1944.1 |
| single-session | Mistral-7B-Instruct-v0.3 | query-full | 2741.2→5435.0 | 2729.6→2718.1 |
| single-session | Mistral-7B-Instruct-v0.3 | query-prefix | 2741.2→4518.7 | 2729.6→2713.5 |
| single-session | Llama-3.1-8B-Instruct | query-full | 2015.9→3910.6 | 2001.5→2019.0 |
| single-session | Llama-3.1-8B-Instruct | query-prefix | 2015.9→3403.6 | 2001.5→2019.1 |
| template-fanout | Qwen3-8B | query-prefix | 1894.3→2901.2 | 1883.0→1884.7 |
| template-fanout | Mistral-7B-Instruct-v0.3 | query-prefix | 2329.5→2352.1 | 2316.4→2310.2 |
| template-fanout | Llama-3.1-8B-Instruct | query-prefix | 1814.3→1893.3 | 1804.0→1804.5 |

p99 是合并三次独立进程重复后的观测分位数，不是独立请求假设下的总体置信区间。后端 TTFT 与包含验证等待的 wave-ready TTFT 各自保留，避免用更快的后端响应掩盖注册造成的尾部等待。

| 场景 | 模型 | 策略 | 验证总秒数 | 验证ms/未来请求 | 实际读取已批准前缀token |
|---|---|---|---|---|---|
| single-session | Qwen3-8B | query-full | 868.33 | 643.21 | 0 |
| single-session | Qwen3-8B | query-prefix | 520.11 | 385.27 | 698144 |
| single-session | Mistral-7B-Instruct-v0.3 | query-full | 461.09 | 341.55 | 0 |
| single-session | Mistral-7B-Instruct-v0.3 | query-prefix | 276.19 | 204.59 | 401968 |
| single-session | Llama-3.1-8B-Instruct | query-full | 333.95 | 247.37 | 0 |
| single-session | Llama-3.1-8B-Instruct | query-prefix | 223.82 | 165.79 | 232560 |
| template-fanout | Qwen3-8B | query-prefix | 61.86 | 22.91 | 125568 |
| template-fanout | Mistral-7B-Instruct-v0.3 | query-prefix | 47.48 | 17.58 | 115968 |
| template-fanout | Llama-3.1-8B-Instruct | query-prefix | 31.24 | 11.57 | 60336 |

这是包含失败尝试的策略级总验证成本，按每个注册调用的完整耗时求和；并行调用可能重叠，不能再把它直接加到已经实测的 TTFT 或完整 wall 上。不同策略可能选择不同级别，故该表不被解释成同一 witness 的逐调用纯算子加速。独立冷读/前缀读控制检查判定一致性、错误 namespace/policy 和零拒绝发布。

| 场景 | 模型 | 策略 | 后端TTFT均值ms | 首token后响应均值ms | 输出token均值 | 其他注册准备ms/作用域 |
|---|---|---|---|---|---|---|
| single-session | Llama-3.1-8B-Instruct | query-full | 808.1 | 1479.7 | 62.66 | 51.0 |
| single-session | Llama-3.1-8B-Instruct | query-prefix | 820.8 | 1469.2 | 62.72 | 50.7 |
| single-session | Llama-3.1-8B-Instruct | raw-order | 1020.8 | 1480.4 | 62.65 | 0.0 |
| single-session | Mistral-7B-Instruct-v0.3 | query-full | 910.3 | 1466.6 | 62.29 | 59.2 |
| single-session | Mistral-7B-Instruct-v0.3 | query-prefix | 902.1 | 1476.4 | 62.35 | 58.7 |
| single-session | Mistral-7B-Instruct-v0.3 | raw-order | 1166.2 | 1512.2 | 62.25 | 0.0 |
| single-session | Qwen3-8B | query-full | 503.8 | 719.8 | 29.82 | 75.2 |
| single-session | Qwen3-8B | query-prefix | 506.4 | 714.3 | 29.90 | 75.3 |
| single-session | Qwen3-8B | raw-order | 1057.0 | 782.1 | 30.36 | 0.0 |
| template-fanout | Llama-3.1-8B-Instruct | query-prefix | 706.8 | 792.4 | 31.83 | 41.9 |
| template-fanout | Llama-3.1-8B-Instruct | raw-order | 1003.4 | 822.2 | 31.83 | 0.0 |
| template-fanout | Mistral-7B-Instruct-v0.3 | query-prefix | 801.8 | 1148.5 | 47.50 | 55.3 |
| template-fanout | Mistral-7B-Instruct-v0.3 | raw-order | 1148.2 | 1206.0 | 47.34 | 0.0 |
| template-fanout | Qwen3-8B | query-prefix | 263.2 | 395.5 | 17.25 | 52.9 |
| template-fanout | Qwen3-8B | raw-order | 1033.9 | 513.2 | 17.25 | 0.0 |

首 token 后响应时间仍含客户端/传输和结束处理，不能当成纯 GPU decode kernel 时间；其他注册准备是完整注册与逐次 verifier HTTP 时长之差，含渲染、tokenize 与控制开销。这些观测用来分析瓶颈，不被加回已经计入全部成本的 wall。输出长度同时列出，以免把生成长度变化的收益全部归因于 cache。

真实任务还配对审计了 990 个 query 注册，其中 982 个具有相同 raw 参考 token 序列。相同参考下仍有 8 个同级判定变化；其中 4 个实际前缀读取为 0，4 个发生了读取。因此不能把全部变化归因于前缀读取，也不能把该优化称为逐位判定不变。缓存/重算及批形状造成的 FP16 排名差异是待检验解释，尚需固定输入的重复 cold/read 重放定位；本次没有据此调改 held-out 门禁。

## 实际长输出与终止边界

先按实际见证长度核对未来输出。以下 token 数采用接口实际返回的 IDs（包含已返回的 terminal stop），不是预算值。超过参考序列长度的位置单独计数；即便长度仍在范围内，一旦 token 路径分歧，后续也不能由原 teacher-forced 历史直接推导。

| 批次/场景 | 模型 | 策略/预算条件 | 编译未来请求 | 见证长度范围 | 未来最长 | 超过见证长度的输出/位置 | 可比较见证序列 |
|---|---|---|---|---|---|---|---|
| R1/free-generation | Llama-3.1-8B-Instruct | contractkv/b0 | 567 | 2–55 | 96 | 27/558 | 0 |
| R1/free-generation | Llama-3.1-8B-Instruct | contractkv/b512 | 567 | 2–55 | 96 | 27/558 | 0 |
| R1/free-generation | Mistral-7B-Instruct-v0.3 | contractkv/b0 | 378 | 3–20 | 31 | 18/189 | 0 |
| R1/free-generation | Mistral-7B-Instruct-v0.3 | contractkv/b512 | 378 | 3–20 | 31 | 18/189 | 0 |
| R1/free-generation | Qwen3-8B | contractkv/b0 | 891 | 7–80 | 80 | 63/441 | 0 |
| R1/free-generation | Qwen3-8B | contractkv/b512 | 891 | 7–80 | 80 | 63/441 | 0 |
| R1R/single-session | Llama-3.1-8B-Instruct | query-full/native | 474 | 2–30 | 42 | 6/126 | 474 |
| R1R/single-session | Llama-3.1-8B-Instruct | query-prefix/native | 474 | 2–30 | 42 | 6/126 | 474 |
| R1R/single-session | Mistral-7B-Instruct-v0.3 | query-full/native | 483 | 3–74 | 74 | 0/0 | 483 |
| R1R/single-session | Mistral-7B-Instruct-v0.3 | query-prefix/native | 483 | 3–74 | 74 | 0/0 | 483 |
| R1R/single-session | Qwen3-8B | query-full/native | 852 | 7–66 | 66 | 10/22 | 852 |
| R1R/single-session | Qwen3-8B | query-prefix/native | 849 | 7–66 | 66 | 13/35 | 849 |
| R1R/template-fanout | Llama-3.1-8B-Instruct | query-prefix/native | 1374 | 3–28 | 36 | 1/12 | 1374 |
| R1R/template-fanout | Mistral-7B-Instruct-v0.3 | query-prefix/native | 1374 | 9–60 | 60 | 0/0 | 1374 |
| R1R/template-fanout | Qwen3-8B | query-prefix/native | 2232 | 7–33 | 33 | 0/0 | 2232 |

原 R1 主实验只保留参考长度/哈希，未保留参考序列的直接 IDs；表中这些序列不可比较，不补造相对见证的首次分歧位置。原 R1 未来 raw/compiled 配对的分歧仍由实际输出 IDs 计算。新 R1R 保留真实业务见证 IDs。详细每请求的长度、超出位置和相对见证的首次分歧见 output_horizon_pairs_v1.csv；这张编译路由表不替代包含 raw/fallback 的总体质量和成本分母。

原 R1 的 512 上限条件中，获准输出实际上均未超过 96 token，因此它不构成 512-token 正向行为证据。下面的独立受控任务要求输出完整整数数组，用 1536 上限允许自然 EOS 的较长输出；只按实际长度与结束状态计数。它不替代五任务族的正式任务评分或性能数据。

| 模型 | 上限 | 参考 length stop | 获准参考 | 编译未来对 | 实际>512 | 编译最长token | 超过见证长度 输出/位置 | 分歧 | 正确数组 raw→策略 |
|---|---|---|---|---|---|---|---|---|---|
| llama31-8b | 256 | 3 | 0 | 0 | 0 | 0 | 0/0 | 0 | 0→0 |
| llama31-8b | 512 | 3 | 0 | 0 | 0 | 0 | 0/0 | 0 | 0→0 |
| llama31-8b | 1536 | 0 | 0 | 0 | 0 | 0 | 0/0 | 0 | 0→0 |
| mistral7b | 256 | 3 | 0 | 0 | 0 | 0 | 0/0 | 0 | 0→0 |
| mistral7b | 512 | 3 | 0 | 0 | 0 | 0 | 0/0 | 0 | 0→0 |
| mistral7b | 1536 | 0 | 3 | 6 | 6 | 769 | 0/0 | 6 | 0→6 |
| qwen3-8b | 256 | 3 | 0 | 0 | 0 | 0 | 0/0 | 0 | 0→0 |
| qwen3-8b | 512 | 3 | 0 | 0 | 0 | 0 | 0/0 | 0 | 0→0 |
| qwen3-8b | 1536 | 0 | 3 | 6 | 6 | 646 | 0/0 | 0 | 6→6 |

所有 length-stop 参考的发布门禁与实际未来输出均在长输出 completion audit 中核验；预算增大本身不被当成完成更长输出。

以下为观测后增加的格式诊断，用来区分 JSON 解析、元素类型和数值序列问题；冻结的数组主评分保持原样。JSON 谓词与 token/EOS 认证门禁独立，格式错误与认证拒绝同时出现，并不证明前者导致后者。详细前缀和类型信息见 posthoc_schema_diagnostics_v1.csv。

| 模型 | 输出角色 | 实际编译路由 | 诊断类别 | 生成次数 |
|---|---|---|---|---|
| llama31-8b | policy | 否 | json_parse_error | 6 |
| llama31-8b | raw | 否 | json_parse_error | 6 |
| llama31-8b | reference | 否 | json_parse_error | 3 |
| mistral7b | raw | 否 | element_type_mismatch | 6 |

## 原七项要求的证据对应

| 要求 | 已获得证据 | 主要解释边界 |
|---|---|---|
| 非 RULER 共同跨模型 | 原 R1 三模型共同 HotpotQA：2430 配对；输入和固定 L2 完全相同 | prefill 降低 38.38–48.05%；完整成本零 slack 宏均值 5.24%，CI [-2.16,12.56]%，不能称普遍冷会话获益 |
| 认证后自由生成 | 原 R1 保留 changed-query 反例；新增 query-bound 实际 token/分数/回退/重复对照 | 新结果不回写原 R1，也不外推任意工具语义 |
| 较长输出 | 原预算和 512 条件保留；新增独立真实长输出任务 | 受控长输出与正式 benchmark 质量分别报告 |
| 完整成本与零 slack | 四配置历史审计、真实零 slack D0/D1/D2、14B TP2 补测、新修复完整 wall | 缺失的历史参考时钟仍标不可得；闭环与开放环结果分开 |
| D1/D2 安全消融 | 两组20-case guard；10/10真正坏布局被拒绝，拒绝发布0；补测实际后决策输出保持raw分数 | D1是性能参考；D2的新增价值是行为准入和发布约束 |
| manifest与隔离 | 9例独立CPU声明/签名/所有权组件检查；另有live namespace/policy控制 | CPU helper未接入live endpoint；可信operator误标私有内容不能由哈希发现；无时延侧信道防御 |
| CacheBlend、统计、输入 | 9000 native-matched 对照重算；阈值敏感性；4695 segment 位移；来源簇CI | 不作2.18%跨运行栈性能优势或112x因果安全排名 |

## 决策、限制与后续可证伪检查

原 R1 的新 query 反例支持收紧证书作用域，真实业务输出复用及 approved-prefix read 则针对完整成本来源。新正式矩阵保留冷会话与模板场景，使收益不足的场景不会被平均或摊销口径隐藏。

如果短 session 的完整 wall 仍不改善，一个待检验解释是新 query 数量、首用 raw 和级别下降成本超过该 session 内可节省的 prefill；本报告没有把它当成已证实的唯一原因。下一项检查应在新的开发输入上分解首次 witness、失败尝试、decode 和控制器等待，并在新冻结数据上检验收益门禁。

raw 路由的质量差异可能与 FP16、批形状或调度轨迹有关；必须结合相同输入与重复运行验证，不能仅靠路径名称归因。继承验证器检查每个答案/EOS 的 rank-one membership；并列最大分数和 teacher-forced/decode 的有限精度差异不构成唯一 argmax 或逐请求数学保证。

修复 trace 保存了冻结来源、session/轮次、query scope、实际输出 token IDs 和服务端 prompt 计数，但没有逐次另存完整 prompt token IDs 或其哈希。因此相同输入对照的身份依据是冻结样本、确定性 renderer 及模型/配置清单，而不是每条请求已留存的 prompt-token 哈希；后续更严格的数值机制定位应补齐这层记录。

安全边界仍依赖正确的 operator 声明。授权和哈希不是机密性分类器，也不消除共享前缀时延推断；CPU 状态机压力操作不计为 GPU 服务请求。

原 R1 报告：`docs/tsc_major_revision_r1_results.md`。复现和计时边界：`docs/tsc_revision_r1r_reproduce.md`。原始数据、逐请求 CSV、运行快照及逐文件哈希保存在本实验 artifact。GitHub 的最终提交和清理审计由交付记录核验，报告生成本身不声称上传或投稿完成。

## 已知失败的定向诊断

这四个模型/来源单位根据原 R1 已观察到的失败选取，不计入新 held-out 成功率。每模型一个新进程，三种策略共享同一新 backend，固定顺序 raw→旧范围逻辑→新 query-prefix；共九个策略单元、108 次未来生成。旧范围客户端是受控适配，不是原运行栈或批形状的完整复现；这里不比较性能。

| 模型 | 来源 | 策略 | 配对 | 编译 | token分歧 | 下降>0.03 总体/编译 | 均分 raw→策略 |
|---|---|---|---|---|---|---|---|
| llama | LongBench:narrativeqa:narrativeqa:doc:126 | legacy-unbound | 9 | 9 | 3 | 3/3 | 0.03333→0.01852 |
| llama | LongBench:narrativeqa:narrativeqa:doc:126 | query-prefix | 9 | 5 | 0 | 0/0 | 0.03333→0.03333 |
| mistral | LongBench:narrativeqa:narrativeqa:doc:85 | legacy-unbound | 9 | 9 | 3 | 3/3 | 0.21402→0.20259 |
| mistral | LongBench:narrativeqa:narrativeqa:doc:85 | query-prefix | 9 | 5 | 0 | 0/0 | 0.21402→0.21402 |
| qwen | LongBench:qasper:qasper:doc:189 | legacy-unbound | 9 | 9 | 6 | 6/6 | 0.42963→0.40000 |
| qwen | RepoBench:python_v1.1:Gryphe/MergeMonster | legacy-unbound | 9 | 9 | 6 | 6/6 | 0.21000→0.14333 |
| qwen | LongBench:qasper:qasper:doc:189 | query-prefix | 9 | 7 | 0 | 0/0 | 0.42963→0.42963 |
| qwen | RepoBench:python_v1.1:Gryphe/MergeMonster | query-prefix | 9 | 7 | 0 | 0/0 | 0.21000→0.21000 |

只有旧范围控制在此条件下确实再次退化、新路由保护了相同输入，才支持该反例的修复解释；若旧控制没有退化，应记录为未重现。新路由同时包含 query 绑定与允许级别下降，不能只凭这个组合对照把收益唯一归因于其中一项。原 R1 的全部失败记录继续保留。
