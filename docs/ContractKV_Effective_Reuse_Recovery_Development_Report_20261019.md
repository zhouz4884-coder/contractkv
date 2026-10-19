# ContractKV 有效复用恢复：开发实验与目标调整

本轮只处理原系统内的授权接线、无效资格工作与合法候选机会，不修改正文或 Response Letter，不启动新的研究机制。用户提供的新建议已全文核对，以下结论来自本轮实际执行与原包独立复算。

## 1. 当前判断

**授权接线与行为回归通过；降低无效候选准备有效，但新增合法覆盖尚未建立。** 不能将两者合称为性能问题已经解决。

三模型各一个 fresh-server 开发单元完成：540 次全服务业务、60 次新来源候选相关生成，共 600 次。完整服务的 Raw / V5-authorized / Deferred-authorized 每模型各 60 次业务。每个模型内三臂依次共用一个引擎，授权命名空间独立，并非三臂各自 fresh-server 的正式速度比较。诊断 trace 也会增加开销，所列 wall 仅供审计。

完整服务的 360 对 Contract/Raw 输出中，输出 token IDs、finish reason 和任务分数变化均为 0；其中 32 对是 compiled 请求。32 次实际 compiled 绑定检查均通过，32/32 实际原生前缀命中大于零。全部 540 次服务业务的实际引擎 lookup 已与授权 salt 对上。新候选探针另有 8 个严格 PASS，实际自由生成及 Raw 重复均保持一致；8/8 实际命中长度等于提交的完整稳定块长度，累计读取 78,000 个 prefix tokens，不能直接换算为 GPU 时间。拒绝候选零新增共享发布，实际发布记录均能关联到获准认证。

这些是有限来源与运行条件下的观察，不能升级为普遍安全或任意动态输入的行为保证。

## 2. 已做的最小改变

1. 全 V5 的 Raw、L0、fallback、Verifier、compiled 使用统一授权入口。实际 compiled 请求还执行签名证书/请求绑定检查；模型、tokenizer、运行时、生成预算、布局、前缀、授权域与 epoch 在绑定内。内部可信服务端点不等于公共 IAM。
2. Deferred Candidate Preparation：取得真实 Raw 见证后，先执行原有 scope/output 确定性检查；确定拒绝时跳过候选构造及两次 HTTP tokenization。其余请求仍执行原 fine benefit gate、Raw/candidate/EOS margin 与 PSTP。
3. 用预先盲选的两 QA、两 Repo 开发来源检查原 L1/L2/L3。另六验证来源在开发输出出现前已选定，本轮尚未读取其模型输出。

未降低 Raw 0.0625 / candidate 0.125 门槛，未忽略 EOS，未扩大 scope，未新增异步调度、预测网络或证书类型。

## 3. 全服务接线结果

| 模型 | 臂 | 编译未来 / 54 | GPU RPC | 获准 scope | 准备耗时累计 ms | 跳过准备 | 直接完整 wall s |
|---|---|---:|---:|---:|---:|---:|---:|
| Qwen3-8B | Raw-authorized | 0 | 0 | 0 | 0 | 0 | 207.663 |
| Qwen3-8B | V5-authorized | 6 | 3 | 1 | 918.898 | 0 | 212.433 |
| Qwen3-8B | Deferred-authorized | 6 | 3 | 1 | 316.389 | 6 | 210.974 |
| Mistral-7B | Raw-authorized | 0 | 0 | 0 | 0 | 0 | 307.696 |
| Mistral-7B | V5-authorized | 6 | 1 | 1 | 465.809 | 0 | 305.335 |
| Mistral-7B | Deferred-authorized | 6 | 1 | 1 | 71.283 | 5 | 302.485 |
| Llama-3.1-8B | Raw-authorized | 0 | 0 | 0 | 0 | 0 | 236.780 |
| Llama-3.1-8B | V5-authorized | 4 | 1 | 1 | 487.697 | 0 | 237.278 |
| Llama-3.1-8B | Deferred-authorized | 4 | 1 | 1 | 231.854 | 3 | 236.114 |

Deferred 跳过 14 次准备，实际获准资格、RPC 数与编译请求数均保留。准备组件累计从 1,872.404 ms 降至 619.527 ms，下降约 66.9%。这是 CPU/HTTP 准备工作，不能称为 GPU 验证减少 66.9%。

V5 三模型直接 registration 累计 17,840.804 ms；Deferred 为 18,420.733 ms。Deferred 的 registration 本身含延后执行的候选准备，不应再将准备耗时重复相加。不同前序缓存状态、时间漂移及实际 GPU 等待均存在，因此组件与 wall 不能组成可信的因果服务加速倍率。Llama 两项原 pre-reference 经济拒绝在 Deferred 中先表现为同一见证的 scope 拒绝，需保留该判定顺序差异，不能声称每个拒绝原因完全相同。

判断：A1 的执行优化成立、收益幅度有限。它本身不足以支持再开大规模 Goodput 矩阵。

## 4. 新来源 L1/L2/L3 可行性

两个 QA 来源为 LongBench HotpotQA doc185、doc8；两个 Repo 来源为 alexzhou907/DreamPropeller、google-research/semivl。它们是本轮开发来源，不能当独立验证来源。

