# 第二阶段完成审计清单

截至2026-10-20 03:25（香港时间）：**原定实验、独立复算和MD报告均已交付，数据/代码/报告归档已在远程核验。** 科学假设并未全部成立；“完成实验”不表示取得零退化保证。

| 原定要求 | 当前可复核证据 | 判断 |
|---|---|---|
| 核对原部署见证语义，额外测量Raw配对 | `P0_source_audit_v2.json`；原始reference/business记录；`paired_quality_v1.csv` | 完成。见证来自compiled路径，不能称任意未来Raw等价证明 |
| 保真真实任务与明确重复服务场景 | `protocol_v2.json`、`serving_measurement_contract_v1.json`、原始/渲染输入、裁剪ledger | 完成。保护完整问题/CODE_PREFIX/空白；超窗可选上下文按gold无关规则裁剪，非生产trace |
| 新开发/正式来源与排重 | 4开发/6正式来源；729历史排除；`source_context_overlap_audit_v2.json` | 完成。无完全相同上下文，不声称语义独立 |
| 三模型P1可行性及前瞻门槛 | 各52生成、三份本地独立复算PASS、`development_catalog_v1.json` | 完成156生成。Qwen/Mistral仅QA族合格，Repo全Raw；Llama未合格，不运行正式矩阵 |
| 保留所有开发不利结果 | 原包、三模型pairs/registrations/native CSV | 完成。Mistral Repo及Llama QA各6次开发掉分保留 |
| Raw-only标定并冻结负载/SLO | 两模型各80成功请求；`calibration_local_independent_audit_v1.json` | 完成160请求，未用正式Contract结果选参数 |
| 三臂同栈、同内容、同授权共享关系 | 冻结job/输入；`formal_cache_partition_audit_v1.json` | 完成。每单元6组×64请求×8tenant，三臂分组相同；salt字节因fresh密钥轮换，不称跨服务器字节相同 |
| Session/Template仅改变资格单位 | 同canonical L3 canary/模型/评分/共享权限；实际registration/RPC日志 | 完成。每单元24→3对象/RPC，双方均允许合法canary缓存与certified-prefix读取 |
| 首注册、失败、生命周期与排队费用入账 | 从注册前epoch计时；实际时钟恒等式；所有cell drain | 完成。零slack，从原计划到达计TTFT；模型启动在client epoch外，日志另存 |
| 完整正式矩阵与三重复 | `formal_exit_v1.json`=0；27 completion；`formal_execution_audit_v1.json` | 完成Qwen18、Mistral9，共10,368业务，全部正常返回，无自动重跑 |
| 同GPU与无混跑测量 | 27实际launch、稳定设备UUID映射、12,524份资源快照 | 完成。同模型/重复使用同一CUDA设备序号；快照未发现其他GPU进程 |
| 真实物理命中与额外验证工作 | 原始Native事件、注册/验证请求；cells与registrations CSV | 完成。3,456编译请求：完整命中3,363、部分1、零命中92；额外prefill全计入 |
| Raw质量、Token IDs和终止配对 | 6,912配对、完整文本/IDs、`formal_quality_diagnostics_v1.json` | 测量完成。1,178个编译ID/终止变化、36次编译掉分；严格Raw保持/零退化假设未成立 |
| 正负变化对称报告与来源聚类 | 全路由811上升、46下降；来源表、6个独特下降请求条件 | 完成。36编译下降均为Mistral doc107；10个其他下降为L0，全部保留 |
| 终止预算核对 | 全量finish_reason与实际输出长度 | 完成。10,368均为stop，无输出预算上限事件；不外推无限输出 |
| 不确定性与来源敏感性 | 冻结三进程5000 bootstrap、六来源条件敏感性/去一来源 | 完成。来源敏感性固定已观察wall；非反事实工作负载CI，重复tenant非独立安全样本 |
| 完整原包与安全恢复 | 原包SHA `2090b699…58a54`、1,140成员、11分片 | 完成。失败/不利数据保留，无模型或runtime二进制拷贝 |
| 独立本地重算 | `formal_local_independent_recompute_v1.json` PASS | 完成。27单元/10,368业务，summary与4 CSV逐字节相同，全部原始成员未变 |
| 本地恢复故障保留 | `formal_local_restore_failure_v1.json`；原失败目录 | 完成。271字符路径失败后，仅换到最长242字符的`.artifacts/f2`；同一原包/程序通过，无GPU重跑 |
| CPU补充诊断与证据强度 | 三份post-hoc诊断脚本/JSON | 完成。标为事后只读诊断，不冒充事前冻结检验，不改评分、阈值、来源或纳入条件 |
| MD总报告与主张选择 | `docs/ContractKV_Task_Bearing_Template_Service_Validation_Report_20261019.md` | 完成。服务/摊销正向，Raw保持失败与来源效用明确；未以均分掩盖局部下降 |
| Git原包/代码/文档与远程SHA | `formal_final_data_publication_v1.json`、`formal_completion_receipt_v1.json` | 完成。数据及报告提交`1f05ce502c9f5827cae36aea64b6a0aaea65caa5`，43新对象及tree/commit精确核对；无force更新 |
| GPU释放及无新增研究线 | worker退出0，GPU compute列表空；CPU后处理结束 | 完成。未改正文/Response，未追加GPU矩阵；原有不相关工作区改动保留 |

与全任务目标分开判断的科学结果：本轮支持固定问题授权模板服务的资格摊销与服务收益，不支持“该部署见证对任意未来Raw行为等价”或“编译子集零掉分”。这些失败属于必须报告的实验结果，不以文字改写成成功。

数据/代码/报告已归档至上述提交；本清单和完成回执作为其后续元数据提交。该数据提交相对本阶段起点`2fa4eb79576b`的928个变更路径已检查，全部在Task实验、数据、测试、实验文档及`.gitattributes`范围内，正文与Response未修改。GPU已释放，不追加实验。
