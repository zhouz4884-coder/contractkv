# ContractKV 授权与任务资格修复：执行/决策记录

2026-10-19。本轮是用户在V5实验收口后新授权的有界修复；不重启旧自动化或旧矩阵，保留cee6f2e中的全部对照。先CPU确认缺陷，再冻结新入口与来源，最后GPU复测，不修改正文/Response Letter。

## D1：P0是实际缺陷，优先修复

旧Raw fallback省略cache_salt，compiled/verification使用policy+namespace；身份检查未贯通Raw APC。实际vLLM0.10.2的serving_chat把salt传入engine_prompt，Request保留salt，首块extra hash含salt，父块链传播到后续块；本地只读取5个实际runtime源并保存SHA，未改runtime。官方设计与当前安全边界来源见下方。

采用新统一可信控制器适配：按engine/policy/template/authorization-domain/active-epoch以HMAC派生不可猜盐值，Raw/fallback/compiled/verify全部必带。过期请求身份发送前拒绝；合法当前身份持旧compiled证书时可Raw fallback，但必须使用当前epoch盐。盐本身不负责撤销已有状态，不把直接调用内部backend的恶意客户端当已实现的公网认证防御。

历史测量源不改。新增contractkv_cache_identity与contractkv_authorized_requests供新服务入口使用；SingleShotRegistrar仅验证payload的salt表达式改变，其他AST保持，原有v5 INCOMPLETE窄修复复用，margin/EOS/输出预算/PSTP不变。

## D2：RepoBench不做无证据放宽

CPU读取旧真实Repo原包所有18个Raw条件：12个旧契约早拒，均无可确认的prefix+完整原输出合法片段。包含解释文字、[CODE_PREFIX]标签或整段重写；2条Llama条件达到length。当前数据支持保留拒绝，未证明所有理论上合法片段都会被正确接受。源码契约与next-line任务仍有一般性不匹配可能，但不能据gold片段或理论猜测把这些真实输出改判放行。

因此本轮不改one_python_statement、不扩大M/L继承L0，不承诺提升覆盖。完整输出、CODE_PREFIX、实际IDs、AST/codeop输入与原因见repo_contract_CPU_audit_v1.json。标签仅离线诊断，未参与在线。

## D3：有界GPU方案

三模型×三fresh-process=9个cell。每个引擎内保留缓存，以同一人工marker和独立真实任务比较未盐化旧路径、统一身份路径、跨域、epoch轮换、过期身份拒绝和拒绝候选零新增发布。六个独立真实来源按713已知来源排除+固定hash顺序选择；输入保真/16K、评分、margin、scope和继承档位均保持。所有物理命中、首块/后续hash、输出IDs和完整费用保留。

性能只报告该明确的顺序微工作流和冷/热状态。沿用已冻结11.7s/435ms阈值给描述性达标吞吐，不声称新的开放到达SLO容量或无隔离基线的因果速度。没有新资格实现缺陷证据时，不再开启一轮大性能矩阵。独立GPU来源仍用于检查真实任务行为/费用，不为了数值替换V5主结果。

## 外部依据（主来源）

- vLLM0.10.2设计：https://docs.vllm.ai/en/v0.10.2/design/prefix_caching.html
- v0.10.2块键源码：https://github.com/vllm-project/vllm/blob/v0.10.2/vllm/v1/core/kv_cache_utils.py
- 当前安全说明：https://docs.vllm.ai/en/latest/usage/security/ （2026-10-19读取；cache_salt不是完整隔离边界，需要可信网关/适当独立实例）。

当前阶段：CPU身份与原准入共10测试通过；新增源码复用INCOMPLETE后将重新验收。远程两3090空闲的只读观察不能替代启动前复核。下一步CPU独立来源packing/实际tokenizer，冻结完整协议和源码，再启动9单元；不能把当前CPU检查称为GPU修复成功。


## D4：GPU前发现RPC身份重复风险，保留v1并冻结v2

