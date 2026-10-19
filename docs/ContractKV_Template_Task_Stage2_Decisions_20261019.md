# Task-Bearing Template Service Validation：执行决策

## D1：采用原部署语义，Raw质量另行测量

源码确认旧模板注册以compiled prompt生成路径作见证，而非Raw回答。新Session/Template两臂统一使用该部署attestation，并分别测实际Raw/Compiled输出IDs、终止与任务分数；不借F7或R4的Raw-query保证。0.0625/0.125/EOS与PSTP检查不变，Repo保留现有Python输出契约，不取消保护以提高通过率。

## D2：不以缓存身份差异制造摊销收益

三臂所有业务采用统一授权模板缓存组；Session只改变证书对象和tenant绑定，不分裂底层缓存组。canary统一在controller-private命名空间生成，避免未验证候选被普通APC提前暴露给业务；Session与Template都可在同一私有模板组复用canary缓存。正式clock从注册前开始，计划到达时间不随注册完成后移，零slack。

## D3：接纳用户新增P0–P3设计，保留CPU历史

首次v1仅HotpotQA、尚无GPU输出。用户随后补充Qwen优先、HotpotQA/RepoBench、六模板/8租户/8轮、两负载/三重复；v2单独发布，复用原盲选Hotpot来源而不根据输出重选，增加2开发/3正式Repo。两版本CPU内容、哈希与未消耗的旧六验证来源均保留。共同16K下完整问题/CODE_PREFIX/空白必须保留；超窗可选上下文仍按已冻结、不读gold位置的首尾规则裁剪，不称为完整未裁原文。新10来源没有发现与729历史组或彼此完全相同的任务上下文，不宣称语义独立。

## D4：Qwen开发先于Raw-only标定和正式矩阵

先4来源52生成；按家族检查双来源注册、配对质量、真实前缀命中及64次复用的实测费用空间。无家族通过即停止，失败家族保持L0。只有通过后才冻结Raw-only实测负载与SLO，Qwen最多18正式单元；其他模型须独立开发通过才各9单元。RPC成功率、布局覆盖和实际Goodput分别报告，不设置漂亮倍率验收线。

## D5：启动基础设施失败零输出，先修复依赖完整性

v2 Qwen attempt1在API模块导入阶段退出：冻结包未收运行时动态导入的`tsc_revision_r2_margin_policy`，且诊断trace路径入口亦未纳入闭包。模型权重未加载、业务/模型输出为0，完整server日志、launch、failure、worker exit与旧freeze保留。此项属于新编排缺陷，不是实验方法或质量负结果。

依据不可变runtime源码补齐五个动态脚本模块及trace entry，增加隔离快照下的API CLI help、scheduler/model runner和trace导入预检。随后v3的CPU预检又拦截了三条Windows分隔符manifest路径；未启动新的模型server。v4将所有seed强制规范为相对POSIX路径并增加断言，旧v2/v3全部保留。未执行过的分析脚本旧远程版本亦改名保留。实际输入、阈值、生成预算、资格规则与统计协议v2不变；修复后Qwen使用fresh-server attempt2，不重跑任何有效完成的科学单元。
