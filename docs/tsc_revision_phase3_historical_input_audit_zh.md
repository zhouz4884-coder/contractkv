# 历史输入处理溯源与实验有效性核对

本记录是实验审计，不修改投稿正文。结论是：顺序词预算与空白折叠并非 R4 新增；它们也出现在原稿主性能实验及既往返修实验的数据路径中。其影响需要按实际来源和任务逐项解释，不能只给 R4 加限制，也不能据此把所有缓存、计时和事务证据一概作废。

## 代码和声明的对应

公共函数 `scripts/phase13b_fresh_policy_quality_replay.py::build_case` 按原 segment 顺序消耗词预算，通过 `" ".join(text.split()[:remaining])` 保留前部并折叠空白；SYS_PROMPT 和 USER_QUERY 在此预算之外。当前整份文件 SHA256 为 `a9f1f694f20559e7dd50ff780141b438ca5fef541099b53d9213ad904f8d7a63`，与 2026 年 7 月仓库提交 `1e7f633` 的文件字节一致。R1R、R2/R3、R4 的冻结快照同样包含该函数。

原稿主表的启动路径是：Qwen8B／Mistral 的 `run_submission_repeats.sh` 调用 `phase19b_end_to_end_live.py::turn_case`；Qwen14B 的 `run_phase23_qwen14_scaleup.sh` 也调用该客户端；Llama 的 `phase22_llama_broad_live.py` 导入同一 `turn_case`。原稿 Qwen8B／14B 的词预算为 2600，Mistral／Llama 为 1500。R1、R1R、R2、R3、R4 为 1500。

这些源码、启动声明和输入承诺可以证明数据处理的对应关系，但不是事后补出的逐请求历史 prompt IDs。早期部分 split digest 只绑定 sample/group 身份，不能单靠该 digest 证明所有旧文本字节；本次恢复文件的字节哈希、历史承诺类型和该限制均单独保留。某些历史路径还调用 `_retokenize_case` 以适配模型窗口，可能发生额外截断；下表只重建词预算这一步。

追加交叉核验显示：恢复的 Llama／14B 以及现存 Qwen8B／Mistral 四份完整输入文件，均与 R4 选样前 exclusion commitment 中登记的整文件字节哈希一致。该承诺早于本次输入问题诊断，补强了存储输入来源的可信度，但仍不能补造缺失的历史逐请求 prompt 记录。追加证明为 `results/tsc_revision_r4/historical_input_additional_provenance_v1.json`。

## 各来源组的重建结果

HotpotQA 的“字面串”只做大小写与空白归一化，不是语义可答性判定。原存储文本中没有完整参考串，不等于没有足够线索；串被保留也不保证模型会正确作答。

| 来源组 | 词预算 | HotpotQA 来源数 | 原文含参考串 | 保留输入含参考串 | 截断后丢失 |
|---|---:|---:|---:|---:|---:|
| 原稿 Qwen8B 主表 | 2600 | 10 | 6 | 4 | 2 |
| 原稿 Mistral 主表 | 1500 | 10 | 9 | 5 | 4 |
| 原稿 Llama 主表 | 1500 | 10 | 9 | 4 | 5 |
| 原稿 Qwen14B 主表 | 2600 | 5 | 5 | 3 | 2 |
| 原稿五模板任务审计 | 1500 | 1 | 1 | 1 | 0 |
| R1 共同 HotpotQA | 1500 | 30 | 27 | 15 | 12 |
| R1 自由生成 | 1500 | 10 | 9 | 6 | 3 |
| R1R | 1500 | 10 | 8 | 6 | 2 |
| R2 | 1500 | 10 | 9 | 5 | 4 |
| R3 | 1500 | 10 | 9 | 3 | 6 |
| R4 | 1500 | 10 | 9 | 1 | 8 |

| 来源组 | RepoBench 来源数 | CODE_PREFIX 裁空 | 部分词保留 | 全部词保留 |
|---|---:|---:|---:|---:|
| 原稿 Qwen8B 主表 | 10 | 5 | 0 | 5 |
| 原稿 Mistral 主表 | 10 | 7 | 1 | 2 |
| 原稿 Llama 主表 | 10 | 7 | 1 | 2 |
| 原稿 Qwen14B 主表 | 5 | 3 | 0 | 2 |
| 原稿五模板任务审计 | 1 | 1 | 0 | 0 |
| R1 自由生成 | 10 | 7 | 2 | 1 |
| R1R | 10 | 6 | 3 | 1 |
| R2 | 10 | 6 | 1 | 3 |
| R3 | 10 | 7 | 1 | 2 |
| R4 | 10 | 5 | 2 | 3 |

以上各组 RepoBench 原有换行均在词预算适配后被折叠；“全部词保留”不等于格式或正常代码补全语境完全保真。R4 的主要 Llama 异常来源 Yuan 属于全部词保留的一类，因此不能把它的同 prompt IDs 下 raw／L0 差异简单归因于前缀裁空。

原稿五模板审计虽然有 50 个 tenant sessions，去除复制后只有 5 个来源。其 HotpotQA 原始与保留输入均含参考串，raw／策略 F1 均为 0.5；NarrativeQA 均为 0，RepoBench 均为 0.08。这些绝对分数与相对保持应同时交代。没有依据把“五任务无相对下降”直接解释成五个正常任务都表现良好。

## 与 marker 服务和 Table I 的区别

`tsc_open_loop_service.py::make_case` 会将原始 query 和目标替换为 PRIVATE_TOOL_OBS 中的 marker。其大规模服务实验是控制过的 marker 任务；保留完整原 QA 答案并非完成 marker 的必要条件。这些日志中的真实缓存命中、块计数、注册成本、吞吐和状态控制仍是该受控任务下的测量，不能替代正常 QA／代码服务的应用有效性证据。

原稿 Table I 的 82.4／2.1 等数值首次在提交 `dcfa7d2` 写入正文。本轮已定位到该版本，但尚未找到其独立生成表与原始数据逐值映射。正文里的数字本身不构成独立验证，不能把此项标记为已复现。后续若仍无法恢复映射，应删除相应未核验的标题性主张，或另行给出可复算的受控 trace 统计；不得补造历史出处。

## 对下一步的约束

当前 R4 全部结果继续保留。现有审计已经说明有必要补一组独立冻结的输入保真对照；只修任务输入，固定 ContractKV 算法、准入规则、评分和成本口径，不能按答案位置裁剪或按表现选择来源。该对照用于检查实验协议有效性，不是新增认证算法，也不预先保证覆盖或收益提高。

定量记录为 `results/tsc_revision_r4/historical_input_audit_v1.json`，生成器为 `scripts/tsc_revision_r4_historical_input_audit.py`。恢复的三份历史输入及身份承诺检查随记录留存，其中 Llama／14B 为 sample/group 身份 digest，五模板任务审计为完整行的 canonical digest。所有来源、错误输入、既往负结果与限制继续归档。
