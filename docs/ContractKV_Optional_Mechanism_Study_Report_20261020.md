# ContractKV：审稿实证收口后的可选机制研究总记录

日期：2026-10-20。定位：**开发机制诊断与附录候选**，不是新的审稿必做矩阵，不增加第五项论文贡献。

## 结论与处置

审稿人明确要求的实验证据已逐项核查，未发现尚需执行的 GPU 单元；本轮先完成该核查，再启动以下探索。

探索得到了一个实质性的机制结果：**在不增加 pool 或人为增加引用计数的条件下，获准编译请求的完整前缀命中从 50% 恢复到 100%。** 融合认证也能从实际 Candidate Decode/EOS 获取证据，并保持原 margin/PSTP 条件。

完整成本结果比较温和：Qwen 的融合+驻留路径为 **1.078×**，Mistral 为 **0.970×**；Mistral 的普通 Raw+相同驻留策略反而达到 **1.289×**。因此，本轮不支持把新原型作为统一默认优化，也不足以替换正文性能主结果。**按用户指定定位保留为附录候选及实验记录，预定矩阵结束后停止，不追加正式来源验证或新布局搜索。**

## 1. 先完成审稿人要求的核查

详见 `ContractKV_Reviewer_Priority_Audit_20261020.md` 与对应机器回执。

- 非 RULER 共同范围跨模型：原 18 份 HotpotQA 请求文件重新核 SHA 和 2,430 配对，原共同来源 bootstrap 三个 slack 条件重放一致。
- 原 RULER CI：30 来源、三模型的点估计与原区间复现，保留来源相关性的同步敏感性区间已经完成；不作未见模型预测。
- 自由生成、实际 512+、D1/D2 拒绝、Manifest、隔离、输入位移与五家族 raw 顺序：均已有实际结果和原始归档；各自有限范围与失败仍保留。
- 原 Table III 全费用：24 cells、4,725 future pairs、525 完整 controller 的同 cohort 补计时已经完成；负收益不删除。
- 时间通道：审稿人允许“实验或明确限制”，当前采用明确限制，没有声称实现防御。

本次发现并拆开了旧证据地图的 CI 混淆：HotpotQA 的零 slack **5.242% [−2.162,12.564]%** 不能用于解释原 RULER 的 **86.672%** 宏平均 CI。

剩余的引用 venue 核对、正文表格与边界嵌入、artifact 版本对应、PDF 版式及 Response Letter 定位属于后续写作交付。本轮没有把这些事项误列为“缺少 GPU 实验”，也没有宣布论文已可直接提交。

## 2. 探索协议与实际完成量

六臂：Raw、当前 Strict、TF-only、Fused、Fused+Residency、Raw+Residency；Qwen3-8B 与 Mistral-7B-Instruct-v0.3 各一 fresh process/臂，共 **12 cells、384 主业务**。

复用此前已经打开的 doc80/doc122/doc61 与 SkunkworksAI/BakLLaVA，**本轮将这些来源作为已知开发诊断来源，绝不再称为独立 held-out**。三个 QA×两 tenant 条件×两模型形成 12 个 QA scope 条件；Repo 仍继承 L0。每个条件访问四次，固定轮转；不是原八次访问实验的重跑，不能与旧 1.027×/0.987× 直接相除。

共同条件：16K 保真输入、QA128/Repo384、greedy/seed14014、模型/分词器身份、授权域及 exact scope；物理 pool 固定 Qwen1940/Mistral3550 blocks。主业务串行闭环；`max_num_seqs=2` 是引擎上限，不是本实验两个客户端并发，更不是生产开放到达容量。

本轮Strict是复用相同Token/EOS门槛、exact ledger与PSTP的受控基线。认证臂对预定重复条件尝试资格，不执行原完整收益门禁的预测筛除；这用于隔离执行/驻留机制，不能标为原收益门禁全系统或开放到达协议的性能复现。

首次 Raw、全部准备、成功/失败资格、日志及最终排空均计入直接 wall；加载模型在服务计时之外。384 主业务和10个私有 Candidate 生成全部自然停止，没有靠提高预算或删除 length 样本取得结果。

冻结主协议后，在任何 GPU 推理之前以 v2 增加 native release 与取消/重复控制；v1 冻结与 CPU 预检保留、GPU 请求为0。实际执行冻结 SHA256：

`02c19f6592f44733f39a8bbececa2e81a2d3de567cfb94de78a89d5ac5c0a2b2`

执行前公开提交：`31423c5344408408f7ab66fa94e296d2b353f873`。运行时只改隔离副本的5个源文件；共享 runtime 完成后重核仍一致，新 runtime revision 单独绑定。

## 3. 完整 wall 结果：全部六臂保留

每模型/臂32个主业务，相对倍率为同模型 Raw wall÷本臂 wall。

| 路径 | Qwen wall(s) | Qwen 倍率 | Mistral wall(s) | Mistral 倍率 |
|---|---:|---:|---:|---:|
| Raw | 105.610 | 1.000× | 130.442 | 1.000× |
| Strict | 116.068 | 0.910× | 137.802 | 0.947× |
| TF-only | 109.378 | 0.966× | 139.073 | 0.938× |
| Fused | 103.247 | 1.023× | 138.974 | 0.939× |
| Fused+Residency | 97.967 | **1.078×** | 134.417 | **0.970×** |
| Raw+Residency | 106.327 | 0.993× | 101.186 | **1.289×** |

