# Task-Bearing Template Service Validation：第二阶段总报告

GPU矩阵完成时间：2026-10-20T02:57:03+08:00（香港时间）。

本报告仅记录实验，不修改正文或Response Letter。完整27个fresh-server单元已结束，原始日志和全部不利结果保留；本地独立复算通过后才生成本报告。

**总体判断：服务性能、物理复用与模板摊销证据正面，严格Raw行为保持未成立。** 本轮支持原Service-Template服务对象的经济性，不能将其包装为“全部输出等价、全部请求零退化”的新主结果。

- 正式27单元、10,368次业务请求全部正常返回；GPU矩阵实际耗时8小时10分39秒，现有GPU进程已释放。另有156次开发生成和160次Raw-only标定，均独立保留。
- Template相对Raw的绝对SLO Goodput：Qwen普通负载0.052479→0.154272 req/s，高负载0.014528→0.123993 req/s；Mistral普通负载0.035328→0.086824 req/s。三进程配对区间和六来源组成敏感性区间均为正值。负载按开发Raw速率归一，不能将这些点的倍率解释为最大SLO容量提升。
- 同条件Session→Template的认证对象及RPC由每单元24→3；Qwen累计Controller工作降低32.8%，Mistral降低24.9%。Template与Session的服务表现接近，主要新增价值是资格费用摊销。
- 已编译3,456个配对中有1,178次输出ID/终止变化，36次分数下降超过冻结阈值0.03；全部下降集中于Mistral的一个QA来源、6个请求条件，重复3次并在两策略中各出现一次。全部事件保留。

## 1. 科学问题与实际保证

在固定问题、稳定文档及明确授权重复使用的服务对象中，Session与Template认证是否在同一Serving Stack、同一缓存授权组和完整冷服务时钟下，保留实际任务质量并改善资格经济性与SLO表现？

见证为原部署模式的compiled-path attestation：它校验该部署路径，不是任意未来请求的Raw等价证明。Raw/Compiled实际输出IDs、终止和任务分数由独立业务配对测量。全部内容来自真实HotpotQA/RepoBench任务；tenant/turn元数据和访问局部性为公开的受控协议，不能当生产trace或生产重复率测量。

## 2. P0与P1：冻结、开发、拒绝及授权闭环

新开发4来源、正式6来源，排除729历史/先前预留来源；所有新来源之间及与历史未发现完全相同的任务上下文，不能据此宣称语义独立。共同16K输入保留完整问题、CODE_PREFIX及原空白；超窗可选上下文按与gold位置无关的首尾规则裁剪，完整ledger保留。

三模型各52次开发生成，共156次。质量、物理命中及费用空间按事前双来源门槛判断，以下是家族级目录，并未根据正式结果解禁：

| 模型 | 通过开发的家族 | 开发attestation获准配对 | 全部开发>0.03掉分 | 正式单元 |
|---|---|---|---|---|
| Qwen3-8B | HotpotQA | 12 | 0 | 18 |
| Mistral-7B-Instruct-v0.3 | HotpotQA | 18 | 6 | 9 |
| Llama-3.1-8B-Instruct | 无 | 12 | 6 | 0 |

Mistral的Repo与Llama的QA开发掉分均未删除；部署自路径认证通过不能代替Raw任务质量资格。所有Repo家族在正式服务中保持Raw fallback，Llama不进入正式矩阵。

三臂业务均经统一授权入口使用相同的**授权分组与共享关系**；Session只改变证书对象及tenant绑定，不剥夺物理共享。canary在controller-private组生成，Session与Template均允许合法的canary缓存和certified-prefix读取。

需区分逻辑分组与salt字节：冻结代码为每个fresh-server单元创建新的CacheAuthority随机密钥，HMAC所得salt字符串因此不同。CPU审计逐项检查27单元的实际wire字段，确认每单元均为6个业务组、每组64请求和8个授权tenant，同一来源当且仅当使用同一salt，三臂共享关系完全相同；canary组与业务组分离。这里没有跨独立引擎复用KV，也没有宣称各fresh-server使用同一长期密钥。详见`formal_cache_partition_audit_v1.json`；初次诊断中“跨服务器salt字节相等”为false的记录原样保留。

## 3. Raw-only标定与完整服务时钟

