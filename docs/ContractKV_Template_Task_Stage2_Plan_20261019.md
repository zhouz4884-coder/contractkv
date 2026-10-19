# 第二阶段：真实任务承载的模板资格同协议验证

用户明确要求完成新建议的第二阶段。本轮不编辑主文/Response Letter，不重跑 F8，不重新扫描 margin、L1/L2、Clean Renderer 或 Early-Abort。


## 用户补充后的v2范围（优先于下方v1初始设计）

尚未产生GPU输出时，用户明确补充Qwen优先、HotpotQA+RepoBench、六正式模板、8租户8轮、两负载与三重复。保留v1和已完成的5个Hotpot来源CPU预检；Hotpot来源不重新选择，以原始内容在v2重新作窗口检查，再盲选2开发/3正式Repo来源。旧6个未消耗验证来源仍排除，未用于试参。

当前正式上限：Qwen3臂×2负载×3重复=18 fresh-server单元；Mistral/Llama仅在各自开发验收通过后各3臂×1共同负载×3重复=9单元。每单元6模板×8tenant×8未来业务=384请求，最多36单元/13824业务。家族未通过即Raw fallback，全家族仍保留正式来源和分母。先Qwen P1；如果无家族合格则直接停止，不因失败改源、档位、门槛。

Qwen开发为2QA+2Repo，每来源2tenant×3turn的Raw/候选配对和一个私有compiled canary，共52生成；保留原L3不试档。Repo额外沿用现有python_statement_contract，不取消旧格式保护，canary未通过时不做GPU认证。QA预算128、Repo384；8租户turn0..8的全部真实tokenizer形状在运行前冻结。

原部署compiled-path attestation与Raw配对质量审计分开；canary在controller-private缓存命名空间生成，避免认证前候选进入业务共享缓存。Session与Template使用完全相同canonical代表性canary，并允许两者在同一个controller-private组中缓存复用；业务三臂的cache group完全相同，仅证书索引/签名作用域按session或template区分。

Raw-only开发fresh-server闭环80请求只用于标定：Qwen固定0.8与1.0×实测backlog速率两档，其他合格模型固定0.8×各自速率；SLO按事前p95公式冻结，正式source/arrival/clock规则不能按Contract结果改变。客户端从同一个全局epoch接收预定到达，注册等待纳入TTFT/全wall，不增加wave屏障。主要指标为计划到达TTFT/Goodput与完整费用，不要求Template Goodput显著高于Session；只证实费用摊销时就如实给出该结论。

## 科学问题与边界

在一个事前合格、授权重复访问的任务模板中，将认证对象从 Session 改为 Service Template，是否能在相同物理缓存共享条件下，保留实际任务质量，并降低完整资格费用、改善到达时刻计算的服务指标？

选择 HotpotQA 固定问题/检索文档作为注册 FAQ 条目，十个授权 tenant identity 重复访问。使用原服务任务质量协议的 neutral private tenant/turn 工具元数据，原真实问题不替换为 marker。它是“真实数据任务 + 受控部署与到达”的实验，不是生产 trace；不声称实际业务有这些重复频率，也不声称所有应用必须把 tenant 元数据放入模型输入。选择不依赖模型表现，全部来源和受控结构公开。

与原部署协议一致，Session/Template 两路都对同一个代表性 **compiled** 生成路径进行部署 attestation。它不证明未来 Raw 等价。开发前瞻质量资格与独立正式 Raw 配对检验承担相应证据，不能借用 F7 的严格 Query-qualified 保证。原 F8 全部保留。

## 冻结设计

- 新开发2来源、独立正式3来源；排除全部729历史/已预留来源，按固定哈希序与容量选取，不读输出或 gold 位置。
- 只用原 L3、16K 保真输入、128-token 任务预算和既有0.0625/0.125/EOS/PSTP门槛。不再试档或调提示词。
- 三模型各一个开发 fresh-server；每模型12个 Raw/候选实际生成配对，另2个私有 compiled canary，共26次生成。两来源均 attestation PASS、无>0.03掉分、来源均分不降且至少一来源 Raw 有正分，才允许该模型进入正式验证。零模型通过则停止。
- Raw APC / Session / Template 的业务缓存身份采用同一个授权模板组，不能通过按 session 分盐人为剥夺 Session 或 Raw 的物理共享。compiled canary 使用独立 controller-private 命名空间，未认证状态不进入业务共享缓存。
- 两种证书粒度只改变注册对象个数；代表性路径、布局、授权对象、缓存局部性、门槛和到达规则相同，实际每次 canary/准备/验证费用保留。既有签名绑定检查覆盖运行时、生成、输入 manifest、固定问题、布局/稳定前缀、授权域与epoch。
- 正式最多三模型×三臂×三fresh-process重复=27单元，每单元3模板×10tenant×6未来请求=180业务。只运行开发通过模型，不能按正式结果再筛。
- 开发源 Raw-only fresh-server backlog标定吞吐与p95；按冻结公式选择一个90%到达率与SLO。所有正式臂共用预定时刻，从服务epoch开始计入注册等待，零slack，客户端并发2，不新增调度器。

## 验收与收口

主要报告到达至首token/完成的Mean/P95/P99、SLO绝对Goodput与达标率、真实业务和资格额外prefill、完整注册费用、失败与覆盖、实际输出及任务得分。Wall倍率保留为辅助指标。统计按来源簇与重复分层，三来源不能伪装成几千独立样本。

先通过开发与身份/PSTP检查，才冻结正式目录/负载。若前置条件不足，记录NO-GO并完成本轮；若正式结果不利，同样保留，不改阈值或增加新的有利负载。完整MD报告、原始结果、独立复算、决策记录与Git远程SHA核验后收口。
