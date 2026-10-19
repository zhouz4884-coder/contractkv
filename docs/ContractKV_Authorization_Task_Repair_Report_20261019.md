# ContractKV 授权与任务资格修复：最终实验报告

2026-10-19。GPU九个冻结单元及本机原包独立复算均完成。本轮是V5收口后新授权的有界修复，不替换V5主结果，不修改正文或Response Letter。Git交付状态见本轮目录的最终发布回执。

## 整体判断

**整体是好消息：已经用真实引擎修复并验证了Raw APC授权边界缺口，域内合法复用仍然保留。任务覆盖方面没有普遍改善，不能据此宣布新的性能提升。**

原先是compiled证书可以拒绝跨域/旧epoch，但Raw fallback仍走无盐原生APC；现在新可信入口把授权缓存身份贯穿Raw、fallback、compiled和GPU验证/PSTP。三模型各三次fresh-server控制中，跨域和新epoch首次请求各63/63为零原生命中，实际块hash链分离；域内四类合法重复各63/63保留命中。不是只检查请求字段。

RepoBench则没有证据支持本轮放宽契约：旧12个语法拒绝和新来源诊断都没有确认合法单行上下文续写被误拒。原语法保护、Mistral/Llama继承L0和全部行为阈值保持。本轮真实获准编译仍集中于Qwen和一个Llama来源，Mistral为零；这个限制保留。

## 1. 修复方法与不变量

新增`scripts/contractkv_cache_identity.py`与`scripts/contractkv_authorized_requests.py`。可信控制器核对membership和active epoch，用HMAC-SHA256绑定engine、policy、template、domain、epoch。每次业务/验证派发前重新检查身份；没有缺省无盐fallback。当前有效身份拿着旧compiled证书可以Raw回退，但必须使用当前epoch身份；过期请求身份本身直接拒绝，不发送Raw。

注册适配只替换原SingleShotRegistrar验证payload中的salt表达式，其余注册AST一致，复用V5既有INCOMPLETE窄修复。Raw margin 0.0625、candidate/terminal-EOS margin 0.125、行为scope、候选档位、评分、生成预算和PSTP发布语义均未放宽。历史测量入口及共享runtime不修改。

CPU共11项检查通过，覆盖身份/域/epoch、伪造或缺失身份、Raw与验证wire一致、margin早拒和single-shot、完整92业务路由及15个模拟验证ID唯一。这些是接线和回归检查，GPU证据另计。