| 模型 | HotpotQA PASS / 6 | RepoBench PASS / 6 | 满足同档位两来源均严格可用的家族 |
|---|---:|---:|---|
| Qwen3-8B | 3 | 0 | 无 |
| Mistral-7B | 3 | 0 | 无 |
| Llama-3.1-8B | 2 | 0 | 无 |

8 个 PASS 全来自 doc8。该来源 Raw F1 分别为 0.5 / 1.0 / 1.0，获准候选输出保持一致，具有正任务分数；doc185 的 Raw 回答长于原 scope 契约，不能因若干反事实输出相同就改判可共享。Qwen DreamPropeller 三档均在 candidate margin 失败，实际输出也有差异。其余 Repo 主要是原 scope 或 Python 输出契约拒绝，未证明这些拒绝可以安全取消。

两来源均通过是事前门槛，不因本次结果改成一来源通过即可。Mistral/Llama 旧 Repo L0 也缺完整经济标定 profile；单有候选可行性仍不足以部署。**B 当前结论为不解禁，不生成新的生产资格目录。**

## 5. 对首词早停提案的实际诊断

本轮全服务与新来源探针共 22 次实际 RPC：14 PASS、8 FAIL。失败 RPC 累计 32,709.683 ms，其中仅 1 次首词即失败；6 次没有认证前缀读取，另 2 次读取 64 tokens。全部 RPC 的 Raw 全轨迹最小 margin 均不低于 0.125，因此将 Raw 门槛从 0.0625 抬至 0.125 会跳过 **0 次**调用。

失败后剩余 witness 位置 / 未缓存强制输入 token-slot 的代理比例约 0.0163%–0.1228%。这不是 FLOPs 或 GPU 时间上界；没有纯 kernel 费用，不能由该比例预测精确加速。当前完整 forward 已在返回逐位置 trace 前完成。结合旧 F8 与授权回归的 CPU 审计，尚无证据支持“省 80% 验证费用”。

**A2 当前不进入 scheduler / staged-forward 开发。** 不使用 Raw margin 对齐、位移启发式或检查顺序前移冒充确定性 GPU 早停。

## 6. 唯一追加的条件分支：代码元数据格式

Qwen semivl 实际输出回显了 `[CODE_PREFIX:s2]`、文件路径并重写代码。官方 [RepoBench 固定版本构造器](https://github.com/Leolty/repobench/blob/53c1c55ad9e6d97d2b60dd2c9548ed1cd463b6a5/data/utils.py) 将文件路径放在注释元数据中。这支持一次格式对照，但尚未证明标题造成拒绝。

单独冻结 current / clean 两 renderer：仅去掉框架 CODE_PREFIX 标题、将开头 filename 元数据注释化，保留原代码正文和空白、原问题、布局、384-token 预算、评分及全部认证条件。相同两个开发 Repo、三模型各一个 fresh-server，共 60 次生成/36 个候选决定；分开授权命名空间、重新 tokenize、构造前缀和认证。Mistral 采用反向 renderer 顺序；同引擎配对只用于可行性，不作为正式速度比较。48 个实际 tokenizer 形状全部符合共同 16K 窗口，预检回执与源码已在模型执行前发布。

本分支执行状态及最终判断将在本节补充。若仍没有同档位两来源均严格可用的证据，则停止，不再调提示词、增加 stop words、输出裁剪或换源。输入适配仍是声明的 chat-task 变体，不称为完整复现官方 RepoBench-C。

## 7. 保留的失败与独立复算

v1 新接入 wrapper 在启用保真 renderer 前捕获了旧函数引用，使首个 compiled 请求与冻结 Prompt ID hash 不符。原检查及时阻断；两台未完成的 fresh-server 共 154 次业务全部保留。它是本轮新增适配器初始化缺陷，不是通过认证后自由生成变化。v2 只修复安装/引用捕获顺序，并新增实际 wrapper 初始化回归；受影响完整配对 fresh-server 重跑，未改来源、门槛、预算或评分。没有已完成有效单元被重跑或覆盖。

完整原包 SHA256：`7a79ff113855957e696663aeefbe77651be4a48835a89632e4d4679ba52a3fc8`，102,110,848 bytes，1,907 个普通文件，包含 v1 失败现场与 v2 完整执行。取回后在新的恢复目录验证所有成员、两版冻结与实际执行源码，再执行归档分析器：600 业务、完整 summary 与三份 CSV 逐字节一致；复算前后原始成员均未改变。

证据入口：`results/tsc_effective_reuse_recovery_20261019/analysis_development_v1/`、`local_independent_recompute_v1.json`、`early_abort_development_CPU_v1.json`、`development_evidence_package_v1/`。

## 8. 收口原则

先判断是否有真实机制改进，再决定是否消耗独立六来源。RPC 成功率上升不等于业务覆盖上升；Raw 任务质量改善也不等于缓存提高模型能力。若代码格式分支不满足门槛，本轮以授权接线通过、A1 小幅执行优化与覆盖恢复 NO-GO 收口，保留既有严格保真及授权回归证据，不启动名义相同的大矩阵寻找有利结果。
