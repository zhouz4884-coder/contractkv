# 已按原冻结v3启动：机制与Manifest共用9进程

- 启动：2026-10-18 12:22:14 UTC / 20:22:14 Asia/Hong_Kong。
- supervisor PID236905；实际worker PID236906。
- 原worker为scripts/tsc_revision_mechanism_worker_v3.py，未改写。
- checked entry校验后exec原worker；/proc命令已确认实际为mode execute。
- freeze_v3 SHA：7170c9101903326c582bc32e93ca2e4d7998b42b8fc5a8bb62c7d158ed8dd4ff。
- 依赖补充SHA：389011e4c1fd5fdc57270ad2445fc5c23e275c4dd9cdba822d3ade3e542bf991。
- 实际预检回执SHA：2262851f17210e56064e374c47a6a7215bcf880955c80b0cc342ee3403a19eeb。
- 六metadata逐SHA匹配，144个模型/case/输入条件适配16K；预检无模型推理。
- 回执、metadata、source与launch plan在本批GPU之前公开，远程main已核对0f1ef20b4ae8f22dbd2a2cbd6775a41e5da33932。

12:24观察到两张指定3090的EngineCore PID237659/237740，对应Qwen与Mistral首轮进程。下次仍以实际PID/命令/锁为准，不依据旧PID重复dispatch。

## 状态显示口径

原worker在execute复用回执后、第一wave期间仍显示AWAITING_RECEIPT_PUBLICATION，第一wave结束后才写RUNNING。该字符串不代表当前仍未发布回执或在等用户。实际execute命令、server PID与responses才是当前依据；不要再次运行preflight或execute来推进状态。

## 冻结验收

两批共用三模型三fresh-process的9cells，共855次业务、最多198次认证RPC，不是18cells。原9注册/19绑定CPU检查直接复用；旧v1/v2无本批GPU数据，不重做。

完整9cells后运行原tsc_revision_mechanism_analysis_v3.py；新增effects_summary_v4仅后处理，按实际输出/finish变化、任务分数升降、正常放行/保守拒绝提供显式分母，保留Raw重复不稳定与不确定RPC。它不用declared risk定义实际有害，不改变collector或freeze。

code_context为合成Python赋值，不能改名为真实RepoBench。CPU缺口索引real_RepoBench_mechanism_gap_v1.json限定必要补充最多3个fresh-model进程；当前9cells保持原样，前三批完成归档后独立冻结补充。

第一批原TableIII已24/24完成；52,671,414字节、2分片、801成员双端校验通过。本地复算12成本、525controller、4725质量行全字段一致。详见docs/tsc_TableIII_fullcost_replay_completed_20261018_zh.md。

三批后还需完成新五批目标中的独立保真Open-arrival和有界Gate等对照。不要提前暂停automation或complete goal；论文与Response Letter后置。
