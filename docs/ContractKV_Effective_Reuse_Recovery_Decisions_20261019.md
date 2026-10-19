# 有效复用恢复：证据、判断与可证伪条件

## D1：不把exact-observation拒绝直接转成PASS

12个V5主服务cell的162项决定已从原包读取。scope拒绝后的同query请求中，没有发现与原见证完全相同的实际Prompt IDs；metadata包含tenant/session与turn。当前没有证据可在不扩大行为作用域的情况下恢复这些请求。拒绝不证明它们必定有害，但不能把这种未知改称已获资格。

## D2：先删除确定无效的候选准备

108项scope/输出契约拒绝在此之前已有候选准备，累计13,547.57ms。它是组件总量，不是关键路径节省或新的GPU秒。最小变体只把同一scope/输出检查前移到Raw见证后、候选tokenization前；合格见证仍执行原fine经济判断、Raw/candidate/EOS检查与PSTP。可能增加某些原fine经济早拒条件的Raw logprob请求，因此全业务成本和Raw变化都必须记录，不能只数少做了几次tokenize。

假设：能在保留有价值PASS的同时减少一部分确定无效准备。反例：PASS覆盖降低、Raw/compiled出现无法解释的变化，或节省量相对于完整服务过小。出现反例不靠扩大scope或调margin补救。

## D3：全V5授权接入是独立修复验收

上一轮828业务证明了统一缓存身份，但全V5 runner尚未调用新入口，也未逐请求使用实际签名绑定。新增适配在业务/验证前强制身份，并将原有CertificateBinding/RequestBinding检查接入compiled准入。HMAC和identity开销在实际服务clock内记录；初始密钥建立在clock前，与已有原型定义一致。backend仍是可信内部端点，不包装成公共IAM。

21项CPU检查通过；首个CPU夹具漏runtime.concurrency造成1失败/20通过，补夹具后21通过，未运行GPU时修改，失败摘要保留。AST证明只更改声明的授权/执行hook及已有final-drain，调度、到达、wave循环与评分不改。

## D4：接线与泛化分开

三个已知来源用于全V5接线：两个已知QA资格来源和一个继承Repo L0来源，每臂60业务。三臂依次共用一个fresh engine且各有独立短期控制器密钥；不同先后工作集会影响驻留/数值路径，因此只作开发、成本分解和正确性，不用它直接宣布新服务倍率。

另盲选4个新开发来源，三模型分别探测已有L1/L2/L3，各12候选。候选经济性尚未由该诊断证明；同时保持原scope/输出/Raw-candidate-EOS margin。原L0族若有候选成功，仍不能跳过成本输入的合法性。独立验证另6来源在任何开发模型输出之前已选定、输入保真/16K与实际tokenizer检查已完成，至此未使用其模型输出。

## D5：不把可行候选或小费用改善夸成收益恢复

原M/L Repo L0只有reason而无完整prefix-state成本模型。即使新开发出现合法候选，也须明确这个缺口，不能把别的模型/家族的费用硬套进去。单个可行来源不满足开发选择规则；正式source-disjoint样本也不能反过来决定新档位。

后续独立服务是否值得启动，依据实际开发的合法覆盖与完整关键路径成本，而非追求一个新Goodput点。若没有实质改进，保留NO-GO及已完成授权回归，不无条件增加矩阵。若启动，Raw与两个Contract臂采用相同授权边界、同来源/到达/设备配置/SLO及完整费用，旧无盐历史结果保持原样。

## D6：新增适配器的renderer引用捕获错误，保留失败、版本化修复

v1已知来源接线在Qwen第一个compiled业务（doc90/turn3）及Mistral第一个compiled业务（doc187/turn3）被原前缀身份检查拦截：实际Prompt IDs hash不同于冻结保真输入。查明是本轮新增适配器先复制`fixed.__dict__`，后启用保真renderer，导致编译业务函数仍引用旧渲染器；Raw准备和candidate planner已正确使用保真版本。这是新增接入基础设施错误，不能归为ContractKV行为认证作用域内的新质量反例。

v1两个fresh-server均未形成完整配对，共154业务全部保留；新4来源候选诊断尚未开始，独立6来源未产生模型输出。两个worker自然失败退出，未终止其他任务。冻结v2只把执行函数编译移到adapter安装后，并在执行前断言捕获的renderer身份；新增能实际走过wrapper初始化的CPU回归，22项通过。原v1源码/冻结/失败日志不覆盖。

Q/M受影响的整套配对使用新的fresh-server attempt2重跑，L此前未启动，在修复版首次执行。没有已完成的有效科学单元被重跑，没有换源、改预算、改margin/scope或按结果选择。v2仍需完整发布实际预检回执后才能GPU执行。

## D7：旧费用残差主要不是可删除的CPU开销

按归档分析器的串行canary分组规则，将525 Controller关联到模型/任务/来源：453真实认证HTTP中298 PASS耗791.013s、155非PASS耗538.447s；435正常Raw参考耗593.273s、30参考异常耗108.607s。另60无RPC L0 warmup耗123.751s；其他残差只有6.204s，总Controller2161.294s。不能把无RPC warmup当未解释CPU开销，也不能将这些跨独立cell的累计值当一次服务wall。