CPU完整路由夹具11检查通过后，静态审查发现同一引擎内legacy/authorized两次注册如果使用相同namespace和scope，会生成相同request_id/txn_id。尚无任何GPU输出。保留protocol/freeze/source_snapshot v1和所有源码，v2给两阶段独立注册namespace并让legacy compiled盐相应一致；统一授权盐不变，作用域/阈值/输入/9cell规模不变。新增CPU断言15个模拟验证RID全部唯一，11项通过。此为预执行基础设施修复，不是按结果调认证。

v2正式freeze为b67da7d3b05c08c96d0bf36c997f99570f01af6b2350bbac6c9f942f22f3c9f3。六源Hotpot doc169/106/191，Repo AContesini/Convert_PDF_to_DOCX_or_vice-versa、MorrisNein/pecapiku、lalalamdbf/PLSE_IDRR；对713既有组/728原文记录的完整context精确比对无重复，非语义去重。三模型16K、关键输入保持检查完成。分析计划在新模型输出前另行登记，明确不同工作量阶段不作公平速度倍率，所有冷/热命中与费用分别报告。

当前科学问题仍为：统一授权身份能否真正贯穿Raw/compiled和Native哈希，并保留域内合法复用及零拒绝发布。没有新的Repo误拒证据，不继续开发宽松语法规则。

## D5：保留预执行版本与事后口径的时间顺序

实际Linux预检回执在87cd23c公开后才启动GPU。次要serial-ready时延口径在启动后明确并单独存入secondary_clock_definition_v1.json：以此前真实业务结束作为下一顺序请求的ready时刻，含其间认证等待，第一请求不可用；没有重建开放到达时间戳。主要身份/块链假设、六来源、准入和停止条件均早于新输出冻结。不得将次要口径冒称全部事前注册。

2026-10-19 06:08:52–06:09:01 UTC（约9秒）补同步170项既有小型审计/CPU版本材料到远程，91项新增、没有覆盖不同内容；81项冻结测量依赖未变，无新增GPU请求。记录这次背景元数据I/O，不把本轮绝对时延当隔离于所有主机活动的硬实时性能证明。

## D6：收尾只做CPU归因，不根据独立来源结果改变资格

task_funnel_v1与report_statistics_v1是事后CPU描述性分析工具，不参与准入。将检查新108个Raw见证条件和全部828个业务记录，区分继承L0、语法、margin/自然EOS及实际候选认证；即使Raw自身稳定/语法可接受，也不能据此声称未验证候选安全，或倒调本轮held-out规则。报告分数上升、下降、输出ID/finish变化和所有length结束，人工marker单列，不合并成绝对安全保证。

保留旧V5主性能证据；本轮不同阶段业务数与缓存状态不一致，不以两阶段wall相除报告修复加速。完成九个单元后做原包SHA与全部成员验收，在本机恢复新目录、用同一归档分析源独立复算，要求summary全值及五CSV逐字节一致，再提交MD总报告/信任矩阵并归档。若出现CPU交付错误，只保留并修CPU交付，不重复已完成GPU。

## D7：实际验收与停止

9/9、828业务与后处理均exit0；无自动重跑，所有业务成功且自然停止。统一入口的跨域/新epoch各63/63首次零命中且实际hash链分离，域内四类复用各63/63；63旧身份发送前拒绝。42个修复路径编译配对0 ID/finish变化，其中真实24、人工18；93项未获准候选新增发布0。三模型人工marker三重复全部完成，没有因M/L Repo继承L0而省去其隔离控制。

新54个Repo Raw条件未确认合法单行上下文误拒。Mistral一个L0来源的6个重复Raw条件有稳定/合法/margin证据，但候选未验证，决定不据held-out倒调族档位。真实编译Q18/M0/L6；本轮不宣称覆盖普遍改善。全378配对含22行Raw ID变化、分数上升/下降>0.03均0，不将Raw变动抹除或定性为已证与策略无关。

原包SHA为4fb42adc91a9d060a682c26e92516b1726c1355a2eae6bdc659f77aec804dba5，334成员、81测量依赖。本机新目录恢复、归档分析源独立复算，summary全部值和五CSV字节一致。未改原始IDs/日志/规则，没有新GPU实验计划。完成MD报告、信任矩阵、历史记录索引及Git发布后收口；正文和Response Letter不在本轮修改。
