# ContractKV：Table I 之后的实证闭合审计与补测决策

本轮原则：先补强实验证据，能测的优先测；不以文字限定代替可解决的计时缺口。不新增认证算法、证书结构或工作负载研究线。正文草稿暂存，待复测完成后再决定修改，Response Letter 暂不撰写。

## 当前结论

| 项目 | 本轮实际完成 | 仍需做什么 |
|---|---|---|
| Table I | 保留已完成的五家族独立原生缓存测量及六来源三模型证据 | 不再为接近旧 85.0/2.4 调参数；旧精确数值链未恢复 |
| 原 Table III | 找回原请求与更多 Llama 日志；四配置原均值可复现；匹配样本的已记录 RPC 零 slack 成本可算 | 完整历史费用仍有缺失；已冻结原样本的新计时复测，等待 GPU |
| Manifest | 重跑 9 例注册 helper、19 例实际 binding 函数、8 项既有测试 | 语义误声明仍可接受；不把 helper 当 live endpoint 或保密分类器 |
| 原 RULER CI | 从找回的原请求重放 10,000 次 bootstrap，原模型/宏平均区间复现 | 已加同步来源的事后敏感性分析；不是新增模型/任务的泛化区间 |
| 92.90/92.62 | 追到各自确切实验单元、分母、生成代码 | 需在最终正文/回复对应标明；不是同一 cell 的数值冲突 |
| Fig.5 Goodput CI | 从原 raw 请求的计时投影及 summary 重算，四个 SLO 桶均复现 | 不把单点区间推广为整条容量曲线 |

## 1. 原 Table III：CPU 能恢复什么，为什么仍需要测量

原始未来请求共 4,725 对，四配置各三次进程。已记录 verifier RPC 的匹配零 slack 结果如下；这里仍没有完整 controller 的含义。

| 配置 | 原 residual-slack 降低 | 零 slack，原分母 | 零 slack，全部未来分母 | RPC 计时覆盖 |
|---|---:|---:|---:|---:|
| Qwen3-8B | 37.81% | 16.81% | 28.91% | 147/147 |
| Qwen3-14B TP2 | 44.69% | 34.39% | 34.39% | 72/72 |
| Mistral | 31.72% | 2.83% | 19.74% | 126/126 |
| Llama | 29.41% | ≤20.37% | ≤20.37% | 75/108 |

Qwen8B/Mistral 原报告用获证未来请求数归一化验证残余，14B/Llama 用全部未来请求数；因此保留两个分母，不能挑漂亮的一列替代原口径。Llama 丢失 33 次失败/中间 RPC 时间，20.37% 是节省上界。另有 Qwen8B/14B 各 3 次、Mistral 24 次 raw-reference 截止于 length，异常路径未留下完整耗时。Llama 150 个 controller 聚合计时均缺失。

本轮额外取回三个 Llama contract metric 文件与三份 server log：1,590 个 metric 观察中的 prefill/decode GPU 时间全部为空；server access log 能证明 verifier 调用数量，却没有逐调用耗时。scheduler wait 不是 controller wall，不能替代。故在这些现存文件中无法恢复丢失时长。

已知完整 controller 时长也比 RPC 大：仅将已记录的 controller 成本摊入全部未来请求，Qwen8B/14B/Mistral 的节省上界分别为 17.02%、24.39%、8.59%；因异常耗时仍缺，不能把这三个数当完整成本结果。Llama 连这一列都不能定量闭合，保留空缺。

**决定：补原样本计时，不再继续用统计近似填洞。** 已冻结四配置×三重复×Raw/Contract 的 24-cell 方案，原未来键 4,725 对。取回 175 个原注册 session，核对每次重复 1,575 个未来键，CPU 检查 1,750 个 raw render，归档历史客户端 356 文件及 SHA。计时补丁覆盖成功、拒绝、异常和多级下降；CPU 控制流测试通过，不冒充 GPU 结果。

当前两张 3090 被 RevBatch 占用。用户已确认等该任务结束后再运行；不得终止其他工作、混跑测性能或静默改协议。完整执行细节和剩余 runtime 预检在 `results/tsc_tableIII_fullcost_replay_20261018/RUNBOOK_zh.md`。**此轮新 GPU 请求数为 0，GPU 复测尚未开始。**

## 2. Manifest：已有反例比新增无关 GPU 矩阵更有解释力

9 例 CPU helper：7 个显式不合法声明被拒；合法声明和可信运营者的语义误标各接受一例。19 例实际客户端 issue/check 函数检查：17 个绑定错误拒绝 compiled；合法匹配通过，域通配下改 tenant label 也通过。8 个既有 binding/scope 单元测试通过。

