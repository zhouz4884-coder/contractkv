# ContractKV Trust Model / Enforcement Boundary Matrix

**2026-10-19后续修复索引：** 下表保留V5历史测量及其无盐Raw缺口，不能当作新入口的当前状态。用户随后授权的统一缓存身份修复已完成三模型×三重复、828业务及原包独立复算；新入口跨域/新epoch各63/63首次Raw为0命中，同域复用保留。实施位置和仍需信任的边界见[新执行矩阵](ContractKV_Authorization_Enforcement_Repair_Matrix_20261019.md)，结果及全部限制见[修复报告](ContractKV_Authorization_Task_Repair_Report_20261019.md)。旧入口留作对照，未声称所有部署自动迁移或完整机密性。

状态：9个fresh-model单元、855次正式业务及本地独立复算已完成；额外63次失败尝试业务保留。Manifest有135次业务、18次实际认证RPC、72次后续控制请求。已有9个注册CPU案例和19项绑定检查继续单列，不当作135个GPU业务的一部分。

## 受信任的执行边界

当前原型由受信任的内部编排器构造manifest、运行HMAC/Scope检查并向内部vLLM服务发送请求。服务运营者决定内容是否稳定、是否允许域内共享；控制器持有签名密钥与模型/版本配置。本文中的“未授权请求被拒绝”限于经过该控制器的路径。原型没有公共IAM代理，也没有实现可对抗直接调用内部推理端点的恶意租户网关。

模板资格对象、行为见证与物理KV前缀是相关但不同的对象：身份与声明检查决定共享资格，行为认证决定候选是否得到本次证据支持，PSTP决定候选块何时可见。某个guard拒绝compiled路由，不等于整个推理引擎不保存任何Raw缓存。

## 检查与实际实施位置

| 对象/检查 | 实施位置与输入 | 失败后的动作 | 当前证据 | 未覆盖风险 |
| --- | --- | --- | --- | --- |
| 注册主体与角色 | `tsc_revision_registration_audit.registration_errors` 检查可信issuer与调用者传入的operator角色 | 控制器拒绝共享注册；合成live adapter另走真实Raw fallback | 既有CPU角色/伪造身份案例；live三类注册拒绝各9次，共27次，后端对应新增提交0 | 角色来自受信任编排器，不是HTTP调用者身份认证系统 |
| Manifest签名 | 同helper对规范化manifest执行HMAC-SHA256校验 | 拒绝注册 | CPU签名/旧签名版本案例 | 不证明声明内容公开、非敏感；不实现密钥分发/轮换服务 |
| Segment身份与字节 | 检查ID非空/唯一、SHA256与声明文本一致 | 拒绝注册 | CPU字节/哈希不匹配 | 正确哈希无法发现语义上错误的公开性标签 |
| 显式PRIVATE/MUTABLE共享冲突 | 对`publish`与`stable`/`tenant_private`声明组合检查 | 拒绝共享注册 | CPU显式冲突；live PRIVATE、MUTABLE、非operator三类共27次拒绝 | 依赖正确标注，不能识别可信运营者重新声明为public/stable的私有文本 |
| 授权域与模板版本完整性 | Helper要求非空domain/version；签名覆盖原声明 | 缺失或旧签名不匹配时拒绝 | 既有CPU案例 | 不是跨组织权限目录，也不从文本推断归属 |
| Binding签名 | `contractkv_certificate_binding.validation_errors`，由现有`issue_binding/check_binding`调用 | 控制器不走compiled | 既有19项客户端检查；live实际调用原函数，跨域/旧epoch各18次拒绝compiled | HMAC由可信客户端核验，内部backend不构成公共签名证书网关 |
| 模型/tokenizer/runtime/generation/policy身份 | Binding字段逐项与当前RequestBinding比较 | 不匹配时Raw | CPU各字段篡改检查；9单元加载源与855业务实际Prompt IDs经过冻结预检匹配 | 不能把客户端提供的identity字符串当作独立远程硬件证明 |
| Tenant与授权域 | 现有服务模板`issue_binding/check_binding`均使用`tenant_id="*"`，并核对authorization_domain | 域不符时不走compiled | CPU wildcard语义与域检查；18次同域compiled，18次跨域拒绝compiled | `*`表示已配置域内共享，不实施逐tenant身份鉴别；其他入口绕过控制器不在该保证内 |
| 模板epoch/过期 | 比较service_template_epoch；`current_epoch > expires_at_epoch`拒绝 | 控制器不再复用该资格 | CPU生命周期检查；live旧epoch18/18拒绝compiled | epoch是服务版本计数，不是已实现的墙钟密钥过期/撤销服务；拒绝后续使用不等于擦除已有物理KV |
| 稳定前缀与布局身份 | Binding核对stable_prefix_hash/layout_hash；实际候选由完整Prompt IDs形成 | 身份不匹配时Raw | CPU身份检查；18/18授权匹配请求完整命中提交前缀，native block-hash链一致 | 哈希只证明字节身份；不说明所有相同字节均可跨域共享 |
| 私有后缀排除 | RequestBinding含`private_suffix_excluded`布尔声明 | 声明false时拒绝 | CPU声明检查 | 布尔值来自可信编排器。误标场景故意声明true，不能写成模型或哈希自动完成隐私检测 |
| Observation行为作用域 | 新冻结机制adapter另核对实际raw messages、候选IDs和预算派生的精确scope | 不匹配时Raw，即使公共prefix/HMAC仍匹配 | live不同ALPHA/BETA共18次精确scope拒绝；正确声明的9次仅scope拒绝也足以阻止compiled | 本诊断是精确observation条件；不能外推任意动态输入或自动协议切换 |
| Raw见证完整性与margin/EOS | 现有SingleShotRegistrar及strict backend核对实际业务见证、候选逐token与terminal-stop证据 | 不完整、margin不足或错误时拒绝；接口不确定另列 | 既有strict审计；本批180候选中102次实际行为变化全拒绝，获准78次后决策生成0分歧 | 有限见证不是开放输入分布的普遍正确性证明；行为保持不等于任务答案正确 |
| PSTP发布边界 | 真实backend仅对PASS候选注册`floor(min(stable-end,computed)/block-size)`完整前缀 | FAIL/INCOMPLETE/CANCELLED候选不新增共享提交 | 既有Phase16R/17/18故障；本批拒绝新增发布0，全部实际提交为block-aligned前缀 | 指候选新增状态；不清除已有公共块或Raw APC，不承诺所有并发交错的形式证明 |
| Native前缀驻留与命中 | 实际vLLM lookup/block链/前缀计数，不由签名或登记状态推断 | 丢失/部分驻留时可能重算 | 既有驻留审计；Manifest同域18/18完整命中，9个可信误标条件实际发布含合成marker前缀 | 已签资格不保证物理块始终完整驻留，token节省不等于纯GPU时间 |
| 默认Raw APC | 保持原客户端`cache_salt=None`，真实fallback照常发送 | 允许backend按原生规则命中已有相同Raw前缀 | live跨域及旧epoch回退各18次原生Raw命中覆盖合成私有marker | compiled被拒不意味着Raw零命中、整引擎保密或跨域Raw状态清除 |
| 时序侧信道 | 当前原型未实施专门防御 | 不适用 | 无防御实测，不声称已解决 | 即使域授权/状态隔离成立，域内prefix-hit时延推断仍可能存在；不提供前缀缓存时序信道防御 |