实际vLLM 0.10.2 V1代码的五份源文件及SHA已保存：salt进入Request和首块extra hash，经父块hash传播到后续块。与[官方前缀缓存设计](https://docs.vllm.ai/en/v0.10.2/design/prefix_caching.html)一致；正式结论同时依赖实际runtime审计和下面的物理日志，不用网页说明替代实验。

## 2. 冻结协议、来源和执行

- 三模型：Qwen3-8B、Mistral-7B-Instruct-v0.3、Llama-3.1-8B-Instruct；各三次fresh-server，共9个cell。每个cell内部始终不清缓存、不重启引擎。
- 每cell含一个人工marker和六个真实来源，92次业务、15项资格决定、7次旧身份发送前拒绝。合计828业务，其中702真实任务、126人工控制；135项资格决定，实际75次GPU验证RPC，无不确定响应或自动重跑。
- 固定seed 2026101901，排除713个既有来源组后按hash顺序盲选；完整context字节与728条既有记录及本轮彼此不重复，不声称语义独立。HotpotQA为doc169、doc106、doc191；RepoBench为AContesini/Convert_PDF_to_DOCX_or_vice-versa、MorrisNein/pecapiku、lalalamdbf/PLSE_IDRR。
- 沿用结构保真16K协议、关键字段及代码空白保留、gold无关裁剪。预算QA128/Repo384/marker64。全部828业务成功，所有实际Prompt IDs与冻结tokenizer结果一致，未出现length结束。
- 先执行legacy无盐Raw对照，再执行统一身份路径。旧阶段每上下文5业务，新阶段8业务（人工另加1业务）；**任务量和缓存先后状态不同，不作两阶段wall相除的速度比较。** 这是有界顺序微工作流，不是新的开放到达容量或完整经济门禁实验；资格门禁是继承档位与未变行为检查的定向诊断，未复现原完整Frozen Net-Benefit Gate。

实际freeze_v2 SHA256：`b67da7d3b05c08c96d0bf36c997f99570f01af6b2350bbac6c9f942f22f3c9f3`，81项依赖。预检在Git `87cd23c52ec500b89ccba0f7a00fdd6878eb874c`公开后才执行GPU。v1未运行GPU；预执行发现两阶段RPC/txn ID可能重复，保留v1，另冻v2解决命名冲突，未按GPU结果修改规则。

## 3. P0：同引擎物理授权边界

每项均有63个可用对照：7个上下文×3模型×3进程，其中9个人工、54个真实任务。重复不是63个独立来源。

| 实际对照 | 原生block-hash/命中观察 | 支持数 |
|---|---|---:|
| 旧跨域Raw fallback | 与旧Raw相同hash链，仍命中 | 63/63 |
| 旧证书/新epoch的旧Raw fallback | 仍复用旧无盐Raw链 | 63/63 |
| 修复后首次跨域B请求 | 相同Prompt IDs，hash链分离，0命中 | 63/63 |
| 修复后首次A epoch2请求 | 相同Prompt IDs，hash链分离，0命中 | 63/63 |
| A epoch1本principal合法重复 | 同链且命中 | 63/63 |
| A epoch1第二合法principal | 同组复用仍命中 | 63/63 |
| B自己的合法重复 | 新域自身状态可复用 | 63/63 |
| A epoch2自己的合法重复 | 新epoch自身状态可复用 | 63/63 |

另有63/63次旧请求身份在backend前拒绝，无业务或fallback发送。它与“有效当前身份持旧证书后Raw回退”的对照是两种不同情形。

人工marker在实际tokenizer中的结束位置分别为64/76/81 token；旧跨域/旧epoch命中确实覆盖marker，而不是只命中前面无关的system文本。三个重复结果一致：

| 模型 | 旧跨域/旧epoch Raw命中tokens | 修复后跨域/新epoch首次 | 同组Raw重复 | 获准compiled提交/实际命中 |
|---|---:|---:|---:|---:|
| Qwen | 1248 / 1248 | 0 / 0 | 1248 | 1232 / 1232 |
| Mistral | 1488 / 1488 | 0 / 0 | 1488 | 1472 / 1472 |
| Llama | 992 / 992 | 0 / 0 | 992 | 976 / 976 |

135项资格决定中42项获准、93项拒绝或未进入认证，后者候选新增共享提交全部为0；75次实际RPC中33次未获准。这不意味着Raw不缓存或已有块被清除。9次专门构造的ACK/NACK错误候选均拒绝、提交0。该控制用于事务拒绝，不冒充CALC合法布局必要性消融。

## 4. 自由生成、任务分数和剩余覆盖限制

修复路径获准后有42个自由生成配对：24个真实任务、18个人工控制；输出IDs及finish均无变化。真实24次读取全部实际命中至少完整的获准提交前缀。这里的42不是42个独立来源，行为保持也不等于绝对答案正确。

| 模型 | 真实修复路径编译业务/配对 | 完整提交前缀命中 | 观察到的ID/finish变化 | 获准真实来源 |
|---|---:|---:|---:|---|
| Qwen | 18 | 18/18 | 0 | Hotpot doc106、doc191；Repo MorrisNein/pecapiku |
| Mistral | 0 | 不适用 | 不适用 | 无 |
| Llama | 6 | 6/6 | 0 | Hotpot doc106 |

分母为各模型三进程共234个真实业务，其中含Raw见证、域切换和epoch控制，不是通常的未来业务编译覆盖率。因此不把18/234或6/234拿去与V5 fan-out覆盖作直接比较。

全部378个预定质量配对均可用（324真实、54人工）：分数上升>0.03为0，下降>0.03为0；22个配对行有输出ID变化，全部是Raw/L0路由，集中于Qwen的PLSE_IDRR和Llama的pecapiku两个来源。配对行共享来源和输出，不能称为22个独立故障。

其中修复路径Raw witness→Raw repeat出现5个ID变化，legacy Raw重复2个；legacy Raw→修复Raw另有3个Llama变化。说明相同Prompt在本轮不同缓存/执行条件下仍有Raw行为变化，但**不证明所有差异与策略无关**。本轮没有超过0.03的质量变化，也没有已编译配对变化；完整输出与IDs保留，未删除这些Raw事件或把相同得分当严格等价。

## 5. P1：RepoBench审计结果与决定

旧真实Repo包18个Raw条件：12个旧语法拒绝，确认的上下文支持单行误拒为0。新六来源产生108个真实Raw见证条件（含两阶段、模型与重复），其中54个Repo条件：

| 模型 | Repo Raw条件 | 独立语句guard通过 | 继承Repo L0条件 | 上下文支持单行误拒诊断 |
|---|---:|---:|---:|---:|
| Qwen | 18 | 12 | 0 | 0 |
| Mistral | 18 | 6 | 18 | 0 |
| Llama | 18 | 6 | 18 | 0 |

Qwen实际语法早拒6次；Mistral/Llama的Repo L0在语法/验证之前挡住候选，不能把它们称为语法误拒。解释、包装或整段重写不能仅因抽取代码后可解析而视为合法原始续写。上下文解析只是语法证据，不证明语义正确；诊断0也不能证明此契约在所有RepoBench上完备。

Mistral的AContesini来源有6个重复条件同时具备Raw自然停止、语法通过、Raw margin及重复一致，但候选从未验证。它是一个可证伪的开发机会，**不是已经发现的错误拒绝或已证明安全的新编译资格**。本轮不据held-out放开L0、不再启动试档矩阵。Qwen非获准来源仍有candidate margin拒绝；这些不能改成放行来追覆盖。

## 6. 全费用与时延：绝对测量，不制造新加速倍率

所有业务、资格/失败、域/epoch操作均计入cell直接wall，业务/认证中没有人工工具等待slack；源packing、tokenization、server/model启动及控制器初始密钥建立在外。九单元工作流wall累计1873.208秒，资格控制器累计184.669秒，含失败及早拒；后者不是独立纯GPU执行时间。本轮也不等同原Table III的全成本配对复测。启动/清理在内的worker实际运行42.40分钟，无自动重跑。

下表每格依次为三次fresh-process；API/serial统计含每cell全部92业务，人工控制与真实请求未混称生产负载。

| 模型 | 完整微工作流wall(s) | 平均API TTFT(ms) | serial-ready p99(ms) | 全部资格controller(s) |
|---|---|---|---|---:|
| Qwen | 192.945 / 191.393 / 193.443 | 859.10 / 850.06 / 851.93 | 5776.06 / 5756.02 / 5768.75 | 119.856 |
| Mistral | 241.931 / 241.945 / 241.313 | 987.08 / 986.22 / 986.96 | 4717.34 / 4687.28 / 4704.34 | 18.866 |
| Llama | 189.876 / 191.203 / 189.158 | 817.00 / 823.09 / 816.78 | 6302.01 / 6297.74 / 6271.70 | 45.946 |

serial-ready从上一真实业务结束计入下一业务之前的资格等待，9个首请求无该时间戳，其余819请求在沿用11.7s/435ms描述性阈值下819达标。这不是新到达负载容量、硬实时保证或“p99已优化”的证据。该次要口径在启动后单列澄清，未冒称全部统计定义事前冻结。完整CSV同时给API TTFT、stream E2E、TPOT和逻辑未命中prompt tokens；tokens不换算纯GPU时间。

实际缓存池：Qwen三次1940 blocks，Mistral3550，Llama2420/2420/2419；没有假定签发证书等于永久驻留。运行中约9秒的小型既有证据元数据同步单列记录，无GPU请求、没有修改81项冻结依赖；不把本轮绝对时延当完全无主机背景活动的强性能证明。

本轮没有对收益门禁、调度或开放到达做新增优化，**不能声称修复带来新的吞吐提升或普遍p99下降**。P0有实际正向证据，Mistral真实覆盖为零和认证费用仍保留，V5较强/较弱的性能单元全部不变。

## 7. 验收、可恢复性与交付

远程后验核对81项测量依赖、父runtime和模型stat均通过，未重复复制模型或改共享runtime。原包334个普通文件，80,972,920 bytes，SHA256：

`4fb42adc91a9d060a682c26e92516b1726c1355a2eae6bdc659f77aec804dba5`

保存为三个≤32MiB分片，分片/整包/334成员SHA均通过。Windows本机在新的`.artifacts/authorization_repair_restore_v1`恢复，使用包中原始分析源码重算828业务：summary全部值、五CSV字节完全一致，全部原包成员未变。源和完整Prompt/Output IDs来自真实日志，没有重建或补造。详细命令与回执在`results/tsc_authorization_task_repair_20261019/README_zh.md`。

主要机器证据：`analysis_v1/summary_v1.json`、五CSV、`marker_token_positions_v1.json`、`post_execution_integrity_v1.json`、`local_independent_recompute_v1.json`；Repo补充为`repo_contract_CPU_audit_v1.json`和`task_funnel_posthoc_v1.json`。后两项诊断不参与在线规则；报告统计源和输出一并保留。执行状态、失败策略、预执行版本和所有不利结果保留，未重复启动或覆盖已完成实验。

## 8. 收口决定

本轮P0修复可以作为原ContractKV授权/发布闭环的实质工程补强，不增加第五项算法贡献。必须使用新可信入口；域的定义、运营者内容标签和backend访问控制仍是信任前提，旧epoch不再准入不等于擦除旧块或撤销在途请求。cache salt也不提供完整租户机密性或时序防御，详见[执行与信任矩阵](ContractKV_Authorization_Enforcement_Repair_Matrix_20261019.md)及[官方安全边界](https://docs.vllm.ai/en/latest/usage/security/)。

P1完成了审计而没有确认可修复误拒，因此保留保护和负结果；未验证候选机会留在记录，不用新独立来源反复调参。没有证据需要重做CALC/PSTP，也没有证据可宣布覆盖或开放到达性能问题全部解决。**结束本轮GPU，保留V5主实验及本轮独立补强；后续正文整合/Response Letter仍待用户安排。**
