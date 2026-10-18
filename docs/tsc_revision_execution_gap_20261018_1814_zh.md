# ContractKV 三批核心实验：实际执行差额

核查时间：2026-10-18 10:14 UTC / 18:14 Asia/Hong_Kong。此文件是该时点的执行快照，不是最终实验结论。

最新用户目标已读取：`C:/Users/LENOVO/.codex/attachments/4bea3e90-15bd-4d67-bcea-804b880cb905/goal-objective.md`。新目标保留前三批，再增加有界的任务保真 Open-arrival 与 CPU 优先机制/尾部分析。不得在前三批后提前宣布整体完成。

## 核查依据

- 本地 HEAD 与远程 main 均为 `1197dbc4c08ecea9cb113195198f05dba5ffffae`。
- 原 Table III protocol SHA：`66c3e68d460102cbcb34d8bf59059155bb0e08aa6e10b45895524a7ef14a1982`；freeze SHA：`5491f9e6dc1a38da1ab264c62fa9993f259e5521ed9512d227f4f1cf3854242e`。
- 机制/Manifest freeze_v3 SHA：`7170c9101903326c582bc32e93ca2e4d7998b42b8fc5a8bb62c7d158ed8dd4ff`，保持不变。
- 原 Table III worker PID 141325 的实际命令匹配冻结 v3 入口，状态 RUNNING，current_pair=mistral_r1；两张指定 3090 正由该矩阵的 vLLM EngineCore 使用。
- 机制/Manifest 尚无 worker、无 preflight receipt、无 GPU responses.jsonl。不能将已有 CPU 结果计为本批 GPU 完成。
- 工作区的两项既有 PDF/ZIP 删除属于用户先前工作，不纳入本次操作。

## 当前三批差额

| 批次 | 实际完成 | 还欠什么 | 接续动作 |
| --- | --- | --- | --- |
| ① 原 Table III 全成本 | 12/24 fresh-server cells；6 个完整 Raw/Contract 配对；2,700/4,725 个未来配对。Llama、Qwen8B 各三重复完成。 | Mistral 与14B TP2共12 cells、2,025未来配对；随后完整计账/尾部/质量分析和全部原始归档。 | 只监测现有 worker。Mistral r1 正在运行，不重复启动，不重跑已完成12 cells。 |
| ② 跨模型机制必要性 | 五类受控案例及客户端源函数检查冻结；本批 GPU 结果0。 | 三模型三fresh-process共9 cells中的行为部分：180候选、720业务生成、最多180次GPU认证。还需真实候选输出、决策、后路由和实际发布数据。 | 保留当前案例和门槛；首批结束后执行已准备的入口。 |
| ③ Manifest闭环 | 原有9注册CPU案例、19绑定CPU检查已完成；新增接线检查为CPU证据，本批GPU发布/命中结果0。 | 与第二批共享同一组9进程；135业务生成、最多18次GPU认证。必须核对真实提交/回退、块链、native命中和合成标记覆盖。 | 不把CPU通过当在线隐私通过；不把binding拒绝compiled当Raw APC零命中。 |

第二、三批合计仍为9 cells、855业务生成、最多198次GPU认证；不是18 cells。四个模型的完整权重SHA已在首批完成，不重新准备或重复整份权重测量。新输入/独立strict runtime的一次预检与回执仍须完成。

## 仅需补齐的启动依赖

只读核查了 strict backend 的六份已登记源文件，全部与 R1R/R2 commitment SHA匹配。它们动态导入的五个项目模块中，四个没有被装入当前脚本快照：

- `scripts.contractkv_quiescence`
- `scripts.contractkv_shadow_parking`
- `scripts.tsc_revision_r2_execution_trace`
- `scripts.tsc_revision_r2_margin_policy`

这些是已有实现，不是新算法。只按原字节补包、做导入/哈希检查并单列补充清单；不编辑旧 freeze_v3、不重新构造案例、不重复旧CPU9/19检查，也不触动正在测量的首批 runtime。若没有补齐，后端会在启动时找不到模块，不能将其称为已具备GPU验收条件。

## 科学证据仍存在的两项边界

1. 当前冻结 `code_context` 为合成 Python 赋值顺序，并非真实 RepoBench next-line completion。它不能冒充新目标要求的真实RepoBench前缀证据。先索引已有真实任务记录；若不足，另用独立协议做最小必要补充，不改当前9 cells。
2. 原 Table III 老客户端没有保存完整逐请求输出IDs/Token长度。已核查的服务端文件保存实际生成tokens总量与分桶分布，不能恢复每个请求的全部ID序列。已有单元不重跑；保留现有真实总量/分布，无法恢复的字段明确标记。后两批和既有保真主验证的完整ID证据分别报告，不能用重分词推导冒充实际输出IDs。

计账分析还应同时保存老客户端原有 sanity proxy 与已归档 Phase20 的 benchmark-aligned诊断，分列说明，不替换原始 `task_score`。

## 已完成的阶段数字

| 模型 | 三次完整wall倍率 | 平均 | 状态 |
| --- | --- | --- | --- |
| Llama-3.1-8B | 1.009263 / 1.015763 / 1.009627 | 1.011551 | 已向用户汇报；108次验证含33次非通过，全部计时。 |
| Qwen3-8B | 1.028826 / 1.027719 / 1.004127 | 1.020224 | 本次差额汇报已告知用户；第三次较弱保留，原因待完整分解。 |

这些为“原 Table III 同样本固定策略完整成本复测”：保留策略中的2s/6s参数，但完整wall不减任何slack。不能称为把策略参数全部改0后重新选布局。

另一个已完成的“保真输入六来源十租户主验证”是零slack完整服务测量，三模型为1.619036 / 1.109074 / 1.070280，属于不同输入、复用密度、预算和资格流程，不能与本表拼接成同条件升级曲线。

## 新目标的后续差额

- 第四批尚未开始：前三批完成并归档后，独立冻结新保真来源、Raw-only负载标定、到达轨迹和SLO；最多Qwen12个正式cells，再扩展Mistral/Llama合计12个。已有闭环结果与旧固定到达5/54单元保留，不重复或冒充新桥梁实验。
- 第五批CPU优先：布局阶梯、Gate/Margin、p99时序和已有PSTP证据索引；只有具体缺口成立才触发独立、小规模GPU。
- 先前三批，再按新目标接续；此前5–8小时预算只覆盖原三批，新增正式矩阵不在该预算内。Raw标定后再给新增阶段的实测时间估计。

不重新启动已有worker、不覆盖历史freeze、不按当前倍率增删来源。最终正文和Response Letter仍后置。
