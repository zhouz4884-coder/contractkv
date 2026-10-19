# ContractKV：授权缓存身份的执行链与信任边界

本轮修复针对已复现的实现缺口：compiled证书拒绝之后，未携带授权缓存身份的Raw fallback仍可能复用其他域或旧epoch的原生APC。修复在新的统一可信服务入口生效；历史客户端保留为对照。实验结果与验收状态见同目录总报告，本文件说明具体实施位置和结论边界。

## 1. 统一身份链

可信控制器输入：`principal → membership → authorization domain → active epoch`。缓存盐由控制器密钥对`engine / policy / template / domain / epoch`的规范表示作HMAC-SHA256派生；同一授权共享组中的不同principal得到相同盐，不同域或epoch得到不同盐。密钥不写入测量日志。

| 环节 | 原缺口/风险 | 当前实施 | 可审计证据 | 边界 |
|---|---|---|---|---|
| 业务准入 | 客户端声称一个域不等于已经授权 | `CacheAuthority.bind`检查受信任的membership及当前epoch | CPU缺失/伪造/越权/旧epoch控制 | membership来自可信控制器配置；没有实现公网用户认证或完整IAM |
| Raw与fallback | 旧入口省略salt，绕开compiled域约束 | `authorized_business_generate`在派发前`require`，无默认无盐fallback | 实际wire salt、完整Prompt IDs、native lookup日志 | 必须使用新入口并禁止不可信方直接访问内部引擎；保留旧入口不意味着部署已自动迁移 |
| Compiled业务 | salt与Raw不一致，授权检查和物理键分离 | 与Raw使用同一有效CacheIdentity，同时保留现有证书绑定检查 | 同组第二principal、实际命中及证书检查 | 盐不能代替行为资格、证书scope或候选合法性 |
| GPU验证/PSTP | 验证发布的键必须与后续读取一致 | `AuthorizedRegistrar`仅替换验证payload的salt表达式 | 除该表达式外注册AST一致；实际验证RPC与发布事件关联 | 复用现有INCOMPLETE窄修复；不改变margin/EOS/行为scope/PSTP |
| vLLM原生APC | HTTP字段存在不证明进入块键 | 实际0.10.2 V1 runtime将salt传入Request，纳入首块extra key并沿父块hash传播 | 五份实际runtime源码SHA、同Prompt跨域整条block-hash链与命中 | 没有修改共享runtime；其他版本/入口需另行验证 |
| 生命周期 | 拿旧身份或旧证书进入新epoch | 派发前拒绝旧请求身份；有效当前身份持旧证书则走当前epoch盐的Raw | stale identity事件、跨epoch首次0命中及本epoch重复 | 不擦除旧块，不取消已准入/在途工作，不实现跨控制器的持久撤销服务 |
| 拒绝候选 | 验证失败仍污染共享发布 | 保留fail-closed事务边界 | `committed_tokens=0`且无对应新增发布事件 | 错ACK/NACK候选是定向拒绝控制，不冒充CALC合法布局的必要性消融 |

主要源码：`scripts/contractkv_cache_identity.py`、`scripts/contractkv_authorized_requests.py`。冻结测量入口：`scripts/tsc_repair_authorized_client_v2.py`。旧协议及先前V5数据不改写。

## 2. 必须保留的信任假设

1. **授权域必须与实际可共享Native APC状态的信任组一致。** 新入口会对整个请求的原生缓存键加盐，不自动把同一请求中的私有后缀变成另一个共享边界。同域请求仍可能观察到域内重复前缀的命中差异。
2. **Manifest的内容标签仍由可信运营者负责。** 哈希证明字节身份，不能证明内容不私有；本轮人工marker故意被运营者声明为可共享，修复不会把它识别为秘密。
3. **Backend是内部可信接口。** vLLM接收salt不等于它知道调用者应属于哪个授权域。salt归属、不可任意选择及生命周期检查由可信入口保证，不能让不可信调用方绕过入口。
4. **逻辑命名空间隔离不是完整机密性。** 本轮不提供时序信道防御、进程/显存安全证明、所有共享资源的拒绝服务隔离或硬实时保证。需要更强隔离时仍应采用适当的独立引擎/实例及系统安全措施。
5. **行为认证保持原有有限作用域。** 同域盐相同只表示允许共享Native APC，不授权未见query/observation跨越行为scope。超出资格仍须Raw，不用提高覆盖为由放宽margin或EOS。

上述边界与[vLLM 0.10.2前缀缓存设计](https://docs.vllm.ai/en/v0.10.2/design/prefix_caching.html)及[官方安全说明](https://docs.vllm.ai/en/latest/usage/security/)一致：缓存盐帮助区分共享组，不能替代完整的租户安全边界。实际runtime另存SHA，官方网页不替代实际执行代码的证据。

## 3. RepoBench资格审计的处理

旧真实Repo包18个Raw条件中，12个旧语法早拒没有发现可以确认的合法上下文续写误拒；解释文字、标签或整段重写不能仅因代码块内部可解析而放行。一般next-line片段与独立完整语句契约存在潜在不匹配，但不能由此把全部真实拒绝判为错误。

本轮保持`one_python_statement`、Mistral/Llama既有RepoBench L0、Raw/candidate/EOS margin不变。新增独立来源的Raw输出仅作事后CPU诊断；即使存在语法合法且Raw重复稳定的L0条件，也不等于重排候选已通过认证。任何潜在机会都必须与实际已验证的合法编译请求分开报告。

## 4. 实验能回答什么

九个fresh-server单元覆盖三个模型各三次重复；每个引擎内不清缓存，先后测试旧路径与修复路径，保存实际Prompt/Output IDs、物理命中、块hash、发布/拒绝与完整业务/认证费用。真实任务为六个与既有来源不重叠的新来源，人工marker另列；重复租户/进程不是新的独立来源。

这是一项授权闭环修复验证。两阶段请求数及先后缓存状态不同，绝对wall不构成公平的修复加速倍率；它也不是开放到达SLO容量实验。已有V5主性能结果继续独立保留，不由本轮控制替代。
