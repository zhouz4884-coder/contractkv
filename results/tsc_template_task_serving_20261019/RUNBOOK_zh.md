# Task-Bearing Template Service Validation：恢复入口

任务未完成：正式27单元运行中，P3分析、原包、本地独立复算及MD总报告仍须完成。不要把启动或开发通过当最终结果。

## 已完成

- 用户最新方案：Qwen18正式单元，Mistral条件性9；Llama开发不通过不运行正式。六来源×8注册tenant identity×8未来请求，384业务/单元，共10368业务。
- 开发3模型各52生成，全部已独立复算。Qwen/Mistral仅HotpotQA合格，Repo全部Raw fallback；Llama无合格家族。Mistral Repo和Llama QA的开发掉分全部保留。
- Raw-only fresh-server两模型各80成功；远程/本地审计通过。Qwen率0.3159078191，负载0.2527262553/0.3159078191，SLO10500/13000ms；Mistral率0.2418217143，负载0.1934573715，SLO11000/18000ms。
- 模板部署attestation的见证是controller-private compiled路径，不能当Raw等价；实际Raw配对另行审计。三臂业务采用同授权模板cache组，Session/Template都允许合法prefix-assisted verification。

## 正在执行

远程根目录：`/media/user/5bc0dc8d-c938-4b2a-af1b-94174fc511a9/VLAtest/contractkv`，Python `contractkv-cu128`。本机SSH使用既有Credential Manager helper，严禁输出凭据。所有模型/日志/cache均在8TB卷；不可修改共享runtime或终止其他任务。

正式源冻结：`formal_freeze_v1/freeze.json` SHA256 `bf5f1960d0bdac48c58402b741e9aab83e61585be9353320ef25412b5e864f87`。
实际预检：`formal_preflight_receipt_v1.json` SHA256 `0401b6bf9ee2f02beef3a195cb29b6d65898a5d3a243eef7ba001512c96ff2e7`。
执行前Git已公开核对：`3eeda44f6a6354aab71f5aae16009611506a282e`。
launcher PID770906，worker实际PID由`formal_launch_v1.json`读取并核查命令/状态。只监测同一worker，不重复启动、不重跑完整单元、不覆盖数据。

worker为`scripts/tsc_template_task_serving_worker_v2.py`；job/arrival/SLO全部在`formal_protocol_v1.json`和`formal_jobs_v1/`。同模型/重复的三臂使用同物理GPU；按wave等待全部server ready后才开始测量，持有先完成peer直到整wave结束，避免加载干扰。15wave的计划到达跨度下界约26155秒，启动/排空另计。

## P3

`tsc_template_task_postprocess_formal_v1.py`只等待现有`formal_exit_v1.json`，成功后执行独立CPU分析和归档，绝不发GPU请求。失败时保留状态/日志，查原因后仅修CPU分析或归档；不能重跑GPU以掩盖结果。

分析：`tsc_template_task_formal_analysis_v1.py`，输出`formal_analysis_v1/`；原包`formal_evidence_v1/`，32MiB分片。用`tsc_template_task_local_recompute_formal_v1.py`在全新`.artifacts/`目录安全恢复，173冻结文件、summary和4 CSV完全一致，原成员保持不变。

结束后写一份MD总报告和决策记录：质量/IDs、绝对Goodput、计划到达TTFT/尾部、完整费用、资格调用、物理new-prefill、Source/Repeat不确定性、全部不利结果与适用条件。正文和Response Letter不改，不新增实验分支。最后commit/push并核对远程SHA，再完成goal。

Git smart-HTTPS曾不可用，已用官方Git Database API经现有GCM内存授权恢复精确blob/tree/commit并fast-forward，未改历史；本地`.artifacts/tools/publish_exact_task_commits_api_v2.py`可继续同样归档，不能打印、存储或把凭据放入参数。