Qwen 新路径相对本轮 Strict 提高约18.5%吞吐，且相对本轮 Raw+Residency 仍略好。Mistral 仍未回本，普通 Raw 优先保留更好，不能把所有驻留收益称为 ContractKV 独有。

这些是同输入开发对照的点值。一进程/臂、固定执行次序和已打开来源，不支持普遍显著性、生产收益或新的 SLO 容量结论。本轮不构造 CI。

实际全部主请求新增 Prefill（包含私有候选和认证）如下，不能换算成 GPU 秒数：

| 路径 | Qwen 新Prefill tokens | Mistral 新Prefill tokens |
|---|---:|---:|
| Raw | 277,128 | 319,080 |
| Strict | 276,730 | 325,054 |
| TF-only | 260,964 | 330,360 |
| Fused | 246,346 | 330,046 |
| Fused+Residency | 214,040 | 312,190 |
| Raw+Residency | 277,128 | 199,128 |

## 4. 容量与驱逐：从推测到实际 hash 证据

| 模型 | 实际pool | 获准稳定工作集 | 最大已观察Raw完整块需求 | 全稳定工作集+该Raw的容量下界 |
|---|---:|---:|---:|---:|
| Qwen | 1,940 | 972（doc80:631，doc61:341） | 903 | 1,875 |
| Mistral | 3,550 | 372（doc61） | 1,005 | 1,377 |

容量下界来自旧原始 Prompt/Output IDs，扣除可见公共前缀的重复计数，只是容量几何，不是预测速度或足以保证驻留的上界。它说明稳定集合本身放得下，其他缓存状态和回收顺序值得检查。

本次完整记录真实 free-queue 分配前被回收的 block hash，结合后续实际 native lookup：Strict 的 **6/6 Qwen、3/3 Mistral 零命中**均能找到此前已温热前缀头块被回收的序列。TF-only 和 Fused 的对应零命中也均如此。与回收关联的调用包括后续 Raw QA 业务；不是证书没被索引或从未发布的推断。

重复 hash 可以有多个物理副本，一次 miss 前也可能有多次回收事件；不能把这些事件数当独立来源。确切序列见 `residency_forensics_v1.json`。

| 路径 | Qwen完整命中/compiled | Mistral完整命中/compiled |
|---|---:|---:|
| Strict | 6/12 | 3/6 |
| TF-only | 6/12 | 3/6 |
| Fused | 6/12 | 3/6 |
| Fused+Residency | **12/12** | **6/6** |

可撤销优先级预算为 pool 可用块的75%，TTL120s，分组FIFO；不增加引用计数，不隐藏容量，不创建永不结束的请求或预取。

- Qwen 认证优先保留峰值972块，普通Raw策略峰值1272块；后者在分配压力下实际回收了711次优先块事件，证明本原型确实允许撤回优先级。
- Mistral 认证峰值372块，普通Raw峰值2504块；普通Raw的保留对象在本池/轮转中能取得很大收益。
- 此 Raw 控制是明确的有界普通替换策略，不是所有通用缓存策略的最优 oracle；不能据它建立普遍算法排名。

## 5. 融合省了什么，为什么Mistral仍亏

Fused 将一次真实 Candidate 自由生成和原 native Token/EOS margin/PSTP 检查合并：真实 decode 行在 KV 释放前收集，原检查读取这些观测行；不重新 teacher-force，不借 Raw IDs 伪造 Candidate。跨进程返回的实际 Candidate Prompt/Output IDs仍由 exact ledger 对比。TF-only另列，缺少资格建立时 Candidate 自由生成证据，不追认为同等证明协议。

12个已知 QA scope 的最终 PASS/拒绝集合在四个认证臂中一致；不同臂的 Raw margin 和拒绝阶段仍有变化。

| 累计完整Controller(s) | Qwen共同PASS | Qwen非PASS | Mistral共同PASS | Mistral非PASS |
|---|---:|---:|---:|---:|
| Strict | 12.198 | 7.732 | 5.820 | 3.763 |
| TF-only | 7.193 | 5.834 | 2.058 | 9.267 |
| Fused | 6.733 | 0.311 | 2.973 | 8.280 |
| Fused+Residency | 6.760 | 7.384 | 2.953 | 8.245 |

共同PASS的实测费用下降；同时存在两个不能忽略的因素：

1. **Raw门槛附近的变化。** Qwen doc122输出IDs相同，但最小margin在0.03125/0.0625之间变化。Fused跳过两个条件；Fused+Residency其中一个达到原门槛后执行并失败，多付约7秒。阈值保持0.0625，没有根据结果调整。不能把总Controller差额全部解释为融合本身。
2. **失败路径并非免费。** Mistral doc80的Raw合格但Candidate行为改变。Strict先用私有Candidate发现差异，不调用昂贵认证；私有namespace内的第二个Candidate可以复用11,408-token前缀。Fused把这些失败也放进 native事务路径；拒绝后不发布，不能依赖未获证共享KV温热后续失败请求。共同PASS省下的费用不足以覆盖这些失败工作。

