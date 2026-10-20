# ContractKV：精确行为作用域修复与独立验证总报告

本轮先修代码，再做预注册对照；不修改论文或 Response Letter。旧 27 单元、36 次 compiled 掉分和全部输出差异保留。本文数值仅来自本轮实际执行和独立复算；不会把旧 Deployment 的高 Goodput 认领为新严格入口的结果。

**本轮判断：两项准入修复已通过独立验证，完整服务收益仍有明显条件。** 严格入口的84条独立compiled配对均与对应Raw的Token IDs/EOS一致、任务分数无下降；实际前缀和Raw见证绑定也全部核验通过。完整wall吞吐为Qwen **1.027×**、Mistral **0.987×**，因此不能宣布“严格保持与高服务加速已经同时全面解决”。18个fresh-server单元、912个业务请求及全部失败工作已完成并保留，预定矩阵结束后停止GPU。

## 1. 需要修复的边界，以及没有失效的机制

旧 Session 每组 72 个对象/RPC（24×3 重复）仅对应 3 条 canonical prompt，绝不是 72 条独立 prompt。对六个真实来源枚举 8 tenant×9 turn，稳定文本各只有 1 种，完整 L3 输入各有 72 种；旧 3,456 次 compiled 的实际稳定 Token 前缀全部匹配证书。模板物理复用和资格摊销证据成立。

需要补齐的是另外两个判断：部署 compiled 见证不能充当具体请求的 Raw 等价见证；旧 admit 的保存 plan 自比不能替代对实际派发前缀的带内校验。前缀字节相同并不能推出重排前后的整个生成行为相同。旧 doc107 的 36 个下降来自 6 个条件，在两策略×三重复中复现；保留官方 >0.03 下降判定。

## 2. 实际代码修复

- `contractkv_exact_behavior.py`：控制器内部区分 `RAW_QUERY` 与 `COMPILED_DEPLOYMENT`，将完整 Raw/Candidate Prompt IDs、模型/运行时/生成设置、授权域/epoch、Raw 输出和 EOS、实际证书/提交边界绑定为精确行为记录。
- `tsc_behavior_scope_protocol_v2.py`：同时要求原有模板授权绑定和精确 Raw 行为记录；对实际 tokenizer Candidate IDs 按证书边界重新计算原有稳定前缀哈希。没有证据、后缀变更、签名/epoch/授权不符均不得进入 compiled。
- `tsc_behavior_scope_client_v3.py`：首次业务是实际授权 Raw 请求并记录见证；候选只在私有 namespace 自由生成。Raw/候选 IDs 与 EOS 一致后，复用既有单次 Token/EOS verifier 和 PSTP；失败保留 Raw，只有 PASS 发布共享候选前缀。
- 唯一输入不投入候选生成/认证；实际重复输入才复用精确资格。所有 Raw、fallback、private reference、verifier、compiled 仍走统一授权缓存入口。CALC、PSTP、Raw 0.0625 / Candidate/EOS 0.125 floor、任务评分均未放宽。

模板身份与物理前缀可保持共享；完整行为资格随精确输入数 U 增长。此修复没有证明任意动态后缀均可由一次模板 Raw 认证覆盖，也没有新建第五项算法贡献。

## 3. 冻结协议和统计单位

开发：两个新 HotpotQA（doc40/doc35）和一个新 RepoBench；独立：doc80/doc122/doc61 和 SkunkworksAI/BakLLaVA。从既有池按冻结 seed:source 哈希及容量选取，排除所有旧/预留来源；gold 不参与选样、裁剪或在线准入。独立四来源均保留原始文本，common16K、完整问题和代码格式；预算 QA128、Repo384，temperature0/seed14014。

每来源两条模型可见精确条件 `(tenant00,turn1)`、`(tenant01,turn1)`；开发各访问4次，独立各8次。调用序号不进入 Prompt，原 tenant/turn TOOL_OBS 不删除、不合并。授权表支持8个身份，本轮实际活跃2个，不声称8路GPU并发。按访问轮次→固定来源→两条件轮转；三臂 Raw/Deployment/Strict-exact 使用同一内容、顺序、授权共享关系和同模型同物理GPU。