严格V5已经复用真实业务Raw见证，所以去除旧重复Raw不属于本轮新收益。失败认证中的真实prefill是主要代价之一，不能仅靠前移布尔检查消除；开发重点仍是已有较轻候选能否合法通过。若没有覆盖机会，预计延后候选准备只带来有限费用改进，应据实收口，不扩大CPU预测或门禁模型。

## D8：采纳新建议的目标分离，并以实际记录否定直接抬Raw门槛

用户新建议已全文阅读，目标细化为A1无效准备成本、A2失败GPU成本诊断、B合法覆盖、C条件性renderer对照、D机制验收后独立服务；详细门槛见计划顶部及goal_refinement_v1.json。现有v2运行和4/6来源不变，不另起平行矩阵，不把认证成功率等同覆盖，也不承诺60%–80% PASS或80%GPU降本。

CPU读取旧F8 Qwen common+high六cell共42 RPC（6 PASS/36 FAIL）及上一轮九cell授权回归75 RPC（42 PASS/33 FAIL）：提议Raw全部margin<0.125的调用两组均0，抬Raw门槛在这两组中不筛掉任何失败RPC。逻辑上Raw低margin也不蕴含candidate低margin，故不采用此修改。

授权回归33失败的完整R2 rank/margin/EOS trace可恢复精确最早失败位置，6次首词失败；全部cached_prefix_read_tokens=0。后续witness位置相对未缓存输入token-slot代理占比约0.076%–0.362%。这个比例不是FLOPs或GPU时间上界，RPC也不是纯kernel时长；它只说明当前记录不支持80% GPU节省的说法。F8性能日志没有完整逐位置trace，不能把全局argmin当最早失败位置，故保留缺失。数据集/人工控制/真实任务分母不合并为生产分布。

因此Early-Abort不抢占当前已冻结GPU任务，也不立即修改Scheduler。待本轮新开发trace完整后再独立诊断；只有存在可观未完成工作和可实现的分段执行点，才考虑完整验证Oracle一致性及真实GPU微基准。Clean Renderer同样需要代码输出回显/格式干扰证据和独立双renderer开发对照，不静默修改当前输入或借用旧证书。


## D9：三模型开发完成，只有代码元数据对照获准进入下一步

v2三个fresh-server正常完成600业务；远程CPU核算中32条已编译Raw配对无ID/finish变化、原PASS无丢失，最终结论仍需取回原包独立复算。Deferred跳过14次准备，但不等于少做GPU认证。36个新候选中8个PASS/可用，均来自同一QA doc8的部分档位；另一QA来源受原scope限制，Repo候选无PASS，没有任何模型/家族满足事前2/2门槛，故新目录暂不部署。

Qwen semivl实际Raw输出回显CODE_PREFIX标题及路径；官方RepoBench构造器将路径写为Python注释（固定提交53c1c55ad9e6d97d2b60dd2c9548ed1cd463b6a5/data/utils.py）。这只支持格式干扰假设，不能直接认定因果。追加一次有界开发对照：同两个已知开发Repo、三模型各一个fresh-server、current/clean两renderer共60业务/36候选；Mistral反向顺序，其余current先。不是正式新来源或公平速度对照，不消耗held-out输出。

仅抑制框架CODE_PREFIX标题并将最前filename元数据注释化；原代码、原问题、预算384、Scope/输出契约、0.0625/0.125/EOS/PSTP与评分不变；重新tokenize/认证/独立授权namespace。5项CPU检查通过；新增真实prepare测试起初误用不存在的raw_order夹具字段，改用原layout_for_level返回的L0 order后通过，未触发GPU。若没有同档位2/2严格可用证据则停止renderer分支，不继续调提示词或放宽门槛。


## D10：格式对照完成，按门槛停止覆盖恢复与正式矩阵

60次生成/36候选、三模型fresh-server全部正常退出。Current 0/18 PASS、3真实RPC；Clean 0/18 PASS、6真实RPC，均candidate margin失败。Raw标题回显1→0、语法通过1→2、scope可共享2→3；任务分数六点两升一降三无实质变化。Qwen semivl 0.05→0.25但新增三档认证均失败，说明格式改善未转化为合法复用，不能取消行为门槛。

12/12 Raw重复稳定；Current六个Raw与先前开发实际Prompt IDs及输出IDs/finish全部相同。36拒绝候选的私有反事实生成有26个改变，零新增共享发布。两仓库不是六个独立来源，不报正式速度因果/泛化效果。原包931ed7b382c19d4dc85464de1832e3e8ebe2c8a453be24c4db70d66de5dcda03的2376成员安全恢复，60生成、summary和3 CSV独立复算完全一致。

决定：不部署clean renderer作为资格/性能修复，不解禁新目录，不开发分段验证或新收益预测器，不启动独立服务大矩阵。六个held-out来源保留且无模型输出。保留全V5授权接线和单独测量的有限Deferred执行变体；当前受限开发不足以支持新的Goodput优势。两卡实际compute PID为空、各24MiB背景占用，全部本轮worker正常退出。正文/回复信不改；本轮目标以真实NO-GO和完整证据收口。