| 模型 | Raw-only速率 req/s | 正式负载 req/s | TTFT/E2E SLO ms |
|---|---|---|---|
| Qwen3-8B | 0.315908 | 0.252726, 0.315908 | 10500/13000 |
| Mistral-7B-Instruct-v0.3 | 0.241822 | 0.193457 | 11000/18000 |

速率与SLO仅由开发源Raw-only两个fresh-server、各80成功请求确定；阈值为1.5×本征请求p95、500ms向上取整、最低1500ms。没有用正式Contract结果选SLO或负载。

到达为相同标记Poisson轨迹：每模板两段32请求，共8tenant identity×8次业务调用，同一模板的固定问题重复；不是8个并发GPU请求。客户端与GPU并发均为2。同一模型/重复的三臂在同一物理GPU执行，三重复Latin-square臂序。所有server ready后才开始测量，整波结束前不加载新模型。

生成预算固定为HotpotQA 128、RepoBench 384 tokens；原包保留每次实际终止原因，达到预算上限的输出也完整保留。ID/终止比较使用实际输出IDs与finish_reason，不将有限预算的结果外推为任意长输出保证。

本次实际10,368次业务输出的finish_reason均为`stop`，没有达到输出token上限的事件。因此本轮质量差异不能归因于被128/384预算截断；这仍不构成更长输出的安全保证。

全局服务epoch在准备与注册前开始，注册完成后不重置到达时钟。TTFT/E2E从原计划到达计算；完整wall包含准备、canary、注册、失败、绑定、业务与最终排空。模型/interpreter启动在client epoch外，单独保留日志。完整wall倍率不是固定到达条件下的最大容量加速。

## 4. P2：完整正式服务结果

| 模型/负载 | 策略 | SLO达标/1152 | 绝对Goodput req/s | Mean到达TTFT ms | p99范围 ms | 编译业务/1152 |
|---|---|---|---|---|---|---|
| Mistral-7B-Instruct-v0.3/common80 | Raw-authorized | 220 | 0.035328 | 55185.3 | [91298.2, 193185.7] | 0 |
| Mistral-7B-Instruct-v0.3/common80 | Session-qualified | 507 | 0.085634 | 26356.7 | [85588.6, 118196.3] | 576 |
| Mistral-7B-Instruct-v0.3/common80 | Template-qualified | 514 | 0.086824 | 25825.7 | [87220.1, 120272.9] | 576 |
| Qwen3-8B/common80 | Raw-authorized | 252 | 0.052479 | 41233.1 | [51744.1, 167299.0] | 0 |
| Qwen3-8B/common80 | Session-qualified | 686 | 0.151155 | 11795.2 | [39752.0, 59601.8] | 576 |
| Qwen3-8B/common80 | Template-qualified | 700 | 0.154272 | 10954.1 | [38066.7, 48307.1] | 576 |
| Qwen3-8B/high100 | Raw-authorized | 64 | 0.014528 | 118416.5 | [192186.8, 382180.2] | 0 |
| Qwen3-8B/high100 | Session-qualified | 441 | 0.120409 | 28376.7 | [76214.5, 106871.5] | 576 |
| Qwen3-8B/high100 | Template-qualified | 454 | 0.123993 | 26495.0 | [70400.6, 106251.1] | 576 |

以上按三个独立fresh-process汇总；Goodput为达标总数/完整wall总和。Mean按三个等规模单元汇总，p99保留重复范围，不承诺所有模型/来源尾延迟均下降。

本次9组匹配的模型/负载/重复中，Template的全局p99到达TTFT均低于对应Raw；仍不能把此有限结果外推为任意工作集、到达或Source的尾延迟保证。Template相对Session的增量较小，Mistral的来源敏感性区间跨零，不作为普遍Goodput优势主张。

本轮部分实际输出内容及长度也发生变化。因此端到端时延差额是整体服务观察，不能全部归为纯GPU prefill时间；真实新prefill减少由引擎计数另行验证。

### 同条件资格经济性与实际物理工作

