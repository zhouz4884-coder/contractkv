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
