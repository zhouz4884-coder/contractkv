# 原 Table III 完整费用复测：第一批完成报告

状态：24个formal fresh-server单元、12个Raw/Contract配对、4,725个future配对和525个完整controller已完成。本文只关闭第一批；机制/Manifest及新增服务桥梁尚需接续。

## 三种费用口径分列

策略仍保留原2s/6s参数，模型、来源、旧renderer、候选和scope不变。A按原Table III的residual-slack定义重算；B和C不抵扣任何slack。A是预算费用估计，B是组件摊销，C是直接测得的完整service wall。三者不可互换。

| 配置 | 历史A：原报告TTFT降低 | 新A：同定义TTFT降低 | 新B：完整controller零隐藏费用TTFT降低 | 新C：完整wall吞吐倍率 | 三重复C范围 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Llama-3.1-8B-Instruct | 29.41% | 29.47% | -0.20% | 1.011551× | 1.009263–1.015763× |
| Qwen3-8B | 37.81% | 31.50% | 10.82% | 1.020224× | 1.004127–1.028826× |
| Mistral-7B-Instruct-v0.3 | 31.72% | 31.78% | 2.00% | 0.993820× | 0.985267–0.998930× |
| Qwen3-14B TP2 | 44.69% | 42.31% | 20.93% | 1.109442× | 1.099322–1.114763× |

C为三次配对倍率的算术平均；范围是固定来源上的进程重复描述，不是独立来源置信区间。14B TP2在该冻结工作点有约10.94%净收益，8B/7B收益较小，Mistral略慢。零slack不保证每个模型都加速。

B按全部future摊销完整controller，包含reference、准备、全部验证/失败/下降和L0 warmup时段；C还包含实际decode、并行请求、基线warmup及完整原main调用。故Mistral的B为正而C略负、Llama的B略负而C略正均可成立。这里没有将token节省换算为纯GPU因果时间。

A的业务/raw均值均取全部future；残余费用分母按历史定义分别取Qwen8/Mistral的certified futures及14B/Llama的all futures。Llama历史字段仍仅保存最终成功档或拒绝后0，A保留该原定义；所有新增实际费用在B/C完整计入。旧的缺失时间戳没有被恢复或补写。

## 完整计账与执行纪律

- 525个完整controller与全部原始canary逐项对应；453次真实认证HTTP访问与包装函数尝试逐cell匹配，全部有正耗时。
- 155次非通过验证尝试，以及30次包装调用异常均保留费用；60个无包装RPC的L0 warmup也在完整controller内，不能记为零费用。
- 108次Llama验证尝试全部计时，包含此前历史记录丢失的中间失败类别；这是新批次测量，不是补回7月时间戳。
- 原TableIII 19个已完成单元原样复用，仅执行余下5个未测单元。14B首个Contract在模型/业务启动前发生端口bind故障，保留失败及原完成Raw，通过公开v4执行补充接续；原始Raw/Contract顺序在r2反转。
- 全部输入及原源码SHA、既有独立runtime清单、已登记模型asset的size/mtime在完成后再次匹配；没有重新下载、复制模型或再做一遍完整权重SHA。保留已知backend兼容性与旧模型原始SHA不可完全追溯的边界，不声称July环境逐字节复现。

## 自由生成与两类评分

原驱动sanity proxy的已存数值逐值复算一致；Llama原客户端未存task_score，其proxy列明确为从原冻结函数重算。另列既有Phase20 benchmark-aligned诊断（QA F1 / RepoBench旧edit-similarity等），没有改动原评分或在线决策。

| 模型 | 全路线配对 | 全路线文本变化 | 次级任务分数上升/下降（>0.03） | compiled配对 | compiled次级下降 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Llama-3.1-8B-Instruct | 1350 | 45 | 0 / 0 | 675 | 0 |
| Qwen3-8B | 1350 | 32 | 1 / 3 | 873 | 1 |
| Mistral-7B-Instruct-v0.3 | 1350 | 49 | 6 / 0 | 675 | 0 |
| Qwen3-14B | 675 | 0 | 0 / 0 | 459 | 0 |

Qwen8B的RepoBench389/r3/turn1在compiled路由出现次级edit-similarity 0.72→0.38；RepoBench136的两个0.21→0.11下降在raw-order回退路由。该compiled事件在原sanity proxy中未触发下降，不能据原proxy宣布质量完全保持。Llama的三个proxy下降来自同一NarrativeQA155/turn2，其QA F1两路均为0；两种评分分别保留。

对这两个Qwen来源逐个读取三个重复的原始canary/warmup/future文本，记录在legacy_negative_text_forensics_v1.json。Raw、reference或Contract均有跨重复文本变化；旧客户端没有完整逐请求Prompt/Output IDs或batch轨迹，尚不能唯一归因为布局、scope、cache或数值执行。它们不被归入当前严格保真协议的“零观察分歧”分母，也不据此对新数据调参。

## 可观察性和证据文件

- 旧客户端完整输出文本均在，逐请求实际字符/UTF8字节长度已审核；逐请求模型token长度和IDs未保留，不以重分词伪造。Llama未来finish_reason已存，其他三配置未存；按模型列出覆盖。
- 原stream helper的TPOT按非空SSE delta片段计算，不能升级称作实际模型token间隔。实际server generation-token lifetime总量与分桶另存，不当作逐future长度。
- initial-request probe与实际RPC是不同分母，特别是legacy多级下降可复用request ID；不能用initial metrics条数推导GPU forward数。HTTP请求也不是GPU kernel计数。
- analysis_v3/summary_v1.json及配套CSV/JSON给出成本、逐controller和逐配对评分；output_observability_v1/给出文本长度与453次真实HTTP访问；post_run_integrity_v1.json给出完成后完整性检查。
- 全部Raw/Contract日志、失败、metadata及源码封入801个regular文件，原始压缩包52,671,414 bytes，SHA256 `9d324d82cbb0262240cc27cab0505f694e9e37b468a2cad3b34a89774162b7cf`；两份32MiB以内分片已在远程逐成员验证。首个复用Raw在transport中为字节相同的常规文件视图，未产生第二次模型实验。

当前结论：Reviewer3关于原TableIII完整费用的主要数据缺口已由同cohort新测量补齐；低复用完整wall收益有限、旧资格模式的个别质量变化和旧日志字段缺失全部保留。当前严格保真主验证仍属于另一份已完成实验，Qwen/Mistral/Llama分别1.6190/1.1091/1.0703×，不能将两个协议连成同条件升级曲线。正式论文与Response Letter后置。
