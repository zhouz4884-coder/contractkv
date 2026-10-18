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

15:23 UTC更新：Raw-only 7/7单元、840业务已全部验收；两套Raw supervisor/worker均退出0。正式390ea831协议、58个依赖文件与统计addendum在Git`f2c1fab35b74fd1136e759dca27309c69377e952`公开并逐blob/远程SHA核验后，启动formal supervisor318277、qwen worker318282。15:24实际命令、RUNNING状态和两个EngineCore319110/319177已核，首wave是共同/高负载Raw两单元。尚无完成的正式Contract效果，不重复Raw标定。

该标定最多 7 cells / 840 次 Raw 业务：4 个 baseline，之后 3 个 Qwen 负载 profiles。只用冻结公式推导负载与 SLO，不用 Contract 收益选择工作点。Raw/Contract 均保留 16K、QA128/Repo384、原 margin/scope/输出契约/PSTP。

正式24 cells与Gate ON/OFF6 cells由同一supervisor有界接续。16:35 UTC后，Qwen首次重复两个负载的4单元完整完成，第二重复按换GPU/反序的原计划接续。首轮各18/324 compiled future无ID/finish变化，但覆盖仅5.56%；共同Goodput .129948925→.128951612，较高负载 .006884815→.022886042req/s（8→27/360，基线小）。wall倍率.999988/.984928，负结果保留。新数据不是三重复结论。详细分解见`tsc_revision_final_serving_first_repeat_20261019_zh.md`。

19:01 UTC更新：Qwen12/12完整、exit0，6组编译配对检查全部通过；同一318277已启动cross worker414783，开始Mistral/Llama共同负载。Qwen三重复每load54/972 compiled future无ID变化，只涉及一个来源/scope；common pooled Goodput .126074002→.126569282、wall .999986×；high .013177818→.023277243、wall .990905×。12/30完成仍非全目标完成；不把小baseline倍率当主结论。详见`tsc_revision_final_serving_qwen_completed_20261019_zh.md`。

服务编排CPU检查已通过：六条轨迹符合原loader；Raw/Contract到达、GPU、重复成对一致；第二重复交换GPU/次序；两个server均ready才测量；同wave任一客户端失败则整个wave留作无效失败，不选择保留较好的一半。CPU检查使用fake transport，GPU请求数为零，不是效果结果。当前正式GPU执行另按实际completion记账。

23:05 UTC更新：cross12/12完整、exit0，M/L六组编译检查通过，主服务24全部完成；已自动进入Gate，实际worker517543。Mistral54/972、Llama48/972 compiled future，所有主编译ID/finish检查0变化；metadata计时比各.999372/.999568。完整native/质量升降/Goodput与CI仍待统一分析。当前24/30完成，余6隔离Gate、分析、复算与归档。

## 还需要完成

截至香港时间 2026-10-19 07:12（UTC 2026-10-18 23:12），Raw 标定 7/7 和主服务实验 24/24 均已完成。12 个主服务配对的编译输出 ID/finish 检查全部通过；其中未来编译配对共 210 条，分布在四个模型/负载组，每组只有少数获准来源，不能当作 210 个独立来源。Qwen common/high、Mistral common、Llama common 的完整 wall 合并倍率分别为 0.999986×、0.990905×、0.999372×、0.999568×：新开放到达协议没有显示完整 wall 加速，不能用此前闭环结果替代这一结论。全量评分、来源簇统计、队列和尾延迟仍待最终统一复核。

1. 只续查现有 supervisor 318277 / Gate worker 517543，不重复派发、预检或重新生成冻结文件。最后六个隔离 Gate ON/OFF cells 已开始，07:12 时为第一单元 26/360 业务、0/6 完成；这是运行中进度，不是效果结论。
2. 六个 Gate 单元及原formal supervisor全部结束后，由一次性CPU后处理进程525181依次调用已经冻结的完整分析、来源簇敏感性与后验完整性入口。该进程已实际核对命令，当前为`WAITING_FOR_FROZEN_GPU`；不要再手工重复启动这三项分析。计划`postprocessing_plan_v1.json` SHA为`822d6c53631af7948cd73e01ae3fa35a749ed4fd35725288e86b2b43854cfffc`，只是执行编排，不改变390ea831主协议/分析规则。GPU测量期间不运行重CPU分析；任一失败保留原日志和输出、不自动重试。
3. 归档全部新原始结果与失败，取回原包进行本地独立复算，不重复归档已验收的四项旧结果。
4. 完成五批总报告、贡献必要性矩阵、逐条审稿实证闭合矩阵、服务性能/尾延迟报告四份 MD，补齐 Trust matrix，commit/push 核远程 SHA。正文与 Response Letter 仍后置。

不以单次正结果提前收口，也不因为某个倍率温和而再增加有利负载或新算法。最终以保真任务、实际行为证据和完整服务成本判断原四项机制的价值。
