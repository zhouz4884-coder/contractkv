# ContractKV 最终实证阶段进展（2026-10-18）

本记录是执行进展，不是全目标完成声明。五批目标见 `tsc_revision_final_strengthening_objective_20261018.md`。已完成实验保持原样；正文与 Response Letter 在实验和证据汇总完成后处理。

## 已经完成、归档并独立复算

| 实验 | 完成量 | 实测结论与必要边界 |
|---|---:|---|
| 原 Table III 全成本重测 | 24/24 cells；4,725 future pairs | 直接完整 wall 吞吐均值：Llama 1.011551×、Qwen8B 1.020224×、Mistral 0.993820×、Qwen14B TP2 1.109442×。原策略 slack 参数不改，但直接 wall 不抵扣 slack。A residual、B 全 controller 零隐藏摊销、C 完整服务三口径分开。旧模式的实际质量下降保留。 |
| 多类型行为机制与 Manifest | 9/9 cells；855 正式业务，另保留 63 条失败附录 | 180 个候选条件中 102 个实际 ID/finish 变化全部拒绝，30 个实际掉分全部拒绝；78 个获准候选后续无变化。人工受控病例，不声称一般安全保证。可信 operator 误标仍能发布人工私有 marker；Raw 原生 APC 不受此绑定全面隔离。 |
| 256-token 等预算条件 | 3/3 cells；240 次回答 | 全部自然结束，无 length；26 个获准候选后续无变化。保持原整数-only 评分，长解释不因最后包含数值而改判正确。不自动扩展 512。 |
| 真实 RepoBench 机制检查 | 3/3 cells；72 次回答，18 个模型×候选条件 | Qwen 两来源获准 L3 后实际命中 9,712 / 3,328-token 前缀，4 次获准后业务无变化。Mistral/Llama 仍由 one_python_statement 早拒；这 12 个条件没有发 GPU 认证，不能写成 GPU verifier 拒绝。保留 Llama 的 384-token length 事件。 |
| 第五批已有 CPU 分析 | 已完成 | 720 布局/19,440 segment，4,860 条未来时序、native 驻留/排队分析，两 margin floor 固定网格，既有 PSTP 故障/提交证据。CPU 推导不当作新服务效能。 |

四项 GPU 结果的详细报告：

- `tsc_TableIII_fullcost_replay_completed_20261018_zh.md`
- `tsc_revision_mechanism_manifest_results_20261018_zh.md`
- `tsc_revision_budget256_results_20261018_zh.md`
- `tsc_revision_real_repobench_mechanism_results_20261018_zh.md`

已公开原始证据 SHA 与独立复算回执位于各结果目录。上述四项完成结果的发布快照为 `4274272109aeec61d5264e9a7ba14970ae65dd53`；后续Raw实际参数另在`669898c4bd4140154cf009fb95a793e05ab424f9`公开并核远程，不覆盖完成结果快照。

## 当前 GPU 执行

14:40 UTC 后核验：Raw-only baseline 4/4 单元、480 次业务全部完成；原 supervisor285458/worker285459退出0。实际derived plan已经生成并独立复算、核验公开SHA后，14:44 UTC启动3个Raw profiles，supervisor301481/worker301486。14:46实际进程与两卡EngineCore已核验，处于模型准备阶段，尚未产生正式Contract结果。详见`tsc_revision_final_Raw_calibration_20261018_zh.md`。没有重复启动baseline。

该标定最多 7 cells / 840 次 Raw 业务：4 个 baseline，之后 3 个 Qwen 负载 profiles。只用冻结公式推导负载与 SLO，不用 Contract 收益选择工作点。Raw/Contract 均保留 16K、QA128/Repo384、原 margin/scope/输出契约/PSTP。

正式 24 cells 与 Gate ON/OFF 6 cells **尚未开始**。服务编排 CPU 检查已通过：六条轨迹符合原 loader；Raw/Contract 到达、GPU、重复成对一致；第二重复交换 GPU/次序；两个 server 均 ready 才测量；同 wave 任一客户端失败则整个 wave 留作无效失败，不选择保留较好的一半。以上检查使用 fake transport，GPU 请求数为零，不是效果结果。

## 还需要完成

1. 完成当前 4 baseline 和随后 3 Raw profiles，冻结实际负载、SLO 与所有正式到达轨迹。原 Raw worker 和输入不重做。
2. Qwen 两负载 12 fresh-server cells；确认执行和编译行为不变量后，Mistral/Llama 共同负载额外 12 cells。每 cell 360 次业务、324 次未来请求。
3. Qwen 隔离协议下 Gate ON/OFF 三对，共 6 fresh-server cells。只关闭经济判断，不绕过行为资格；不借用并行 Raw 冒称隔离加速。
4. 分来源/进程进行 Goodput、质量双向变化、完整 wall、队列和尾延迟归因；归档全部原始结果与失败，独立复算。
5. 完成五批总报告、贡献必要性矩阵、逐条审稿实证闭合矩阵、服务性能/尾延迟报告四份 MD，补齐 Trust matrix，commit/push 核远程 SHA。

不以单次正结果提前收口，也不因为某个倍率温和而再增加有利负载或新算法。最终以保真任务、实际行为证据和完整服务成本判断原四项机制的价值。