| 模型/负载 | 策略 | 注册对象/真实RPC | Controller ms/business | 业务新prefill | canary+验证额外新prefill |
|---|---|---|---|---|---|
| Mistral-7B-Instruct-v0.3/common80 | Raw-authorized | 0/0 | 0.000 | 16316464 | 0 |
| Mistral-7B-Instruct-v0.3/common80 | Session-qualified | 72/72 | 175.510 | 9299888 | 235152 |
| Mistral-7B-Instruct-v0.3/common80 | Template-qualified | 9/9 | 131.876 | 9295360 | 227718 |
| Qwen3-8B/common80 | Raw-authorized | 0/0 | 0.000 | 13256384 | 0 |
| Qwen3-8B/common80 | Session-qualified | 72/72 | 197.955 | 6866352 | 215136 |
| Qwen3-8B/common80 | Template-qualified | 9/9 | 132.971 | 6851968 | 207660 |
| Qwen3-8B/high100 | Raw-authorized | 0/0 | 0.000 | 13256384 | 0 |
| Qwen3-8B/high100 | Session-qualified | 72/72 | 197.963 | 6866352 | 215136 |
| Qwen3-8B/high100 | Template-qualified | 9/9 | 132.944 | 6851968 | 207660 |

每个正式单元共有六模板，其中三个QA模板获前瞻资格；因此计划注册对象为Session24、Template3，8×对象摊销，不能照搬旧25tenant实验的25×数字。实际RPC、拒绝和费用如表。对象数减少不意味着GPU时间同比减少；两路都可读取合法已认证prefix。新prefill为真实初始引擎hit与prompt之差，不换算为GPU kernel时间。

将canary与验证额外新prefill计入后，Template相对Raw的新prefill总量减少Qwen46.75%、Mistral41.64%。3,456次编译业务实际命中分类为3,363次完整命中、1次部分命中、92次零命中；已发资格不能当作KV始终驻留的证明，零命中请求仍保留在费用与时延中。

### 配对增量与不确定性

| 模型/负载 | 比较 | Goodput增量 req/s | 三进程配对CI95 | 来源条件敏感性CI95 | 去一来源范围 |
|---|---|---|---|---|---|
| Mistral-7B-Instruct-v0.3/common80 | Session-qualified − Raw-authorized | 0.050307 | [0.045493, 0.057990] | [0.012602, 0.091532] | [0.028614, 0.051871] |
| Mistral-7B-Instruct-v0.3/common80 | Template-qualified − Raw-authorized | 0.051496 | [0.047335, 0.059079] | [0.014632, 0.092920] | [0.029801, 0.052215] |
| Mistral-7B-Instruct-v0.3/common80 | Template-qualified − Session-qualified | 0.001189 | [0.000008, 0.002540] | [-0.000329, 0.003044] | [0.000344, 0.001356] |
| Qwen3-8B/common80 | Session-qualified − Raw-authorized | 0.098676 | [0.075233, 0.137887] | [0.042140, 0.161686] | [0.062775, 0.096076] |
| Qwen3-8B/common80 | Template-qualified − Raw-authorized | 0.101793 | [0.075233, 0.144282] | [0.044806, 0.165207] | [0.065443, 0.098970] |
| Qwen3-8B/common80 | Template-qualified − Session-qualified | 0.003117 | [2.4706e-7, 0.00639495] | [0.002006, 0.004229] | [0.002229, 0.002894] |
| Qwen3-8B/high100 | Session-qualified − Raw-authorized | 0.105881 | [0.088966, 0.129082] | [0.033548, 0.176373] | [0.070656, 0.110191] |
| Qwen3-8B/high100 | Template-qualified − Raw-authorized | 0.109465 | [0.094770, 0.130642] | [0.031506, 0.179431] | [0.073957, 0.113501] |
| Qwen3-8B/high100 | Template-qualified − Session-qualified | 0.003584 | [0.001559, 0.005804] | [0.000566, 0.007149] | [0.001664, 0.003583] |

仅有六个来源簇和三个独立进程。来源bootstrap/去一来源保持已观测整单元wall不变，属于组成敏感性，不能当重新改变工作负载后的反事实性能区间。tenant重复请求不当独立安全样本。区间跨零时，不把点估计写成稳健推广增益。

## 5. Raw配对质量与行为

