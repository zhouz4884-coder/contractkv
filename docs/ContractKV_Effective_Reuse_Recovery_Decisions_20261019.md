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
