# 可选机制研究：自主决策记录

## D1：先关审稿实证清单，再使用 GPU

原信逐条核查与已有实际证据对齐后，没有发现待执行的必做 GPU 单元。18 份共同 HotpotQA 请求文件重新核 SHA、配对和 CI 均通过；原 RULER 已单独复核。写作/引用/表图交付仍待做，不把它们记为实验未完成。

## D2：纠正 CI 研究对象混淆

旧证据表将 HotpotQA 的 5.242% 零 slack CI 写在 RULER CI 行。新增优先级审计将其明确拆开，不修改原数据、bootstrap 单位或模型。审稿实验核验已先推送 `5d2c7e9`。

## D3：探索默认放附录，不再开正式大矩阵

采用两模型六臂、每臂一进程的开发机制对照。旧验证来源已经打开，本轮明确将其降为已知开发诊断来源，保留全部三个 QA 的 12 个 scope 条件以及 Repo L0，不能声称新 held-out 泛化。四次访问而非原八次访问，只在本轮同条件比较，不能与旧倍率直接相除。

## D4：先做可回收优先级，不做永久 pin / 预取 / 新收益预测器

保留真实 pool、引用计数与分配能力。75%预算、120s TTL、group FIFO 事前固定，分配压力下允许回收。增加 Raw 的相同策略对照，任何通用缓存收益单独报告。不改行为门槛或 CALC，不宣称新的资源管理算法贡献。

## D5：融合必须用实际 Decode/EOS，不借 Raw 输出伪造 Candidate

EngineCore 在释放前收集真实 Candidate token、rank、top-2 logprobs 和终止状态；原 native verifier 从这些实际 decode 行视图检查原门槛，再按原 PSTP 提交。跨进程返回真实 Candidate Prompt/Output IDs，ExactBehaviorLedger 仍独立核验 Raw/Candidate 一致。TF-only 单列为缺少资格阶段自由生成证据的探索对照。

## D6：预执行补上取消/重复发布检查，保留 v1

v1 冻结和 CPU 预检通过，但尚无 GPU 推理。为避免只检查正常完成路径，在任何 GPU 运行前单列 v2：只增加 native release 观察与辅助控制，不改主矩阵、样本、门槛、任务预算、访问次数或评分。

辅助控制在已有两个 Fused 单元的主服务计时结束后、同一引擎中执行：wrong-answer、wrong-EOS、timeout、cancel、同时重复 ID、完成后重复事务；每模型最多7次 HTTP/取消发送和8次读取探针。独立账本记录全部费用，保留原主服务 wall，原始 trace 按 request ID 区分。取消/失败必须结合释放时块状态和后续真实物理命中审核，不能只看客户端异常。

v1 无 GPU；旧 freeze/preflight 原样保留，不覆盖。正式执行使用 `freeze_v2` / `preflight_v2` / `worker_v2`，SHA256 `02c19f6592f44733f39a8bbececa2e81a2d3de567cfb94de78a89d5ac5c0a2b2`。

## D7：模型和运行时身份必须反映这次隔离副本

两模型沿用已登记完整 SHA 的全部 asset，并在预检检查 size/mtime。原 runtime 清单与源保持一致，复制后只补丁5个源文件；新 identity 将 runtime_revision 绑定到本次真实完整清单，保留 parent_revision。无共享 runtime 修改。

v2 CPU 导入预检 PASS，回执 SHA256 `cee9f1ace6b66917762629c874701f321aacda91947857a8570325317f8f7b9e`。另18项现有精确行为/前缀/授权 pytest 通过，6项新 Decode/队列 unit 检查通过；不把 CPU 检查称作 GPU 性能或事务发布结果。
