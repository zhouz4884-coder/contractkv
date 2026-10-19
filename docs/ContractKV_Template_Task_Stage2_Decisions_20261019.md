# Task-Bearing Template Service Validation：执行决策

## D1：采用原部署语义，Raw质量另行测量

源码确认旧模板注册以compiled prompt生成路径作见证，而非Raw回答。新Session/Template两臂统一使用该部署attestation，并分别测实际Raw/Compiled输出IDs、终止与任务分数；不借F7或R4的Raw-query保证。0.0625/0.125/EOS与PSTP检查不变，Repo保留现有Python输出契约，不取消保护以提高通过率。

## D2：不以缓存身份差异制造摊销收益

三臂所有业务采用统一授权模板缓存组；Session只改变证书对象和tenant绑定，不分裂底层缓存组。canary统一在controller-private命名空间生成，避免未验证候选被普通APC提前暴露给业务；Session与Template都可在同一私有模板组复用canary缓存。正式clock从注册前开始，计划到达时间不随注册完成后移，零slack。

## D3：接纳用户新增P0–P3设计，保留CPU历史

首次v1仅HotpotQA、尚无GPU输出。用户随后补充Qwen优先、HotpotQA/RepoBench、六模板/8租户/8轮、两负载/三重复；v2单独发布，复用原盲选Hotpot来源而不根据输出重选，增加2开发/3正式Repo。两版本CPU内容、哈希与未消耗的旧六验证来源均保留。共同16K下完整问题/CODE_PREFIX/空白必须保留；超窗可选上下文仍按已冻结、不读gold位置的首尾规则裁剪，不称为完整未裁原文。新10来源没有发现与729历史组或彼此完全相同的任务上下文，不宣称语义独立。

## D4：Qwen开发先于Raw-only标定和正式矩阵

先4来源52生成；按家族检查双来源注册、配对质量、真实前缀命中及64次复用的实测费用空间。无家族通过即停止，失败家族保持L0。只有通过后才冻结Raw-only实测负载与SLO，Qwen最多18正式单元；其他模型须独立开发通过才各9单元。RPC成功率、布局覆盖和实际Goodput分别报告，不设置漂亮倍率验收线。

## D5：启动基础设施失败零输出，先修复依赖完整性

v2 Qwen attempt1在API模块导入阶段退出：冻结包未收运行时动态导入的`tsc_revision_r2_margin_policy`，且诊断trace路径入口亦未纳入闭包。模型权重未加载、业务/模型输出为0，完整server日志、launch、failure、worker exit与旧freeze保留。此项属于新编排缺陷，不是实验方法或质量负结果。

依据不可变runtime源码补齐五个动态脚本模块及trace entry，增加隔离快照下的API CLI help、scheduler/model runner和trace导入预检。随后v3的CPU预检又拦截了三条Windows分隔符manifest路径；未启动新的模型server。v4将所有seed强制规范为相对POSIX路径并增加断言，旧v2/v3全部保留。未执行过的分析脚本旧远程版本亦改名保留。实际输入、阈值、生成预算、资格规则与统计协议v2不变；修复后Qwen使用fresh-server attempt2，不重跑任何有效完成的科学单元。


## D6：Qwen开发通过HotpotQA，Repo保留Raw；进入条件性后续

52生成、24配对的原包1745c4b6de146302ddf1d9c895d06b4233b2916a6dafa028d02434dd14ca146e（399成员）已本地安全恢复，summary和3 CSV独立复算完全一致。两个HotpotQA来源的12个实际compiled配对全部IDs/finish一致，Raw/候选分数分别0.75与0.50，12次全长度前缀命中；稳定提交14208/12192 tokens。完整Controller为11886.35/8311.05ms，64复用的TTFT粗投影均有成本空间；仅为开发门槛，不当正式加速。

两个Repo的compiled canary都未通过既有Python输出契约，因此无认证RPC/共享提交、不解禁；私有反事实6次ID改变均来自OpenServer，分数0.06→0.08未越0.03门槛。Qwen仅HotpotQA L3通过，Repo L0。依照预注册执行Mistral/Llama同源独立开发，后续Raw-only标定和正式服务仍须单独冻结；六独立正式来源尚无模型输出。


## D7：前瞻资格与正式范围收敛

三模型156生成全部完成；每个模型原包都经本地独立复算。Mistral两个QA来源通过质量/物理/成本门槛；OpenServer虽部署attestation PASS，Raw配对出现6次>0.03掉分，Repo族被前瞻门槛拒绝。Llama的QA doc151同样attestation PASS但0.40→0.00、6次掉分，两个家族均不合格，不运行其正式单元。所有失败保留，compiled自路径认证不能当Raw等价。正式仅Qwen18+Mistral9，共10368业务；两个模型Repo都Raw fallback，六个正式来源全部保留。

## D8：Raw-only锁定到达、SLO与计时

Qwen/Mistral各80请求全部成功，实际输入/Native/计划epoch和总wall均经远程及本地独立核对。Qwen Raw率0.3159078191 req/s；两负载0.2527262553/0.3159078191；TTFT/E2E SLO10500/13000ms。Mistral Raw率0.2418217143，负载0.1934573715；SLO11000/18000ms。阈值来自事前1.5×Raw请求本征p95、500ms向上取整公式，不用backlog全零到达的排队p95放大门槛。