| 模型 | 策略 | 子集 | 配对数 | ID/终止变化 | >0.03上升 | >0.03下降 | Raw正任务分数 |
|---|---|---|---|---|---|---|---|
| Mistral-7B-Instruct-v0.3 | Session-qualified | all | 1152 | 384 | 193 | 25 | 1152 |
| Mistral-7B-Instruct-v0.3 | Session-qualified | compiled | 576 | 376 | 192 | 18 | 576 |
| Mistral-7B-Instruct-v0.3 | Template-qualified | all | 1152 | 379 | 192 | 21 | 1152 |
| Mistral-7B-Instruct-v0.3 | Template-qualified | compiled | 576 | 376 | 192 | 18 | 576 |
| Qwen3-8B | Session-qualified | all | 2304 | 213 | 213 | 0 | 2304 |
| Qwen3-8B | Session-qualified | compiled | 1152 | 213 | 213 | 0 | 1152 |
| Qwen3-8B | Template-qualified | all | 2304 | 213 | 213 | 0 | 2304 |
| Qwen3-8B | Template-qualified | compiled | 1152 | 213 | 213 | 0 | 1152 |

各家族的绝对任务分数如下，仅作描述性汇总。HotpotQA与RepoBench评分不同，分别报告；输出一致性不等于回答正确。

| 模型 | 策略 | 任务家族 | 配对数 | Raw平均任务分数 | 策略平均任务分数 |
|---|---|---|---|---|---|
| Mistral-7B-Instruct-v0.3 | Session-qualified | HotpotQA | 576 | 0.4942 | 0.7222 |
| Mistral-7B-Instruct-v0.3 | Session-qualified | RepoBench | 576 | 0.2575 | 0.2571 |
| Mistral-7B-Instruct-v0.3 | Template-qualified | HotpotQA | 576 | 0.4942 | 0.7222 |
| Mistral-7B-Instruct-v0.3 | Template-qualified | RepoBench | 576 | 0.2575 | 0.2573 |
| Qwen3-8B | Session-qualified | HotpotQA | 1152 | 0.2225 | 0.2944 |
| Qwen3-8B | Session-qualified | RepoBench | 1152 | 0.1100 | 0.1100 |
| Qwen3-8B | Template-qualified | HotpotQA | 1152 | 0.2225 | 0.2944 |
| Qwen3-8B | Template-qualified | RepoBench | 1152 | 0.1100 | 0.1100 |

**本轮未建立编译子集零任务退化。** 所有已获准请求中的下降均保留在配对CSV，应按来源及重复定位；不能用速度或仅部署自路径认证成功掩盖。

全路由下降包含Raw fallback，不能删除或自动归因于编译。基线自身三重复与来源级记录可用于区分背景变化；不能仅因路由L0就宣布完全无策略关联。

### 5.1 来源级任务效用与分歧

两策略在下列QA来源的均分相同，表中列出Template，Session完整数据在CSV中。Qwen每来源384个配对（两负载×三重复），Mistral每来源192个配对；这些重复调用不能当作相同数量的独立问题。

| 模型 | QA来源 | Raw平均F1 | Template平均F1 | Template >0.03下降 |
|---|---|---:|---:|---:|
| Qwen | doc107 | 0.09756 | 0.09756 | 0/384 |
| Qwen | doc64 | 0.28429 | 0.50000 | 0/384 |
| Qwen | doc22 | 0.28571 | 0.28571 | 0/384 |
| Mistral | doc107 | 0.14921 | 0.16667 | 18/192 |
| Mistral | doc64 | 0.33333 | 1.00000 | 0/192 |
| Mistral | doc22 | 1.00000 | 1.00000 | 0/192 |

“Raw正任务分数”仅表示F1/相似度大于零，包含部分匹配，不能解释为答案完全正确。doc107的低绝对F1必须与其输出一致性、服务收益一起看。总体均分上升不能抵消或删除单请求下降。

### 5.2 36次编译下降的CPU归因

全部编译下降来自Mistral doc107的tenant00–tenant05、turn6，6个不同请求条件×3个重复×2策略，共36次。对应Raw输入与输出在这些条件的三重复中稳定；编译输出全部匹配注册时的compiled见证，均有16,000-token Native前缀命中。每例首次输出ID分歧位于零基位置7，正常`stop`，没有预算截断。这组证据指向注册见证向Raw质量的作用域转移边界，未发现本轮输入漂移、KV未命中或见证执行不一致来解释这些事件。

一个完整例子：标准答案为`Juan Rulfo`。Raw输出称John le Carré先出生，同时给出1931年与Juan Rulfo的1917年生日；compiled也选择John le Carré并给出同样日期，但措辞更长。两者的主要人物选择均错误；Raw为37 tokens、F1=0.2000，compiled为41 tokens、F1=0.1667，差值−0.0333。官方评分、0.03阈值均不改变，36次下降全部保留。不能将其改称零退化，也不能因为来源均分上升就否认该失败。

