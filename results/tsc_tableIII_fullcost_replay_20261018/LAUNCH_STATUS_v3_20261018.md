# 当前执行入口：v3，短 IPC 路径修复

原协议、历史客户端、样本、候选、阈值、作用域和评分均不变。`formal_attempt2` 的两个 Llama server 因 Unix socket 路径超过 107 字节在 API ready 之前退出，未执行客户端，业务请求数为 0；全部日志保留。

v3 只在每个 cell 的真实 8TB 临时目录外建立 `/tmp/ckvIII-<hash>` 短符号链接，并把该别名用作 TMPDIR。实际文件仍在 8TB 卷。Linux 10 项基础设施检查全部通过，包含真实 ZMQ IPC bind、文件实际位置和外国进程组保护。

模型/输入/运行时预检沿用已完成的完整校验，并重新核对所有模型 stat 和全部 runtime 字节。`launch_attempt3_preflight/runtimes` 指向本实验自己的 attempt2 runtime 副本，没有修改共享分支。新回执 SHA：`e487945435f26f854569c0be4fbed49893d8010c15f24d09bceb6d03ddca8cea`。

当前使用 `scripts/tsc_tableIII_fullcost_worker_v3.py`，`--attempt 3 --repair-record <.../infrastructure_repair_v3.json>`。执行前先把新回执、代码、修复记录、`formal_attempt3_supervisor.py` 和启动参数归档/commit/push并核对远程 SHA，然后才启动。执行需传入新回执 SHA，不能用旧 worker/source hash 绕过验证。

监测时读取远程 `execution_state_v1.json`、actual worker PID/命令和锁。已有进程（含 CPU preflight）只监测，不重复启动。程序退出后保留整对失败记录；不能续跑半个 cell。先前源码 v1/v2 及其冻结记录保留，不覆盖。

总体目标现为三批：原 Table III 完整成本；五类跨模型 D1/D2 必要性；合成 Manifest 注册/绑定/真实发布与命中闭环。第一批完成不是整体目标完成，不要提前暂停自动化或开始正文修改。详见 `docs/tsc_revision_three_batch_GPU_plan_20261018_zh.md`。