访问采用已声明的两段32请求/template、所有六模板64请求的标记Poisson；这是受控模板局部性，不是生产trace或任意大工作集证据。新正式三臂的每个模型/重复固定同一物理GPU，Latin-square臂序，不改变registered identities与GPU并发2的区别；所有注册等待从相同全局epoch进入用户时延。仅按实际服务结果解释SLO，不以完整wall比值宣传容量提升。

## D9：网络故障只延迟归档，不改科学条件

GitHub smart-HTTPS反复reset/connect失败。已公开的科学冻结b525de3保持不变，真实校验回执在本地/服务器先封存，记录延迟上传后继续Raw-only。随后复用现有GCM授权，走GitHub官方Git Database API，逐blob/tree/commit验证字节与SHA，fast-forward更新同一main；未改写历史、未导出凭据。实际回执1632c9d及完整正式冻结93f54f5均已恢复公开并核对精确SHA，正式生成前完成。

## D10：按原编排完成前两波，不提前挑选性能结论

19:47核对前四个正式单元，每个384业务全部成功，最终后端排空均计入服务时钟；第二波的两份summary与completion SHA一致，未发现failure回执。两路metrics端口在波间停止响应，复查同一worker真实进程及completion确认属于原编排关闭旧server并进入第三波，未重启或复制worker。

仅取回已完成的summary/completion/drain/launch，原始逐请求数据与质量/物理命中独立复算仍待矩阵结束；不把不同重复或不完整三臂的结果写成最终性能结论。全部27单元、来源、到达、阈值及SLO保持冻结，未新增GPU请求。

## D11：六单元形成首两组三臂摘要，等待完整复算后选主张

20:16核对第三波两个单元的summary SHA、384/384成功与最终排空回执；累计6/27、2304业务全部成功。Qwen common80的第1/2重复三臂已齐，同重复arrivals SHA一致；只封存摘要级描述，不替代原始逐请求独立复算。

两重复中Session均为24对象/24真实认证RPC，Template均为3对象/3 RPC；累计Controller work约75.8–75.9s与50.9–51.0s，实际注册屏障约38.1–38.3s与26.4s。对象/RPC减少8倍，不把它写成完整认证GPU费用或服务延迟减少8倍，两臂均能复用合法canary/认证前缀。

Raw/Session/Template的SLO达标数，第1重复为105/240/245，第2重复为42/236/245（每臂384）；已封存`formal_first_two_triplets_summary_v1.json`，明确为待完整独立复算的中间摘要。暂不声称质量保持、统计显著性或普遍Goodput收益，不据此调整余下来源、SLO、负载或运行范围。第四波由同一worker进入原定high100单元，原计划继续。

## D12：报告同时展示绝对任务效用，明确重复与预算

正式GPU、评分器、分析程序及统计方法均不变。总报告生成器增加按任务家族分别列出的Raw/策略平均任务分数，直接由已定义的配对CSV字段描述性汇总；不因输出ID一致就认定任务回答正确。另明确每模板是同一固定问题的64次业务调用，生成预算HotpotQA128/Repo384，实际终止记录保留，避免把调用重复当独立问题或把有限预算当无限输出保证。

21:07第五波两个384/384成功单元的summary SHA及完整排空回执均通过；累计10/27、3840业务成功。原始逐请求独立复算、全部质量与服务结论仍待矩阵结束。报告措辞与描述性呈现的改进不用于改变实验资格、来源、负载、SLO或执行范围。

## D13：双负载前两重复全部封存，服务点使用绝对指标

21:34第六波完成并核对回执，累计12/27、4608业务全部成功。Qwen前两重复的双负载三臂摘要完整封存于`formal_Qwen_first_two_repeats_summary_v1.json`，同重复三臂到达SHA一致。high100两重复的Raw/Session/Template达标数分别为4/169/171与35/144/148（每臂384）。

这些仍是待原始逐请求独立复算的中间摘要。Raw在高负载点的达标数很少，相对Goodput倍率的基线较低；后续主要呈现绝对达标数、绝对Goodput和完整到达时延，不用巨大倍率掩盖原生路径的低达标基线。负载按开发Raw-only吞吐归一，不是正式来源的SLO容量保证；不因已看到的结果更换负载或SLO。Template与Session的主要差异仍从实际对象/RPC与完整费用解释，不预设其Goodput必须显著不同。

原worker已进入Qwen第三重复及前瞻资格通过的Mistral正式单元，剩余范围保持不变。全部任务分数、输出/终止保持与来源不确定性仍在最终审计中独立判定。

## D14：Mistral首个Session单元出现合法编译路由，不外推跨协议改进

22:51第八波两个384/384成功单元的summary SHA及完整排空回执均通过，累计16/27、6144业务成功。Mistral首个Session单元摘要记录24对象、24 PASS、24认证RPC，192/384业务进入compiled路由，Native计数无缺失。其Template臂仍在运行；全部原始记录、任务分数、输出/终止与具体命中量仍待独立复算。

