# ContractKV 跨模型机制与 Manifest：完成结果

2026-10-18。原9个冻结单元全部完成；新分析、原始归档和本地独立复算通过。本文件关闭五批目标中的原第二、三批，不代表整个目标完成。256-token、真实RepoBench小补充及任务保真固定到达/门禁消融另列。

## 方法与实际规模

三个模型各3个fresh-server进程，每进程20个受控候选，覆盖指令顺序、RAG证据位置、tool状态、合成代码赋值与EOS/stop。每候选都实际执行Raw见证、Raw重复、私有命名空间的未经认证候选及认证后的真实路由，保存完整实际Prompt/Output IDs、分数、逐token/EOS证据和native发布/命中。

正式共180次候选评估、720次行为生成。Manifest另有135次业务生成，包括27次拒绝注册后的Raw、18次见证/重复和72次后续控制请求。合计855次正式业务生成、198次资格决定、180次真实认证RPC。RPC不等于GPU kernel数。

失败的Llama旧attempt另有63次真实业务和13次RPC，全部原文及成本保留，未加进正式完整单元的统计分母。因此本批实际观察918次业务生成；没有丢掉失败尝试。

输入是小规模受控机制挑战，行为预算64 tokens、Manifest预算32。两个变体及三次进程重复不等于独立生产来源。两个布局均满足**提供的**DAG；没有编码的顺序语义由本实验刻意留作行为认证挑战，不能据此声称CALC会自动推断缺失依赖。

## 真实行为决定的分母

| 模型 | 候选评估 | 实际ID/终止变化 | 其中任务掉分 | 变化候选拒绝 | 未变化候选放行 | 获准后实际ID/终止变化 | 拒绝新增发布tokens |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Qwen3-8B | 60 | 24 | 18 | 24/24 | 36/36 | 0/36 | 0 |
| Mistral-7B | 60 | 30 | 0 | 30/30 | 30/30 | 0/30 | 0 |
| Llama-3.1-8B | 60 | 48 | 12 | 48/48 | 12/12 | 0/12 | 0 |
| 合计 | 180 | 102 | 30 | 102/102 | 78/78 | 0/78 | 0 |

所有180条Raw重复均与该次见证IDs一致。全路由未观察ID/终止或任务分数变化；没有不确定认证响应。按实际观测定义变化与掉分，没有把事前标成order-risk的病例自动算作有害。

未认证候选同时存在分数上升：Mistral 15次、Llama 6次。它们仍可能属于行为变化而被拒绝，说明认证不是通过挑选更高分的重排来改良模型答案。原exact-normalized评分不改；Raw正分候选评估为Qwen48/60、Mistral18/60、Llama24/60，行为保持不等于绝对任务正确。

这支持受控范围内的机制结论：结构合法性不足以授权共享；行为检查能拦截这里实际观察到的变化，再由PSTP限制新增状态发布。不能据有限20例声称普遍零风险。合成code_context不是RepoBench next-line completion，不能替代计划中的72次真实RepoBench诊断。

## 完整诊断费用

| 模型 | 行为资格RPC | 全资格controller均值ms/候选 | Raw见证生成均值ms | 后决策生成均值ms |
| --- | ---: | ---: | ---: | ---: |
| Qwen3-8B | 60 | 323.651 | 386.837 | 226.698 |
| Mistral-7B | 51 | 256.712 | 601.948 | 457.682 |
| Llama-3.1-8B | 51 | 204.195 | 617.491 | 524.404 |

表中RPC合计162；Manifest另18，合计180。未发RPC的资格决定也计controller费用。这里使用同步native审计hook、串行诊断请求和短输入；费用是诊断口径，不能把这些均值相除当成服务吞吐加速，也不叫纯GPU核函数时间。

## Manifest与发布闭环

注册helper及既有HMAC/Scope函数确实在可信内部client中运行，再调用真实推理与PSTP。不是公共IAM网关。

| 控制 | 真实请求数 | 实际路由与状态 |
| --- | ---: | --- |
| 显式PRIVATE共享、MUTABLE共享、非operator注册 | 27 | 27次拒绝、0认证RPC、0对应候选共享提交；真实Raw回退保留 |
| 相同值、相同授权域 | 18 | 18次compiled；18/18完整命中已提交前缀，native block-hash链与发布一致 |
| 不同私有observation、相同域 | 18 | 全部Raw；18次精确observation scope不匹配，其中9次还发生稳定字节身份不匹配 |
| 相同值、不同授权域 | 18 | 18次binding拒绝compiled；Raw仍有18次原生APC命中覆盖合成私有标记 |
| 旧epoch | 18 | 18次binding拒绝compiled；Raw仍有18次原生APC命中覆盖合成私有标记 |

正确声明的9个条件实际发布前缀均不含合成私有标记。可信operator将该标记误声明为stable/shared时，9/9条件真实发布了含标记的前缀；后续授权域内命中也成立。正确哈希、HMAC和行为ACK认证都不负责判断文本公开性。

Raw路径保持原`cache_salt=None`，所以拒绝compiled不等于Raw无缓存、不等于跨域全引擎状态隔离。以上是合成字节的实际缓存可见性证据，不是已实施的外泄攻击、时间信道攻击或防御。完整边界见[Trust矩阵](ContractKV_Trust_Model_and_Enforcement_Boundary_Matrix.md)。

## 修复与失败保留

1. 原固定端口复用失败发生在下一wave模型启动前，0业务；只换独立端口，已完成单元保留。
2. Llama旧attempt的64-token Raw见证不完整，原splitter抛VerificationIncomplete但registrar没有捕获该异常。v5窄修复返回INCOMPLETE、L0、0RPC/0提交；15条既有完整见证CPU回归决策不变。仅未完成的cell按原实验单位完整重测，已完成3个不重测。
3. effects_v4的CPU分析把三个Manifest注册namespace压成同一个字典键；v5只为行为表索引原20病例，完整保留720/135分母。原analysis_v3不重跑，GPU不重跑。
4. 本地复算最初缺实际tokenizer资产，检查在分析前停止；另建14个已登记tokenizer资产的字节校验视图，保留历史CPU snapshot不动，没有复制/下载模型权重或重新计算权重SHA。

## 可复核交付

- 原始压缩归档SHA256：`39b2ad426f101602bed6706d1d5866665355cde3c8f3b84915c90eca1a7a3c1f`。
- 归档6,059,658 bytes、254个普通文件；33,976,097未压缩bytes。含全部成功/失败、实际IDs、native链、源码postimages和CPU故障记录，排除权重、二进制runtime、编译缓存及凭据。
- 双端逐成员校验通过。本地从归档重新分析，analysis_v3全部summary字段及四份CSV逐字节一致；effects_v5的233个叶值完全相同，0个浮点容差差异。
- 实际GPU入口仍是continuation_v5；分析为analysis_v3 + effects_v5，归档入口package_v6。不要启动旧worker或重跑已完成矩阵。

证据目录：`results/tsc_revision_mechanism_controls_20261018/`，尤其`analysis_v3/`、`effects_v5/`、`local_independent_recompute_v1.json`及归档manifest。源与原始分片按本轮Git归档记录核实发布。
