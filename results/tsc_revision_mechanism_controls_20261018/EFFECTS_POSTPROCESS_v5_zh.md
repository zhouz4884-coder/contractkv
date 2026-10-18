# 行为分母分析的 CPU 键冲突修正

原9单元已经全部完成，855次正式业务生成，另有63次失败尝试业务保留。原 `analysis_v3` 已成功核对实际Prompt IDs、后端源码、PSTP及Manifest native命中；不重跑该分析或任何GPU单元。

后续 `effects_summary_v4` 在构建 `(cell, case_id, condition)` 字典时，将不用于行为对照的Manifest注册回退也纳入。三个不同注册namespace使用相同Manifest case和fallback condition，因此键冲突触发断言；不是生成重复、没有丢失业务，也没有观察到认证或发布失效。该CPU失败发生在输出目录创建之前，日志保留。

新 `effects_summary_v5` 仅将冻结的20个behavior case纳入该行为字典，完整保留720次行为业务及原180个候选；135次Manifest业务继续由已经成功的原analysis_v3单独分析。明确断言720/135分母，不按任务分数、PASS或输出筛选。其他分组、评分、费用与拒绝分母逻辑不变。

归档入口改为 `tsc_revision_mechanism_package_v6.py`，读取effects_v5，并同时保存v4失败分析源与日志。原GPU执行与归档版本仍按v5记录，科学数据不变。新增GPU请求为零。
