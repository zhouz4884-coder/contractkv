# 第二阶段完成审计清单

截至2026-10-19 23:28（香港时间）：**目标尚未完成**。本清单将完整目标保留为逐项交付要求，不以开发通过、正式启动或进程存活代替最终实证。

| 要求 | 可证明完成的证据 | 当前判断 |
|---|---|---|
| 保留原部署见证语义，额外审计Raw配对 | `P0_source_audit_v2.json`、compiled canary日志、配对质量CSV | P0/P1完成；正式配对待全部单元 |
| 真实任务、明确授权重复场景 | `protocol_v2.json`、`serving_measurement_contract_v1.json`、原始/保真输入与裁剪ledger | 已冻结；明确为固定问题的受控模板服务，非生产trace |
| 新开发与独立正式来源 | 4开发/6正式来源、729历史排除清单、`source_context_overlap_audit_v2.json` | CPU审计通过；无完全相同上下文，不声明语义独立 |
| 三模型开发与资格门槛 | 每模型52生成、原包SHA、本地独立复算、`development_catalog_v1.json` | 完成156生成；Qwen/Mistral仅QA合格，Repo保持Raw，Llama不运行正式 |
| 保留所有不利结果 | Mistral Repo/Llama QA的开发掉分，原包及失败日志 | 已保留；不把部署自路径认证描述为Raw等价 |
| Raw-only标定，不用正式Contract结果定负载 | 两个fresh-server各80请求，远程及本地`calibration_*audit_v1.json` | 完成160请求；公式、实际速率与SLO全部冻结 |
| Raw/Session/Template同栈同内容同缓存授权组 | 服务客户端/authority源码、GPU AST证明、冻结job、P1实际引擎salt/命中审计 | 设计与P1完成；正式各请求的输入/回执/物理命中待P3核验 |
| Session/Template仅改变认证对象及次数 | 同canonical compiled canary、同L3、同共享cache组、允许两路读取已认证prefix | 已冻结；实际对象数/RPC/失败费用待P3汇总 |
| 注册、失败及生命周期检查纳入费用 | 全局epoch在注册前，原计划到达不后移，direct wall与Controller记录 | 客户端与计时CPU检查通过；正式逐行时间恒等式待P3 |
| 同GPU/同到达/三重复正式对照 | Qwen18、Mistral9，6模板×8tenant×8业务；同模型/重复三臂同物理GPU | 已完成18/27单元、6912业务全部成功（Qwen15/18、Mistral3/9）；第十波启动；worker770907已核查真实`/proc`命令，未重启 |
| 真实用户时延与SLO | 计划到达TTFT/E2E，绝对Goodput/达标率；完整wall仅辅助 | 指标已冻结；无最终结果 |
| 真实物理工作与资格额外工作 | 引擎initial prefix hit、prompt-hit新prefill、canary/verification额外prefill | 待P3完整核算；不换算为GPU kernel时间 |
| 来源及重复不确定性 | 三独立进程配对bootstrap、6来源条件敏感性、leave-one-source | 计算程序已准备；不得把tenant重复当独立安全样本 |
| 全部正式单元原包与独立分析 | `formal_exit_v1.json`成功、27 completion、10368业务、源/数据SHA | 尚未完成；当前属于经核实的运行等待 |
| 独立本地复算 | 新目录恢复、173冻结文件、summary与4 CSV逐字节相同、原成员不变 | 待正式原包完成 |
| MD总报告及科学结论选择 | 方法、结果、费用、质量、负结果、适用边界、可支持/不支持的主张 | 待P3完成后撰写；不能先承诺服务加速成立 |
| Git归档与远程SHA | 数据分片、源代码、文档commit；逐对象/tree/commit核对远程main | 正式协议/回执与开发已归档；最终数据待交付 |
| 不改正文/Response Letter、不扩分支 | 本轮提交范围及最终工作区审计 | 保持；完成预定矩阵后收口 |

正式worker和CPU后处理是两个独立进程。CPU后处理PID774981只等待现有正式worker退出，再分析/归档，不发新GPU请求。任何观察超时均不视为worker死亡；只有真实终态/缺失句柄经复查才处理故障。

最终只有上述所有必要交付完成且证据足以证明时，才能把goal标为complete。若正式结果中性或负面，依然交付完整结果；不换来源、SLO、负载或减少已冻结单元来改变结论。
