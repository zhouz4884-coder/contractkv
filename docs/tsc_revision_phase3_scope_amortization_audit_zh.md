# 第三阶段：模板对象与行为作用域的对应审计

本记录响应用户新增的机制一致性意见，只审计代码和实验账本，不修改正文、策略、冻结样本或运行协议。`scripts/tsc_revision_r4_scope_object_audit.py` 是冻结之后新增的解释性 CPU 审计，不是新增的证书机制或 GPU 缩放实验。

用户随后把第三阶段明确收口为最后一次返修风险检查：保留 CALC、Scoped Behavioral Certification、PSTP、Service-Template Certificate 四项贡献；不新增证书体系或性能优化矩阵。正在执行的冻结独立验证完成后，只有作用域内稳定复现的实质退化、错误准入或发布不变量问题才继续修复；小收益和不普遍的 p99 改善不再单独触发下一轮研究。

## 从实现中确认的区别

当前 R4 客户端的 `gates`、`certificates` 和 registrar 决策以 `(namespace, query_scope)` 为键。十 tenant 展开时，同一个原始模板保留共同的 `shared_template_id`，由它确定 namespace；各 tenant 因此可以消费同一个行为 scope 的已记录决策。代码不是每 tenant 独立认证每个 scope。

稳定前缀状态预测采用 `prefixes[namespace][stable_prefix_hash]`，验证和编译业务请求使用模板 namespace 的 cache salt。多个行为 scope 可能对应同一个稳定前缀哈希。因此，行为资格与共享状态对象具有不同粒度。

但当前 R4 保存的是每 scope 的联合注册结果。两种索引不等于两个独立签名、独立生命周期或分别由服务端强制执行的证书对象。审计不能把这种概念区分包装成已经实现了新的双证书系统。

原部署模板模式在既定 prospective qualification 之后，以 **compiled prompt 的生成路径** 作部署 attestation 的参考；R4 则使用真实 **raw 业务回答** 作见证。原有部署条件、资格证据、任务质量审计与新的 raw-reference 保守模式需要分别说明。原部署 attestation 不能写成每个未来动态输入的 raw 等价性证明。

原 real-task 服务控制面还有签名 binding 检查。R4 的受控客户端 query 资格检查不能自动继承为“新 public endpoint 已经实现全部鉴权与双层证书强制检查”的证据。完整模型/运行时身份冻结、客户端资格检查、原有 binding 实验和服务端 PSTP 发布，各自对应的实现与测试要分清。

## 修补历程：哪些改变了，哪些没有

| 模式 | 见证与资格对象 | 相对此前的实际变化 | 论文中应如何处理 |
|---|---|---|---|
| 原部署模板模式 | 预先 route qualification；代表性 compiled prompt 路径的部署 attestation；模板身份和授权域检查 | 一个部署模板对象摊销其注册；未来私有输入有效性属于经验资格范围 | 保留原部署场景和原始质量/治理证据；不能写成任意未来 query 的 raw 等价性证明 |
| R1R | exact query 首次真实 raw 业务输出作为见证；`(namespace, query_scope)` 决策 | 改变了见证来源与行为资格粒度，仍沿冻结 ladder 下降；是受控保守模式，不只是补一个 if 检查 | 与原部署模式分别给出适用范围、覆盖和成本 |
| R2 | 继续 raw 业务见证和 query scope | 单次固定候选、逐 token/EOS margin、完整实际 IDs 和收益门禁；正式 v2 catalog 的 raw/candidate floor 均为 0.0625 | 属于准入与测量修补；不构成新的 CALC 或 PSTP |
| R3 | 继续 R2 见证与索引 | candidate floor 0.125、raw floor 0.0625，增加有限的 Python 输出语法准入 | 保留相应覆盖损失和新来源失败，不事后改分 |
| R4 | 继续 raw 见证、query scope 和原发布后端 | 收紧经验共享资格，调整已有收益/尾部准入；没有两个独立证书对象 | 作为保守运行条件及工程修补报告，不新增第五、第六项贡献 |