独立三臂×两模型×两 fresh-process 重复=12 cells、768业务；加开发共18 cells、912业务。Repo继承两模型已有L0，没有借本轮解禁；Llama不在本轮新协议范围。冷在线时钟在准备前开始，含首次Raw见证、私有候选、成功/失败认证、绑定、客户端等待及最终排空；模型加载另记，不含在服务 wall 中。零slack，但本轮是闭环积压与固定轮转，不是开放到达SLO容量实验。

## 4. 开发结果（不能代替独立结果）

| 模型 | 路径 | 业务/compiled | 完整wall(s) | 相对Raw吞吐 | 认证RPC | Controller(s) |
| --- | --- | --- | --- | --- | --- | --- |
| Qwen3-8B | Raw-authorized | 24/0 | 80.307 | 1.000× | 0 | 0.000 |
| Qwen3-8B | Deployment | 24/16 | 52.316 | 1.535× | 2 | 21.271 |
| Qwen3-8B | Strict-exact | 24/12 | 81.637 | 0.984× | 4 | 35.028 |
| Mistral-7B-Instruct-v0.3 | Raw-authorized | 24/0 | 145.834 | 1.000× | 0 | 0.000 |
| Mistral-7B-Instruct-v0.3 | Deployment | 24/16 | 91.337 | 1.597× | 2 | 23.033 |
| Mistral-7B-Instruct-v0.3 | Strict-exact | 24/12 | 114.905 | 1.269× | 4 | 22.872 |

两模型各12严格compiled配对，ID/EOS差异与掉分均为0，且这24个Raw参考分数全部>0。四次访问时Qwen略未回本，不能写成全线收益；Mistral已回本。是否进入独立阶段只按事前固定八次访问成本屏幕与行为/物理门槛判断。开发原包217成员、本地复算所有值完全一致。

## 5. 独立完整成本结果

| 模型 | 路径 | 业务/compiled | 完整wall(s) | 相对Raw吞吐 | RPC | Controller(s) | 含认证新Prefill |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Qwen3-8B | Raw-authorized | 128/0 | 422.135 | 1.000× | 0 | 0.000 | 1108512 |
| Qwen3-8B | Deployment | 128/96 | 322.216 | 1.310× | 6 | 48.050 | 622618 |
| Qwen3-8B | Strict-exact | 128/56 | 410.915 | 1.027× | 8 | 36.467 | 983464 |
| Mistral-7B-Instruct-v0.3 | Raw-authorized | 128/0 | 517.612 | 1.000× | 0 | 0.000 | 1276160 |
| Mistral-7B-Instruct-v0.3 | Deployment | 128/64 | 386.717 | 1.338× | 4 | 39.722 | 713832 |
| Mistral-7B-Instruct-v0.3 | Strict-exact | 128/28 | 524.206 | 0.987× | 4 | 19.070 | 1240236 |

上表吞吐比=相同业务量的Raw完整wall÷对应完整wall；包含全部失败费用。Controller仅指每次注册完整工作，首次Raw已计业务；不能把其差额当纯GPU验证成本。Prefill是引擎实际初始新增Token计数，含私有参考和验证，不换算为GPU时间。

| 严格模型 | compiled/全部业务 | compiled/后续访问（access>0） |
| --- | --- | --- |
| Qwen3-8B | 56/128 (43.75%) | 56/112 (50.00%) |
| Mistral-7B-Instruct-v0.3 | 28/128 (21.88%) | 28/112 (25.00%) |

| 模型 | 路径 | 重复1吞吐比 | 重复2吞吐比 |
| --- | --- | --- | --- |
| Qwen3-8B | Deployment | 1.309× | 1.311× |
| Qwen3-8B | Strict-exact | 1.023× | 1.032× |
| Mistral-7B-Instruct-v0.3 | Deployment | 1.336× | 1.341× |
| Mistral-7B-Instruct-v0.3 | Strict-exact | 0.982× | 0.993× |

