# ContractKV：行为作用域修复决策记录

## D1 — 先修准入连接，不改评分或部署结果

用户上传评估指出部署 compiled 自路径见证被误用于未来 Raw 行为准入。已核对原代码：`register_one` 固定 tenant00/turn0，模型可见 metadata 却随后续请求变化。保留 27 单元、36 次 compiled 掉分和全部 ID 差异。新版本将模板授权与精确请求 Raw 行为记录分离；只有实际 Raw witness、实际 Candidate 自由生成一致、既有 Token/EOS margin 与 PSTP 验证全部满足才能签发严格记录。授权、schema 或部署自路径 PASS 均不能代替这条记录。

## D2 — 不将 64 个唯一输入变成 64 次昂贵认证

先离线统计旧协议每个引擎中的精确输入重复数。唯一请求直接 Raw，不声称取得模板 O(1) 的 Raw 等价资格。新机制验证使用明确声明的精确输入重复负载，保留模型可见 tenant/turn 内容，不合并不同后缀、不删除 metadata。精确作用域随不同输入数增长，模板物理前缀仍可共用；不宣称任意 query 只认证一次。

## D3 — 有界新来源验证与停止条件

开发使用 Qwen/Mistral、两个新 HotpotQA 和一个新 RepoBench 来源，三个 fresh-engine 对照：Raw-authorized、历史 Deployment、Strict-exact。每来源两个精确输入，各重复四次，合计 24 业务/单元、6 单元；额外 Raw/Candidate 参考及认证全部计费。旧 Repo 家族前瞻 L0 保留，不借本轮解禁。来源只按预先冻结种子哈希和容量选取，gold 不参与选择或裁剪。

开发若严格已获准子集出现不能解释的 ID/EOS 差异，或完全没有 QA 资格，停止正式测量并报告失败。若至少一个模型同时具备严格合法资格、实际命中和按八次访问的实测成本空间，则只为该模型运行独立阶段：三个新 QA、一个新 Repo、每来源两个精确输入各重复八次；三臂、两次 fresh-process 重复，最多 12 单元/768 业务。来源提前锁定，规则不据 held-out 调整。指标为完整 wall、TTFT、任务分数、实际新 Prefill 与资格成本；本轮不宣称开放到达容量或新的 SLO Goodput。

该重复负载是显式条件，不是生产重复率测量；原 64 唯一后缀负载不能被新结果替换。若实测成本不能摊销则保留 NO-GO，不扩大矩阵或放宽门槛。正式阶段仍须另行冻结文件 SHA、执行前回执和来源。

## D4 — 资源与旧任务核查

已通过保存的 Credential Manager/known-host SSH 入口确认同两张 RTX3090 的实际 UUID，无 compute PID；旧 27 单元 worker 已完成。新环境、缓存、日志仍限 8TB 卷，复用冻结隔离 runtime，不修改共享运行时、不抢占其他任务。新 worker 启动前再次检查。

## D5 — 首次公开冻结的换行属性修正，推理前逐字节复核

首次加入新 results 目录时 Git 沿用了文本换行规范，导致远程 Git 中 freeze JSON 的字节与本地/部署副本不同。GPU 尚未启动。为新实验目录及脚本增加 `-text`，重新提交原始字节并核查所有冻结文件与 source snapshot 的 Git blob；保留前一提交，不改科学内容、哈希或选样。后续仅使用字节一致的公开提交和实际预检回执启动。

## D6 — 吸收用户补充，区分物理前缀与行为范围，推理前封存 v2

用户补充正确：Session 24 对象仅为 3 条 canonical prompt 的 8 租户绑定；不能解读为 24 条独立 prompt。不同 tenant/turn 的完整输入不同，而稳定前缀相同，这是物理模板复用的正当依据；它不能推出 Raw/重排完整生成等价。新补充还指出旧 admit 用保存 plan/certificate 自比，没有对实际线上前缀重新哈希。新 v2 在发送前对实际 tokenizer IDs 按证书 stable_prefix_tokens 重算原有 JSON-ID SHA，并检查 block-aligned commit 边界；完整请求的 Raw 行为证据仍独立必需。Native 命中是事后物理观测，不能替代准入中的这项检查，也不能由 partial/zero hit 推出前缀身份不同。