## 已有CPU分母与新GPU验收分开

原注册CPU共9例：7例拒绝、有效公开声明与可信误标各1例接受。误标被接受是信任边界的观测，不是遗漏的拒绝案例。已有客户端Binding共19项检查，拒绝17项，合法条件及改变具体tenant但保留wildcard授权语义各1项接受。这些计数不证明任何GPU块已发布或被拒。

Manifest与行为机制共用9个fresh-model进程。Manifest实际135次业务、18次RPC/18次获准发布、27次注册拒绝控制及72次后续请求；没有不确定响应。正确声明9个条件发布前缀均不含marker；可信operator误标的9个条件均实际发布含marker前缀。这不是“零隐私泄漏”的证明。

只使用合成ALPHA/BETA私有标记。正确声明与可信误标两条件全部保留。获准prefix实际detokenize、native提交与后续block-hash链、跨域/旧epoch/不同observation真实路由均已核对。同域匹配18/18 compiled；不同值、跨域、旧epoch各18/18 Raw。跨域和旧epoch合计36次Raw回退命中覆盖marker；不把compiled拒绝写成整引擎Raw状态隔离，也不将缓存字节可见性当作已经执行的外泄/时序攻击。

源码位置以新诊断`source_snapshot`为准，字节承诺为 `freeze_v3.json`（SHA `7170c9101903326c582bc32e93ca2e4d7998b42b8fc5a8bb62c7d158ed8dd4ff`）及已有后端依赖补充清单。静态索引为 `results/tsc_final_existing_evidence_CPU_20261018/trust_source_boundary_index_v1.json`，其中不含运行密钥。原始归档SHA39b2ad426f101602bed6706d1d5866665355cde3c8f3b84915c90eca1a7a3c1f，254成员双端核对；本地重算summary及四CSV完全一致。详见tsc_revision_mechanism_manifest_results_20261018_zh.md。本文是受信任内部路径的实际边界报告，不是公网多租户安全保证。

## 本轮收口核验（2026-10-19）

上表对应的135次Manifest实际业务与全部失败记录已原包恢复并独立复算；第四/五批服务完成不会扩大这里的安全边界。新服务的运行时、IDs、RPC、PSTP与native账本另在37单元原包和本地复算回执中，不能把其零编译分歧当作隐私或时序防御。可信operator误标9/9发布、跨域/旧epoch Raw原生命中均作为正式不利证据保留。后续必须据此写正文安全小节，不能只藏入补充材料；不需要再开GPU隐私研究线。