| 模型 | 路径 | Mean/P95/P99 readiness TTFT(ms) |
| --- | --- | --- |
| Qwen3-8B | Raw-authorized | 2462.1 / 4345.2 / 4374.8 |
| Qwen3-8B | Deployment | 1656.1 / 3096.7 / 20442.8 |
| Qwen3-8B | Strict-exact | 2373.1 / 4875.6 / 10475.0 |
| Mistral-7B-Instruct-v0.3 | Raw-authorized | 2788.7 / 4764.2 / 4785.8 |
| Mistral-7B-Instruct-v0.3 | Deployment | 1811.1 / 2262.6 / 15854.2 |
| Mistral-7B-Instruct-v0.3 | Strict-exact | 2821.7 / 4792.9 / 6469.6 |

Readiness从前一个业务完成到本请求首Token计时，包含期间同步资格等待；首请求从服务epoch计时。两次进程重复与四个来源不足以支持普遍显著性、生产容量或通用p99保证；逐重复与来源表全部给出。

### 5.1 为什么Qwen只有小幅收益、Mistral仍未回本

| 模型 | 业务HTTP累计节省(s) | 新增完整注册Controller(s) | 其它完整路径增量(s) | 实际完整wall净节省(s) |
| --- | --- | --- | --- | --- |
| Qwen3-8B | 53.462 | 36.467 | 5.775 | 11.220 |
| Mistral-7B | 14.608 | 19.070 | 2.132 | −6.594 |

这些是实际时钟的描述性分解，四列严格闭合；业务HTTP包含生成、decode与传输，不能把它称作纯GPU prefill节省。Mistral的业务节省在扣除其它准备开销之前就不足以覆盖注册Controller，因此不能仅凭“减少一点CPU准备”宣称已能大幅加速。

严格入口的失败漏斗（两次重复合计）如下，未调门槛、未重复试档：

| 模型 | Raw/候选自由生成不同 | Raw完整Token/EOS证据缺失或低于既有floor | 通过/尝试的精确作用域 |
| --- | --- | --- | --- |
| Qwen | 2 | 2 | 8/12 |
| Mistral | 4 | 4 | 4/12 |

相同失败条件在两个重复中出现，不能当成更多独立来源。拒绝范围确实减少可复用业务；其中部分Deployment输出分数反而更高，拒绝代表缺少严格Raw行为一致证据，不代表已证明回答一定变差。

## 6. 行为保持与绝对任务效用

| 模型 | 路径 | compiled配对 | compiled ID/EOS变/降分 | 全路由ID/EOS变/降分/升分 | compiled中Raw分数>0 |
| --- | --- | --- | --- | --- | --- |
| Qwen3-8B | Deployment | 96 | 32 / 0 | 32 / 0 / 0 | 96 |
| Qwen3-8B | Strict-exact | 56 | 0 / 0 | 0 / 0 / 0 | 56 |
| Mistral-7B-Instruct-v0.3 | Deployment | 64 | 32 / 0 | 46 / 0 / 32 | 64 |
| Mistral-7B-Instruct-v0.3 | Strict-exact | 28 | 0 / 0 | 2 / 0 / 0 | 28 |

分数变化按固定>0.03升/降分，两者之间为无实质变化；输出差异即使升分也不算严格行为认证成功。Raw等价亦不意味着答案正确。以下为每个独立来源的官方任务分数，不把均分提高用于删除单请求下降：

特别是Mistral doc80：Deployment的32个配对从Raw均分0.08333提高到0.50000，同时32次ID变化。严格路径没有用gold挑选这类有利变化，而是按同一Raw行为规则回退。另有Strict全路由2次ID变化，均为doc122的L0、tenant00、access1（每重复一次）；实际Prompt IDs相同，分数变化约+0.00879，未越固定阈值。两种输出均在该精确输入的Raw重复中出现，但这不能证明策略执行上下文完全无影响。完整文本、IDs、首次分歧位置保存在diagnostics，不归为compiled违规，也不从全路由记录删除。