v1 仅完成 CPU 准备/预检，未启动任何 GPU 推理。保留 v1 全部快照和回执，另建 v2 源码、协议、冻结与回执；来源、评分、输出预算、margin、重复负载及预定停止门槛不变。修复不需要重新选择来源或模型结果调参。

## D7 — 推理前校正可区分的 Native APC 对照，不按结果选择 locality

代码审查发现 v1/v2 的 source-outer 请求循环会连续耗尽单来源的两条精确输入；Raw APC 在该顺序下也可能缓存完整 Prompt。精确重复本身不是 ContractKV 独有优势，不能因此预设加速。首条 GPU 输出前，将三臂统一改为 access round → frozen source order → 两个 exact scope 的轮转。保留每个 Prompt、计数、模型和所有门槛；不增来源、不制造不同 raw/compiled 身份或更小 Raw 缓存。v1/v2 均无 GPU 推理，保留 CPU 冻结/回执。v3 单独冻结，双方实际命中和工作集效应必须共同报告；该访问模式不是生产访问率或通用加速证明。

## D8 — CPU 预检日志名称冲突，保留旧日志并修复编排命名

v2 完成文件/模型核查后，`open('xb')` 阻止覆盖 v1 的未版本化 CPU import log，故预检退出，尚无 GPU 推理。v3 同样存在该日志路径问题，未运行。新 v4 worker 仅将预检、worker 日志和执行回执命名隔离；科学客户端仍为 v3、科学协议仍为 v3，来源/顺序/参数均不变。旧日志及失败完整保留，不删除冲突文件或绕过回执。v4 重新冻结、CPU 预检成功并公开实际回执后再启动首条推理。

## D9 — 区分传输占位文件与真实执行状态

早期 CPU-only 监测尝试下载尚不存在的 v2 回执，传输工具在本地留下 0-byte 文件；后来部署清单同步了这些空文件。没有对应实际 launch/worker/GPU 请求，不能解释成 v2 已运行。旧 0-byte 占位及快照原样保留。监测器改为先 stat 远程文件、下载临时文件后原子落盘，并显式标注 legacy empty placeholder，禁止把它读成有效 JSON 回执。v4 使用独立命名且启动前核查无现有 worker/有效状态，未覆盖真实数据。

## D10 — 首次 GPU 启动使用已公开真实回执

实际科学 freeze v4 SHA：`fab31a882f05c13a564cabfd53765087916263098a478713f18f428a7ba5057f`；实际模型全 SHA 与隔离 import receipt SHA：`74e33b7e6a4336da4dae33281cef5d9317021e3a88c4e357841a8c806266b8d6`。285 份 root/snapshot/Git blob 逐字节一致。实际回执提交 `86e146f8d45ebbd698f2ce2fe5786b73e9790924` 与 origin/main 一致后，唯一启动 worker PID 1158844，epoch 1792472155.7256038；两张 GPU 的真实进程为其隔离 EngineCore。只续查同一 worker、锁与状态，不重新启动已完成单元。

严格入口用于本轮真实 GPU 客户端；旧 Deployment 入口保留为显式对照，不能自动视为严格 Raw 等价。新记录复杂度随精确输入数增长，不通过该修复宣称模板一次认证覆盖任意动态后缀。物理前缀对象、授权组和行为准入是三个不同的判断对象。

## D11 — 6 个 GPU 单元成功，离线哈希编码检查作窄修复

worker 1158844 于 epoch 1792472966.8830047 正常结束，6/6、144 业务均正常完成，GPU 已释放。冻结分析 v4 在首个 Raw 行为哈希检查处失败：新 ExactBehaviorLedger 用 compact JSON 的 SHA，旧传输日志 `phase17.digest` 用带空格 JSON；两者对同一 IDs 数组字节不同。客户端与 ledger 内部编码一致，实际 Raw/verification 证据还单独按旧传输哈希核对，属于离线比较器错误。保留 v4 失败，新建 v5 仅将这一处比较改为 ledger 的 exact_digest，并以 AST 证明除新增 import 和该单调用外完全不变；未改 GPU、评分、阈值、统计或成本公式，不重跑有效 GPU 单元。

## D12 — 本地原包复算通过后，按预定门槛进入独立阶段