这支持本轮固定问题模板服务条件下具备可执行资格与编译路由，不将其与旧R4不同来源/作用域的覆盖率直接比较，也不把部署自路径PASS当Raw等价证明。不据此扩展模型、来源、门槛或实验矩阵，继续完成原27单元。

## D15：Mistral首组三臂的服务效果相近时，以实际费用解释模板价值

23:28第九波完成并核对回执，累计18/27、6912业务全部正常返回。Qwen common80三重复的Raw/Session/Template达标数为252/686/700（每策略1152请求）；Mistral首重复为92/191/191（每策略384请求）。这些为摘要级中间值，完整逐请求独立复算、质量与不确定性尚待矩阵结束。

Mistral本组Session/Template各192请求进入compiled路由，实际认证RPC为24/3，累计Controller work为67.39/50.67秒。两者SLO达标数相同，符合事前允许的“主要优势在资格费用摊销”情形；不将微小wall差异包装为Template超越Session的稳定Goodput优势。Qwen的费用与RPC模式继续一致，全部18摘要封存于`formal_eighteen_cells_summary_v1.json`。

继续完成Qwen高负载第三重复与Mistral其余两重复，不以现有正向摘要代替Raw任务质量与输出行为核查，也不因结果修改原计划。

## D16：主模型测量结束后继续完整矩阵，提前修正最终MD交付的路径限制

10月20日01:17，第十二波完成并核对回执，累计24/27、9216业务均正常返回；Qwen18个正式单元全部完成，Mistral仍有原定第二重复三单元。完整24份摘要及各自SHA保存在`formal_twentyfour_cells_summary_v1.json`，明确标注尚未完成原始数据独立复算，不作为质量结论。

不因主模型已完成或已有正向服务摘要跳过剩余Mistral单元，也不扩展新来源或新负载。末轮统计、输出/终止与Task分数仍须等27单元完整后核验。

本机Git API交付helper的保护清单原仅允许`docs/ContractKV_Template_Task_Stage2_`前缀，与事前指定总报告文件名不同。仅补充允许确切文件`docs/ContractKV_Task_Bearing_Template_Service_Validation_Report_20261019.md`，没有开放其他文档路径；该调整只影响本地最终交付范围，不改GPU运行器、冻结分析或实验条件。

## D17：完整GPU矩阵后停止，不根据质量结果调参

10月20日02:57，27单元正常退出，10,368业务全部正常返回，无自动重跑。全量固定分析发现3,456编译配对中1,178次ID/终止变化、36次>0.03下降，全路由46下降、811上升。决定按原范围结束GPU，不改0.03阈值、不删来源、不放宽margin、不另开矩阵；以完整Raw质量与实际服务费用一起解释本轮结果。

## D18：Windows路径失败只修复交付路径

服务器分析/归档均退出0，356,134,211-byte原包、11分片、1,140成员全部SHA核对。首次本地恢复因Windows总路径271字符失败，尚未进入分析；失败目录/记录保留。改用工作区内最长242字符的`.artifacts/f2`，同一原包、同一分析程序完成全量独立重算，summary全部值与4 CSV字节完全相同。没有改评分、统计或GPU数据。

## D19：质量失败按来源归因，不能用均分或词面变化删除事件

事后只读CPU诊断确认36编译下降全部为Mistral doc107的6个tenant/turn条件，在3重复、两策略中重复出现。Raw实际输入/输出在这些条件重复稳定；compiled全部匹配注册compiled见证，均命中16,000-token前缀。两答案均选择错误人物，措辞长度使F1为0.2000/0.1667，首次ID分歧位置7，正常stop、未触预算。保留官方分数和下降标记，不将其解释为零退化；同时记录doc64的正向变化，不将提高准确率当作行为等价认证。

另有10个L0下降，11个L0输出差异中10个与另次Raw输出相同，说明存在背景变化，不能据此证明全部与策略执行上下文无关。全部文本、IDs与对应文件记录可查。

## D20：缓存共享公平性核对关系而非跨fresh-server盐字节

首次事后诊断的“跨fresh-server salt字符串相同”为false，原记录保留。冻结代码每单元生成新CacheAuthority HMAC密钥，各新空引擎的盐字节因此轮换。后续只读审计直接检查全部wire字段：27单元均为6业务组、每组64请求/8tenant，三臂共享关系相同，canary与业务组分离。没有对Session做per-tenant物理分区，也没有跨独立引擎转移KV。报告明确逻辑授权组一致、实际salt字节不同，不把后者改写为字节一致。

## D21：本轮证据选择与收口

本轮可支持同栈Service-Template资格经济性、真实前缀复用、零slack计划到达Goodput/TTFT，须同时展示Raw配对质量。不能把其与先前保守Raw-witness协议的零事件合并为统一保证。模型/来源/Scope均分开，Repo仍Raw、Llama开发No-Go及低绝对任务分数完整保留。MD报告给出实际能/不能支持的主张，正文与Response暂不修改；原定实验完成后结束本阶段，不自动创建新研究线。