`scripts/tsc_revision_r4_method_semantics_audit.py` 对 13 个实际源码函数记录了 hash、位置和 AST 身份。它还确认：封存的 R1R-slice 与 R2-margin 后端中，验证 PASS 后的发布分支 AST 完全相同；修改主要作用于能否进入该分支的条件。这个静态结果只比较这两个具体后端，不等于证明原系统所有代码字节未变，也不替代既有 live 拒绝/零发布实验。完整记录是 `results/tsc_revision_r4/method_semantics_audit_v1.json`。

doc99 的 t1/t7 元数据变化在旧 query-scope 规则下确实会复用同一资格；已知对照发现 raw 路径变化而 candidate 保持见证。因此它是旧声明的经验范围内的失败，不能追溯性地称为“原本就不在作用域”。本轮才采用更窄准入，是否有效以完整新来源结果为准。

## 已完成开发数据的账本结果

以下是开发试跑的实测日志重算，不是新 50 来源的独立验证结果。每个冷会话模板有一个 tenant，每个 fan-out 模板有十个 tenant；每个模板都观察到三个 query scope。

| 模型 / 模式 | 模板数 | GPU 尝试 | 获准行为 scope | 观察到的稳定前缀哈希对象 | 编译业务请求 / 其中未来请求 |
|---|---:|---:|---:|---:|---:|
| Qwen / 冷会话 | 12 | 6 | 6 | 2 | 14 / 14 |
| Mistral / 冷会话 | 12 | 6 | 6 | 2 | 14 / 14 |
| Llama / 冷会话 | 12 | 6 | 6 | 2 | 14 / 14 |
| Qwen / 十 tenant | 5 | 15 | 13 | 5 | 414 / 374 |
| Mistral / 十 tenant | 5 | 5 | 5 | 2 | 160 / 144 |
| Llama / 十 tenant | 5 | 4 | 4 | 2 | 122 / 114 |

“稳定前缀哈希对象”只是已获准记录中的 `(namespace, stable_prefix_hash, stable_prefix_tokens)` 去重数，不是独立签名模板证书数、新分配物理块数或新事务提交数。编译业务请求包含初始 turn 中已经可以消费其他 tenant 资格的请求，因此与只统计未来请求的主表分母不同。

完整逐模板/逐 scope 记录、源码与原始文件 hash 见 `results/tsc_revision_r4/development_scope_object_audit_v1.json`。该文件同时保存原证书粒度消融 CSV 的原始字符串行，明确它属于另外的冻结部署协议，不与 R4 做跨协议延迟相减。

## 应采用的复杂度表述

若一个服务进程管理 T 个模板身份、U 个不同的行为作用域、M 个业务请求，当前保守模式保存 O(T+U) 控制状态，形成 O(U) 次 scope 决策。每个被选择的 scope 最多做一次 GPU 认证，认证工作可以跨该 scope 的授权 tenant 请求摊销。门禁拒绝的 scope 可能没有 GPU 认证，但仍有控制工作。

只有把每模板的 U 视为固定常数时，才能说相对于 tenant 数量的完整认证次数不增长。唯一 query / 动态作用域流若使 U 随请求数增加，认证成本可能随之增长。当前三个 query 的复用次数是受控 benchmark 声明，尚未测量生产重复频率；不能外推成一般生产服务中的 O(1) 行为认证。

## 由此调整的实验收尾要求

继续完成已经冻结的 90 单元，不依据新样本修改方法。完整收尾后，对两份正式协议分别运行同一对象审计，报告行为 scope、GPU 尝试、稳定前缀对象与实际 tenant 复用。先检验现有代码和证据是否足以支持清楚的模式划分。

若仅需限定复杂度与适用范围，不追加 GPU 矩阵。若决定把两个独立证书或新的在线强制绑定作为新增实现主张，则需要另立实现、冻结协议和验证，不能把当前 R4 结果归到未运行的新方法名下。

最新收口要求下，不主动引入上述新证书实现。先用真实实现、原有资格冻结/ScopeValid/fail-closed 路径和现有治理实验解释清楚四项贡献；不能为了追求每个性能单元都变好而继续展开研究。