开发原包 7,524,486 bytes，SHA `246f236dc86f25ce38f3682d2fefec45e88dbf2fc1b995e962c8c2fb51d61dcc`，217 原始成员安全恢复，全部 SHA 保持不变；相同 v5 分析源码在本机独立复算所有 JSON 值完全相同。两模型各 12 严格 compiled 配对，ID/EOS 变化与分数下降均为 0；8 个精确作用域通过原有 Raw/候选/EOS/PSTP，均有负例拒绝控制。8-access 开发成本屏幕均为 true，故两个模型按既定规则进入独立 12 cells，不按候选快慢或 QA 正确答案改来源、顺序、门槛或 SLO。本轮不新增开放到达/SLO 容量矩阵。

## D13 — 独立冻结及实际启动

独立 freeze SHA `960cfd1c92ab6c10b143e6967dde497dc8e50542a9974ca436723d86f2f0bc90`；实际 preflight SHA `9b82634491ba5122a998f08af9f7138941904c793fe5b41bb3946caf73bbec09`。339 份 Git/root/snapshot 字节一致，真实回执公开到 `5d65625520aa06584ebc2eb8012077b654171aec` 后，唯一启动 worker PID 1172482。三臂两模型两重复共12 cells，未改独立来源或规则。后续只监测同一 worker，不因首重复结果改变余下单元。

开发完整 wall 如实保留：Qwen Raw80.307s / Deployment52.316s / Strict81.637s；Mistral145.834s / 91.337s / 114.905s。Qwen四次访问尚未回本，不能把八次访问的开发投影写成已测收益。24条严格compiled的Raw参考分数均>0；旧doc107实际36对输出离线比较全部不相同，旧部署记录不能绕过新Raw行为记录要求。此回归不预测新GPU重放必然生成旧输出。

## D14 — 记录代价机制与联合准入检查，不改独立规则

开发实际记录显示 Mistral 第二个同模板精确资格分别读取15,904/15,840个已认证前缀Token，验证HTTP约94/97ms、完整Controller约513/520ms；首个资格约10.4–11.4s。Qwen只部分读取4,752/2,352 Token，注册仍约6.4/8.7s。该描述支持保留原PSTP前缀辅助验证与驻留区分，不能把所有资格都当全驻留，也不是独立冷热因果实验。

新增CPU联合测试覆盖“合法授权+真实前缀+Raw行为记录”同时满足才通过；修改实际前缀同时触发物理/行为拒绝，修改后缀则保持物理前缀检查通过但行为资格拒绝。相关23项CPU检查通过。测试和事后审计不改变任何GPU客户端或冻结分析口径；独立进程持续使用同一worker，未依据首重复改规则。

## D15 — 独立单元完成后停止，混合收益如实收口

独立worker 1172482正常退出，12/12、768业务正常返回且均stop；无自动重试，GPU已释放。加开发共18 cells、912业务。独立严格84 compiled配对ID/EOS变化0、下降0；Qwen56/128业务、Mistral28/128业务。全路由Qwen无ID变化；Mistral两次L0变化、分数+0.00879未越阈值，均在Raw重复中见过对应输出，不据此宣称策略完全无影响。

完整wall收益Qwen1.027×、Mistral0.987×；不继续调margin、换来源、增加重复次数或扫描档位追倍率。Mistral业务HTTP节省14.608s，小于注册Controller19.070s，再加其它2.132s，净多6.594s；Qwen53.462−36.467−5.775=净省11.220s。该分解不是GPU kernel因果归因。84 compiled中42零命中都在每对的tenant00，随后的tenant01共42全命中；实际前缀/共享组正确，记录“驻留/工作集与合法覆盖为后续性能问题”，不在本轮新增pinning或调度算法。

## D16 — 原包、独立复算与完整费用闭合

全原包29,502,530 bytes，SHA `96fc6281f0049ba3f374c2be1177d5edd76d6c2144acc2dc1ca10f895e8ac3b2`，379成员安全恢复到本机，所有原成员SHA保持不变；开发/独立v5所有JSON值复算一致。18单元954生成HTTP+34验证HTTP与Native初始观测逐项对应，额外未记账请求0，失败/私有候选均计费。34 PASS的既有floors与block提交边界再次检查通过；14个注册拒绝零compiled发布。826资源快照中无外部GPU任务。正文和Response未修改，停止本阶段新增GPU。