同样要保留正向变化：Qwen doc64有426个编译配对（两策略合计）分数上升，Mistral doc64有384个；这些改善不构成严格行为等价成功，也不建立缓存机制普遍提高回答正确率的结论。

### 5.3 Raw/L0差异

另外10次下降来自Mistral的Wonder3D Raw/L0路由，均为0.09→0.05，差值−0.04。共有11个L0输出差异，实际Prompt IDs在配对中相同；10/11个策略输出与该输入在另一次Raw执行中的输出相同，原Raw重复中也存在变化。这说明有背景执行变化，仍不能证明全部L0事件均与策略调度或执行上下文无关。原始文本、IDs、首次分歧与终止记录保留在`formal_quality_diagnostics_v1.json`。

## 6. 这批证据能支持什么

- 直接回答同栈、相同任务与授权局部性下的Session/Template费用差异；只根据实际对象、RPC及完整费用解释摊销。
- 按冻结到达和完整成本评价TTFT与绝对Goodput；若只有费用优势而服务增量不稳健，就只主张模板经济性。
- 结合Raw实际配对和原子发布回执/物理命中解释条件有效性；部署自路径认证与Raw等价始终分开。
- 不修改原F8负结果，不把不同scope/来源/输入协议的倍率拼成因果曲线；不增加新算法贡献。

本轮可作为**同栈模板资格经济性、实际前缀复用与固定到达服务表现**的证据，须同时展示Raw配对质量。它不能替代此前保守Raw-witness协议的行为证据，不能共同包装成“本轮零退化且获得上述Goodput”的统一结论。要求逐请求Raw行为保持的场景，仍需匹配其证据作用域及相应成本；当前原型没有在两协议之间自动切换的实现主张。

本次不删除doc107、不改0.03阈值、不将正式结果用于重新选择来源，也不追加GPU矩阵。对严格Raw保持的未解决点及已知Repo/Llama限制交给下一次明确决策，当前阶段以完整证据收口。

## 7. 原始证据、复算及保留失败

完整原包SHA256：`2090b69910e47ce904ac97516c126ca0dc912fa374501d85801008678f758a54`；356134211 bytes，1140个成员，32MiB分片。
本地安全恢复后，10368业务、27单元、完整summary和4份CSV逐字节一致；原始成员均未改变。
正式冻结SHA256：`bf5f1960d0bdac48c58402b741e9aab83e61585be9353320ef25412b5e864f87`。所有角色真实输入IDs、计划时钟、任务评分、Native hit及HTTP验证次数按原记录核对。

证据入口：`formal_protocol_v1.json`、`formal_analysis_v1/`、`formal_evidence_v1/`、`formal_local_independent_recompute_v1.json`。
保留首次零输出启动依赖遗漏、Windows manifest路径预检失败、独立归档镜像漏收与修复记录；这些基础设施/CPU交付失败不冒充模型负结果，也没有通过重跑有效GPU单元消除。

本次本地恢复另遇到Windows总路径长度271字符的限制，尚未进入分析；原失败目录保留。改用工作区内`.artifacts/f2`（最长242字符），同一原包、同一分析程序即通过。该路径调整不改评分、统计或GPU记录。见`formal_local_restore_failure_v1.json`。

独立复算后另做只读CPU诊断，未修改预注册主分析：`formal_quality_diagnostics_v1.json`记录质量与终止，`formal_cache_partition_audit_v1.json`记录实际共享分组，`formal_execution_audit_v1.json`核对27份实际launch/排空与12,524份资源快照。未发现测量期间其他GPU进程，匹配三臂使用相同CUDA设备序号且实际GPU UUID映射稳定；GPU矩阵正常退出后计算进程已释放。这些诊断脚本和输出单独归档，不冒充事前冻结的新增检验。

模型、tokenizer、runtime身份与epoch/授权组冻结；可信operator的语义误声明和时序信道仍不由HMAC/字节hash自动解决。本轮是内网可信controller实验，不声明公共IAM或完整多租户机密性。

预定单元结束后收口；不更换来源、负载、SLO或输出预算追求最高倍率。正文与Response Letter留待后续单独处理。