| 模型 | 来源 | 路径 | compiled/业务 | Raw均分 | 路径均分 | 下降/上升/ID变化 |
| --- | --- | --- | --- | --- | --- | --- |
| Qwen3-8B | LongBench:hotpotqa:hotpotqa:doc:122 | Deployment | 32/32 | 0.09302 | 0.09091 | 0/0/32 |
| Qwen3-8B | LongBench:hotpotqa:hotpotqa:doc:122 | Strict-exact | 0/32 | 0.09302 | 0.09302 | 0/0/0 |
| Qwen3-8B | LongBench:hotpotqa:hotpotqa:doc:61 | Deployment | 32/32 | 0.50000 | 0.50000 | 0/0/0 |
| Qwen3-8B | LongBench:hotpotqa:hotpotqa:doc:61 | Strict-exact | 28/32 | 0.50000 | 0.50000 | 0/0/0 |
| Qwen3-8B | LongBench:hotpotqa:hotpotqa:doc:80 | Deployment | 32/32 | 0.33333 | 0.33333 | 0/0/0 |
| Qwen3-8B | LongBench:hotpotqa:hotpotqa:doc:80 | Strict-exact | 28/32 | 0.33333 | 0.33333 | 0/0/0 |
| Qwen3-8B | RepoBench:python_v1.1:SkunkworksAI/BakLLaVA | Deployment | 0/32 | 0.02000 | 0.02000 | 0/0/0 |
| Qwen3-8B | RepoBench:python_v1.1:SkunkworksAI/BakLLaVA | Strict-exact | 0/32 | 0.02000 | 0.02000 | 0/0/0 |
| Mistral-7B-Instruct-v0.3 | LongBench:hotpotqa:hotpotqa:doc:122 | Deployment | 0/32 | 0.07747 | 0.08132 | 0/0/14 |
| Mistral-7B-Instruct-v0.3 | LongBench:hotpotqa:hotpotqa:doc:122 | Strict-exact | 0/32 | 0.07747 | 0.07802 | 0/0/2 |
| Mistral-7B-Instruct-v0.3 | LongBench:hotpotqa:hotpotqa:doc:61 | Deployment | 32/32 | 0.14286 | 0.14286 | 0/0/0 |
| Mistral-7B-Instruct-v0.3 | LongBench:hotpotqa:hotpotqa:doc:61 | Strict-exact | 28/32 | 0.14286 | 0.14286 | 0/0/0 |
| Mistral-7B-Instruct-v0.3 | LongBench:hotpotqa:hotpotqa:doc:80 | Deployment | 32/32 | 0.08333 | 0.50000 | 0/32/32 |
| Mistral-7B-Instruct-v0.3 | LongBench:hotpotqa:hotpotqa:doc:80 | Strict-exact | 0/32 | 0.08333 | 0.08333 | 0/0/0 |
| Mistral-7B-Instruct-v0.3 | RepoBench:python_v1.1:SkunkworksAI/BakLLaVA | Deployment | 0/32 | 0.01000 | 0.01000 | 0/0/0 |
| Mistral-7B-Instruct-v0.3 | RepoBench:python_v1.1:SkunkworksAI/BakLLaVA | Strict-exact | 0/32 | 0.01000 | 0.01000 | 0/0/0 |

## 7. 资格、物理状态与故障保留

开发实际物理命中：{"Deployment:partial": 7, "Deployment:full": 25, "Strict-exact:zero": 2, "Strict-exact:full": 17, "Strict-exact:partial": 5}；独立：{"Deployment:zero": 30, "Deployment:full": 86, "Deployment:partial": 44, "Strict-exact:zero": 42, "Strict-exact:full": 42}。资格不是完整驻留证明；零/部分命中仍全部计费。所有合格证书的点状margin/EOS与16-token提交边界均独立核验，共34条PASS记录。

独立严格编译的42次零命中全部来自每对请求中的tenant00（Qwen28、Mistral14），紧随其后的tenant01全部完整命中（Qwen28、Mistral14）。实际前缀IDs与授权共享组均一致，所以没有发现“已获资格未使用/前缀身份对不上”的索引错误。该首个请求冷、第二个请求热的模式与跨来源轮转时稳定前缀未持续驻留一致；尚无专门的pinning/驱逐反事实，不能把提升驻留的潜在收益当成已测结果。若后续单独研究性能，优先检查合法覆盖和真实block驻留，而非放宽Raw/EOS门槛。