这些是实测时钟和路径的描述性归因，不是独立GPU kernel计时。相同Prompt而margin不同的底层原因没有通过本轮逐kernel/批形状实验唯一定位；执行与数值轨迹差异是待检验假设，不用于删掉费用。

全部主费用闭合：**384业务HTTP + 10私有Candidate HTTP + 32实际认证HTTP = 426次主派发**，每次都有native初始观测。成功、失败和前置拒绝的完整Controller及其他路径均计入wall；HTTP不是GPU forward/kernel数量。

## 6. 行为、任务分数与事务控制

- Strict/Fused/Fused+Residency合计54个compiled配对，与隔离Raw及自己的实际Raw见证均无ID/EOS差异、无掉分。
- TF-only另有18个获准后自由生成配对，本样本也无ID/EOS差异；不据此证明它与融合协议等价或可普遍删除自由生成检查。
- 四臂72个compiled观察都以Raw正分样本为参考；正分不是答案完全正确，重复条件不等于72个独立来源。
- 全部非Raw臂共320个业务配对，11个ID/EOS变化均在L0：Mistral Strict 1、Qwen TF-only 4、Mistral Raw+Residency 6。保留8个微小分数变化；超过±0.03的升分/降分均为0。不能把它们删成“全路由输出完全一致”。

两个Fused单元结束主服务计时后，在同一未清缓存引擎执行独立辅助控制，共14次HTTP/取消发送与16次真实读取探针，另计完整费用：

| 控制 | 实际原生观察 |
|---|---|
| 错误answer / 错误EOS（每模型各1） | Candidate自然完成，但候选分配的636/379块中共享cached块为0；后续首次读取0命中 |
| timeout / cancel（每模型各1） | 每模型均观察到2个实际Native ABORT释放；timeout分配0块、cancel分配16块，cached均为0 |
| 拒绝/取消后的本组Raw重复 | 8个首次读取全部0命中；之后8个合法重复均命中，Qwen10,160 / Mistral6,032 tokens |
| 同时重复request ID | 两模型均观察到pending重复错误，原请求继续完成 |
| 完成后重复有效事务 | 返回相同certificate identity，提交边界仍为631/372块；不声称物理块去重或重复提交不再计算 |

这些是冷辅助namespace中的有限对照，不能外推到所有暖缓存取消、异步并发或公共IAM场景。既有授权盐、Manifest信任主体和时序通道限制保持原来的范围。

## 7. Mistral覆盖与本轮停止理由

Mistral三个QA来源中仍仅doc61获准；doc80实际Candidate与Raw不同，doc122的Raw门槛不合格。没有降低margin，也没有用分数提高替代行为一致。Repo继承L0，不能把它当成新认证失败或已证明无合法布局。

本轮没有执行新的L1/L2布局搜索，不能将当前L3的有限覆盖说成ContractKV所有合法布局的理论上限。该分支属于可选后续研究；本轮已经观察到Mistral成本不改善、普通Raw策略更优，未达到继续扩展正式验证的门槛。

最终决策：**GO作为有界机制记录；NO-GO作为统一默认替换或新的正文性能主结果。** 保留Qwen的实际改进、Mistral的负结果和普通Raw的强对照。暂不追加独立来源矩阵、候选搜索、新收益模型或调度器。

## 8. 可复现交付

所有原始响应、实际IDs/Native日志、失败/取消/重复记录、冻结源码和时钟归档为659个regular文件：

- archive：`results/tsc_exploratory_mechanisms_20261020/evidence_v1/all_raw_evidence_v1.tar.gz`
- 大小：26,111,377 bytes
- SHA256：`2f366d960cbf9a2880ec6fc5231f9b293e8a848f75fe1c6f127ef19e2624e9ee`
- 从该包在本地独立恢复，完整科学分析和实际hash驱逐取证全部值精确一致，659个原始成员SHA再次不变。

主要入口：

```powershell
# 已完成的审稿优先级核验见 reviewer_experiment_recheck_v1.json，无需重复运行。
python scripts/tsc_exploratory_local_verify_v1.py --root . --restore .artifacts/new_restore_name
python scripts/tsc_exploratory_breakdown_v1.py --root .artifacts/new_restore_name --output fresh_cost_breakdown.json
```

`analysis_v3.json`、`residency_forensics_v1.json`、`full_cost_breakdown_v1.json`、`local_independent_recompute_v1.json`与决策记录分别给出原始统计、物理序列、全费用、独立复算及选择理由。早期partial/v1/v2均保留，没有用后验结论覆盖原观察。

GPU编排从单次写入的launch/state时间戳计 **1,736.516秒（约28.94分钟）**；12个主服务时钟累计1,420.492秒、辅助测试累计45.927秒。编排墙时含模型加载、编译、双卡并行及清理，不是GPU算子累计时间。

完成后两张3090各24MiB、无compute PID；共享运行时和实验副本完整性均核验通过。没有修改正文、图表或Response Letter。
