# ContractKV Trust Model / Enforcement Boundary Matrix

状态：已有源码、9个注册CPU案例和19个客户端绑定检查已核对；新冻结Manifest GPU闭环仍待运行。本表不把静态检查计为在线隐私证据。最终实际分母须由该批completion与native trace填入。

## 受信任的执行边界

当前原型由受信任的内部编排器构造manifest、运行HMAC/Scope检查并向内部vLLM服务发送请求。服务运营者决定内容是否稳定、是否允许域内共享；控制器持有签名密钥与模型/版本配置。本文中的“未授权请求被拒绝”限于经过该控制器的路径。原型没有公共IAM代理，也没有实现可对抗直接调用内部推理端点的恶意租户网关。

模板资格对象、行为见证与物理KV前缀是相关但不同的对象：身份与声明检查决定共享资格，行为认证决定候选是否得到本次证据支持，PSTP决定候选块何时可见。某个guard拒绝compiled路由，不等于整个推理引擎不保存任何Raw缓存。

## 检查与实际实施位置

| 对象/检查 | 实施位置与输入 | 失败后的动作 | 当前证据 | 未覆盖风险 |
| --- | --- | --- | --- | --- |
| 注册主体与角色 | `tsc_revision_registration_audit.registration_errors` 检查可信issuer与调用者传入的operator角色 | 控制器拒绝共享注册；合成live adapter另走真实Raw fallback | 既有CPU角色/伪造身份案例；新GPU尚待 | 角色来自受信任编排器，不是HTTP调用者身份认证系统 |
| Manifest签名 | 同helper对规范化manifest执行HMAC-SHA256校验 | 拒绝注册 | CPU签名/旧签名版本案例 | 不证明声明内容公开、非敏感；不实现密钥分发/轮换服务 |
| Segment身份与字节 | 检查ID非空/唯一、SHA256与声明文本一致 | 拒绝注册 | CPU字节/哈希不匹配 | 正确哈希无法发现语义上错误的公开性标签 |
| 显式PRIVATE/MUTABLE共享冲突 | 对`publish`与`stable`/`tenant_private`声明组合检查 | 拒绝共享注册 | CPU显式冲突；冻结live路径覆盖三类拒绝 | 依赖正确标注，不能识别可信运营者重新声明为public/stable的私有文本 |
| 授权域与模板版本完整性 | Helper要求非空domain/version；签名覆盖原声明 | 缺失或旧签名不匹配时拒绝 | 既有CPU案例 | 不是跨组织权限目录，也不从文本推断归属 |
| Binding签名 | `contractkv_certificate_binding.validation_errors`，由现有`issue_binding/check_binding`调用 | 控制器不走compiled | 既有19项客户端检查；新live adapter直接调用这些原函数 | HMAC由可信客户端核验，内部backend不构成公共签名证书网关 |
| 模型/tokenizer/runtime/generation/policy身份 | Binding字段逐项与当前RequestBinding比较 | 不匹配时Raw | CPU各字段篡改检查；新运行另记录实际加载源/实际Prompt IDs | 不能把客户端提供的identity字符串当作独立远程硬件证明 |
| Tenant与授权域 | 现有服务模板`issue_binding/check_binding`均使用`tenant_id="*"`，并核对authorization_domain | 域不符时不走compiled | CPU wildcard语义与域检查；冻结live含跨域请求 | `*`表示已配置域内共享，不实施逐tenant身份鉴别；其他入口绕过控制器不在该保证内 |
| 模板epoch/过期 | 比较service_template_epoch；`current_epoch > expires_at_epoch`拒绝 | 控制器不再复用该资格 | CPU生命周期检查；live stale-version为epoch不匹配 | epoch是服务版本计数，不是已实现的墙钟密钥过期/撤销服务；拒绝后续使用不等于擦除已有物理KV |
| 稳定前缀与布局身份 | Binding核对stable_prefix_hash/layout_hash；实际候选由完整Prompt IDs形成 | 身份不匹配时Raw | CPU身份检查；新GPU将核对真实提交与后续hit | 哈希只证明字节身份；不说明所有相同字节均可跨域共享 |
| 私有后缀排除 | RequestBinding含`private_suffix_excluded`布尔声明 | 声明false时拒绝 | CPU声明检查 | 布尔值来自可信编排器。误标场景故意声明true，不能写成模型或哈希自动完成隐私检测 |
| Observation行为作用域 | 新冻结机制adapter另核对实际raw messages、候选IDs和预算派生的精确scope | 不匹配时Raw，即使公共prefix/HMAC仍匹配 | GPU前source-function检查；不同ALPHA/BETA实际请求尚待 | 本诊断是精确observation条件；不能外推任意动态输入或自动协议切换 |
| Raw见证完整性与margin/EOS | 现有SingleShotRegistrar及strict backend核对实际业务见证、候选逐token与terminal-stop证据 | 不完整、margin不足或错误时拒绝；接口不确定另列 | 既有strict自由生成审计；新五类机制数据待完成 | 有限见证不是开放输入分布的普遍正确性证明；行为保持不等于任务答案正确 |
| PSTP发布边界 | 真实backend仅对PASS候选注册`floor(min(stable-end,computed)/block-size)`完整前缀 | FAIL/INCOMPLETE/CANCELLED候选不新增共享提交 | 既有Phase16R/17/18真实故障记录；新live/native trace待完成 | 指候选新增状态；不清除已有公共块或Raw APC，不承诺所有并发交错的形式证明 |
| Native前缀驻留与命中 | 实际vLLM lookup/block链/前缀计数，不由签名或登记状态推断 | 丢失/部分驻留时可能重算 | 既有驻留审计；新Manifest实际marker覆盖待完成 | 已签资格不保证物理块始终完整驻留，token节省不等于纯GPU时间 |
| 默认Raw APC | 保持原客户端`cache_salt=None`，真实fallback照常发送 | 允许backend按原生规则命中已有相同Raw前缀 | 新冻结协议明确保留，实际结果待完成 | compiled被拒不意味着Raw零命中、整引擎保密或跨域Raw状态清除 |
| 时序侧信道 | 当前原型未实施专门防御 | 不适用 | 无防御实测，不声称已解决 | 即使域授权/状态隔离成立，域内prefix-hit时延推断仍可能存在；不提供前缀缓存时序信道防御 |