逐作用域的完整Controller、验证HTTP、失败HTTP、实际已认证前缀读取量和提交量都在 `final_descriptive_tables_v1.json` 的 registration_costs 保留；成功证书也可能因驻留损失而重新计算。现有PSTP前缀辅助验证允许后续独立行为资格读取已认证稳定前缀，但仍须针对本请求的Raw见证逐项验证。

终止状态完整分层：

| 阶段 | 路由 | finish | 条数 |
| --- | --- | --- | --- |
| development | L0 | stop | 76 |
| development | L0 | length | 12 |
| development | L3 | stop | 56 |
| validation | L0 | stop | 524 |
| validation | L3 | stop | 244 |

v1/v2/v3准备版本未执行GPU：先补实际前缀校验、统一轮转，再修CPU预检日志重名。旧日志/空传输占位和失败保留；v4才实际推理。离线v4分析的单处compact/spaced JSON哈希比较错误由v5窄修复，AST证明其余分析完全一致；有效GPU单元无重跑、无覆盖。完整决策见 `ContractKV_Behavior_Scope_Repair_Decisions_20261020.md`。

费用覆盖逐项核验通过：18个单元共954个实际生成HTTP、34个实际验证HTTP，均与逐请求记录和Native初始prefill事件对应，无未记账GPU请求。29,502,530-byte原包SHA为`96fc6281f0049ba3f374c2be1177d5edd76d6c2144acc2dc1ca10f895e8ac3b2`，379原始成员在本地恢复后全部哈希不变；开发/独立两个阶段的相同v5分析均复算所有JSON值完全一致。826份资源采样覆盖完整原包的两阶段，未见无关GPU任务；23项相关CPU检查通过。前缀篡改负例为CPU检查，不能称作额外的GPU攻击实验。

## 8. 本轮能支持什么，仍不能支持什么

修复后的严格入口把模板授权、实际提交前缀和精确Raw行为证据连接在同一执行链。是否获得性能收益必须按上面各模型、重复及工作集条件判断；原Deployment的服务收益仍只支持其自身语义。旧36个下降、旧3456个compiled配对及本轮结果分别保留，不合并成统一安全率。

精确重复与轮转局部性是声明的服务条件；原384唯一输入/引擎的负载在此严格模式下应Raw，不会凭空获得摊销。此处没有测生产exact-query重复率，没有证明任意动态query/observation的Raw等价，没有解禁Repo或验证Llama新入口，也没有为新严格入口补开放到达Goodput。

统一cache salt/HMAC仍依赖可信入口和正确共享声明。哈希证明身份，不判断内容保密性；可信operator错误标共享仍是信任边界。时序侧信道、硬p99和完整多租户机密性不在本修复保证内。

## 9. 可复核记录

- 规则/输入：`protocol_v3.json`、`input_selection_v1.json`、两个inputs目录。
- 冻结/预检：`development_freeze_v4`、`validation_freeze_v4`、对应实际preflight及Git byte audit。
- 原包：`evidence_development_v1`、`evidence_all_v1`，每成员SHA；本地恢复后原成员未变。
- 复算：`development_analysis_v5.json`、`validation_analysis_v5.json`、`all_local_independent_recompute_v1.json`。
- 完整表：`final_descriptive_tables_v1.json`，含全部逐来源/逐重复/质量/费用。
- 归因与费用核查：`validation_diagnostics_v1.json`、`all_fee_coverage_v1.json`、`validation_conformance_v1.json`。
- 工具：`scripts/tsc_behavior_scope_analysis_v5.py`、`tsc_behavior_scope_conformance_v1.py`、`tsc_behavior_scope_fee_coverage_v1.py`、`tsc_behavior_scope_diagnostics_v1.py`、`tsc_behavior_scope_report_v1.py`。

预定独立单元结束后停止本轮，不新增研究矩阵。正文与Response Letter均未修改。
