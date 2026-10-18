# 仅补齐已有后端依赖：执行补充清单

此补充不修改 `freeze_v3.json`、案例、候选、门槛、评分、worker_v3 或已完成数据。原 freeze SHA 仍为 `7170c9101903326c582bc32e93ca2e4d7998b42b8fc5a8bb62c7d158ed8dd4ff`。

只读后端导入审计发现，六份已登记 backend 源文件全部匹配原 R1R/R2 commitment，但脚本快照漏带四个它们动态调用的已有模块。补包从远程现有实现逐字节取得；四份均与本地既有实现 AST 一致，两份 R2 模块还匹配既有 commitment 的精确 SHA。没有新实现替代旧机制。

新增四模块为 `contractkv_quiescence`、`contractkv_shadow_parking`、`tsc_revision_r2_execution_trace`、`tsc_revision_r2_margin_policy`。原字节同时存于 `backend_project_dependencies_v1/scripts/` 和原快照中原本缺失的路径。原快照已登记的55文件全部保持不变，补充清单为 `backend_project_dependency_manifest_v1.json`。

其 SHA：`389011e4c1fd5fdc57270ad2445fc5c23e275c4dd9cdba822d3ade3e542bf991`。

使用很薄的校验入口 `scripts/tsc_revision_mechanism_checked_entry_v1.py`：校验旧 freeze、四个新增依赖及后端六文件，递归检查/导入实际项目依赖，然后 `exec` 原 worker_v3。它不重写编排、不启动第二个worker、不改业务逻辑。检查父进程及后续worker的HF/Torch/临时缓存仍位于8TB卷。

执行顺序保持：

1. `--check-only` 仅执行源码/导入CPU检查，不进入模型或worker。
2. 第一批24 cells完成、原worker退出且资源独占后，使用校验入口 `--root <root> --dependency-freeze-sha256 389011e4c1fd5fdc57270ad2445fc5c23e275c4dd9cdba822d3ade3e542bf991 --mode preflight`。
3. 取回并公开原worker生成的 `preflight_v3/receipt_v1.json` 及全部元数据，核对远程Git SHA。
4. 同一校验入口加 `--mode execute --receipt-sha256 <真实回执SHA>`，进入已冻结的9 cells。已有worker或锁只监测，不重复启动。

四模型完整权重SHA已有，按原worker的已有注册和当前stat一致性检查复用；不重新准备或重跑已完成的GPU单元。不再修改先前freeze文件，也不将本补充的CPU检查计作GPU结果。