## 已有CPU分母与新GPU验收分开

原注册CPU共9例：7例拒绝、有效公开声明与可信误标各1例接受。误标被接受是信任边界的观测，不是遗漏的拒绝案例。已有客户端Binding共19项检查，拒绝17项，合法条件及改变具体tenant但保留wildcard授权语义各1项接受。这些计数不证明任何GPU块已发布或被拒。

新Manifest与行为机制共用9个fresh-model进程。每进程Manifest最多15次真实业务生成、2次认证；实际GPU RPC数、PSTP提交数、明确拒绝/不确定响应以及后续native命中必须从运行结果分别统计，不能预先填为18次成功认证或“零隐私泄漏”。

只使用合成ALPHA/BETA私有标记。正确声明与可信误标两条件均保留。验收须核对：获准prefix实际detokenize内容、native提交/命中块链、跨域/旧版本/不同observation的真实路由，以及Raw fallback是否复用默认APC。任何可信误标导致的真实共享提交都要保留。

源码位置以新诊断`source_snapshot`为准，字节承诺为 `freeze_v3.json`（SHA `7170c9101903326c582bc32e93ca2e4d7998b42b8fc5a8bb62c7d158ed8dd4ff`）及已有后端依赖补充清单。静态索引为 `results/tsc_final_existing_evidence_CPU_20261018/trust_source_boundary_index_v1.json`，其中不含运行密钥。最终GPU数量与实际边界尚待追加，本文暂不作为已完成的在线安全报告。