这明确区分三个位置：注册声明一致性 helper、客户端 HMAC 选路、引擎内 PSTP 发布。前者没有接入 live endpoint；binding 失败仍可走 raw；`tenant_id=*` 要求上游应用负责用户认证和域成员授权。不能据此声称已经实现公共鉴权网关。

若同样的字节、hash、合法签名和 shared 标签被赋予错误的保密含义，现有检查输入无法区分这种语义错误。再跑 GPU 的行为等价验证也不能证明内容可公开。该问题应由明确的可信运营者边界和真实反例说明；不临时发明未验证的保密分类器。P4 仍为缓存状态授权，不含时序信道防御。

## 3. 原 RULER CI：数值可复现，解释需分清总体

在同一 30-session 冻结 RULER 范围上，原三模型估计及各自区间均从请求重算一致：Qwen 86.64%、Mistral 87.41%、Llama 85.97%。宏平均 86.67%，原 95% 区间 [86.44,86.90] 可复现。

原算法固定三模型，对每模型独立抽进程，再在每个重复里独立抽 session；没有重采样模型。固定三模型平均值的区间本来不要求覆盖三个分量的范围，因此“窄于模型差异”本身不是算术错误。但是同一 30 个来源跨模型、跨重复反复出现，原抽样没有同步保留它们的相关性；每模型 90 个 process-session 组合不是 90 个独立来源。

新增明确标注为事后敏感性分析：seed=20261018，10,000 次，共同抽取 30 个 session ID，并让这份来源抽样贯穿三模型和全部进程；再抽模型内进程，保留 session 内九个未来轮次。宏平均不变，95% 区间为 **[86.3204,86.9911]%**。这增加有限共同范围内的统计可信度，不证明非 RULER 或任意新模型的泛化。原结果完整保留，不静默换区间。

## 4. 92.90% 与 92.62%：不同工作点，另发现一个计时表述问题

- 92.9007%：同路径 D0/D1/D2，5 次进程、每次 450 个 future 请求；D0/D2 业务 mean TTFT=2742.826/194.722 ms；500ms E2E goodput=0.066412/1.427519 req/s。
- 92.62%：独立 service-locality，25 tenants/template、80% calibrated open-arrival load、3 次进程；业务 mean TTFT 的跨进程聚合为 852.354/62.908 ms；500ms goodput=0.172668/0.830651 req/s。

生成代码还揭示一处应修正的旧报告措辞：第一组的 `mean_ttft_ms` 是业务请求 TTFT，**并未把 registration wall 加进 TTFT 均值**；registration wall 加在 `end_to_end_slo_goodput_rps` 的时间分母里。不能把“完整计费的 goodput”扩写成“完整计费的 92.90% TTFT”。本轮没有将这种表述替代实测；原样本复测将分别保留完整 wall 与组件均值。

## 5. Fig.5：从原输入重算，而非只核对显示文件

取回六个 Qwen 原 cell 的计时字段投影及 summary，保留每份完整原文件 SHA、字节数和 mtime。用原 seed=27020、10,000 次层次 bootstrap 重算四个 SLO 桶。500ms 点：

- Raw=0.172667764，ContractKV=0.830651232 req/s。
- 绝对增量=0.657983469 req/s，95% CI=[0.538943295,0.765225192]。
- 比值=4.810690862，95% CI=[2.847508685,12.606992697]。

均与存档结果一致。方法为成对抽进程编号、每个 policy 内独立抽 template/tenant session、保留其全部轮次，固定各实际 cell wall。它不是将 raw/compiled 的 template/session 同步重采样，也不覆盖未观察负载点的容量不确定性。绝对增量宜作为主要解释，比值区间较宽必须保留。

## 决策台账与文件

1. 先把原数据真实复算，避免为写作方便把独立实验当成原 Table III 的完整成本替代。
2. 统计相关性用额外、标明事后的 CPU 敏感性分析处理；不改原结果文件。
3. GPU 仅计划用于仍缺实测计时的原协议复测，不新增第五项算法或另一任务矩阵。
4. GPU 有其他任务时等待；用户已明确选择此安排。
5. 先前拟定的正文调整仅保存在 `pending_text_changes_after_experiments.patch`，正文已恢复本轮开始时的交付版，未生成新 PDF。
6. 本轮恢复/投影 37 份现存文件，全部有 SHA；新增注册测试、RULER/Goodput 统计重放及输入核对均是 CPU 工作。

入口：`scripts/tsc_revision_remaining_stats_audit_v1.py`；输出目录 `results/tsc_revision_remaining_audit_20261018/`。新计时方案位于 `results/tsc_tableIII_fullcost_replay_20261018/`。只有真实 GPU 矩阵完成且费用覆盖核查通过后，才将其标为完整零 slack 补测完成。
