# ContractKV：整体重构与配图记录

日期：2026-10-17。输入为作者上传的 `ContractKV_revision_round1_20261017.zip`；原压缩包和解包快照未覆盖。本轮只写作、绘图和编译，没有新 GPU 实验、算法修改或实验调参。

## 一个主信息

**把编译后的稳定 KV 前缀作为有行为证据、身份与授权绑定、事务发布边界的服务对象，才能把结构性重复变成可审计的实际服务收益。**

叙述顺序是具体 RAG 请求的前缀断点 → 合法重排仍缺少行为准入和共享发布控制 → 原四机制 → 同来源严格全成本性能 → 自由生成与覆盖 → 治理、摊销及实际驻留。没有增加第五个创新点。

## R1 指定的删减

已核对原始大修信 `major .txt` 第115行：R1明确建议压缩 segment model/dependency/layout 定义，减少 evidence/scope 与 service-template material 的重叠，消除协议表文重复，并将单句式相关工作归组。

- 精简模型、请求实例、算法步骤和同一组指标的重复报数。
- certification 小节集中说明 witness、适用作用域及接受条件；certificate 小节集中说明身份、授权、生命周期和摊销，避免反复解释两个索引。
- 主文以图展示性能、行为和治理；逐次结果及扩展表移到独立补充材料。
- 相关工作按物理复用、服务调度、成本/契约/隐私归组。
- 首轮嵌图稿13页；精简后主文12页，包含六图、两表、算法和28项参考文献。沿用正常 IEEEtran 双栏字号，没有负间距压缩或整体缩字。

## 各节职责

| 章节 | 读者需要获得的结论 | 对应证据 |
|---|---|---|
| Introduction | 重复文本不能自动成为安全可共享前缀 | 固定 Azure 模板实例；一个服务对象主张 |
| Background | 稳定内容占比和 native 可恢复量之间有可复算缺口 | Table I 的实际 IDs/命中分母 |
| Service model | 依赖、身份及四项发布属性各约束什么 | 形式化定义；P1–P4 |
| Design | CALC、scope、PSTP、template certificate 如何连成一条路径 | Fig.1；Algorithm1；margin/commit/成本公式 |
| Implementation | 真实执行路径、保真输入和计时口径 | 版本、窗口、冻结 wave 时钟、计数定义 |
| Evaluation | 严格准入仍能偿还成本；资格、治理和驻留各自起作用 | Fig.2–6；覆盖、p99、L0和成本变体 |
| Related work | 本文增加的是行为准入和发布治理的耦合 | 沿用作者提供的文献，按机制组织 |
| Discussion | 哪些输入和服务条件允许摊销，哪些保证并未提供 | unique-query、manifest信任、timing channel、规模边界 |

## 图形处理

| 图 | 本轮改动和自主判断 |
|---|---|
| Fig.1 | 根据新参考图重画可编辑矢量架构。保留三段故事，去掉重复底部流程和装饰字段。实际画出 SYS→OBS a/b→DOC 的断点；compiled 顺序为 SYS→DOC→OBS→Q。两种 witness 明确是分别评测的协议，不是多个 witness 合成。PSTP 仅作 PASS+binding 提交，不作第二次模型验证。相同模板的两个租户共享同一前缀。未使用无来源的4096等样例数值。 |
| Fig.2 | 用橙色强调实际认证堆叠顶边并保留真实高度，没有扩大认证工作数值；明确 future requests/frozen wave clock；保持无柱顶圆点。 |
| Fig.3 | 改为“Compiled subset: raw reference score > 0”，分母和不等于完整正确率的含义写入图注。精简实际请求链底注。主覆盖仍为共同保真 HotpotQA/RepoBench；RULER仅留在历史审计聚合中，并在正文交代2178/2442的构成，避免合成任务主导应用证据。 |
| Fig.4 | 改为 Goodput under governance，保留D1/D2均值和明确的五进程min–max。 |
| Fig.5 | 图内直接说明 registered tenants, not concurrent GPU requests；左右不同SLO/到达协议继续分开。 |
| Fig.6 | 核心图形与数据保持，仅纳入统一版本导出。 |

## 保留的关键边界

- 0/1296 和 0/2442 是有限作用域内观察到的 output-ID 事件数，不是100%语义或未来安全保证。
- raw正分/零分保留；全路由L0变化和归因限制仍在主文。
- 三模型主验证的p99点估计均变差；成本适配的覆盖/吞吐损失没有隐藏。
- 部署模板注册与query-qualified的witness来源和 O(1)/O(U) 成本明确区分。
- FAIL下零promotion仅指被拒的compiled candidate；不宣称raw fallback完全不缓存。
- manifest CPU helper未接入live endpoint；可信误声明不能靠hash识别；不实现时序通道防御。
- 驻留探针不是新独立质量样本，也不是性能修复。原性能已经计入miss和重算。
- 未完成的5/54固定到达单元没有被写成完整容量验证。

## 编辑性调整

保留全部引用键；主文参考文献按首次引用顺序重排，另有独立补充材料编号。出版元数据沿用作者上传稿，本轮没有宣称重新完成外部文献元数据核验。将witness的非终止token序列与terminal token分开定义，避免自然EOS被重复计数的表达歧义；补充有限精度/执行形状下归纳论证的条件。这不改变认证实现或实验结果。

`input_*`证据索引文件是原上传稿的历史快照，里面的章节/页数不代表最终重排。本轮实际位置与编译信息以 `manuscript_QA.json` 和当前主文为准。正文仍是供作者审阅的重构稿；作者简介和正式逐点Response Letter不在这次写作范围内。
