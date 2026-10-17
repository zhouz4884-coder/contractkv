# ContractKV Story V4 正文与版面修改记录

日期：2026-10-17。V3 保留在 `Paper/revision_story_v3_20261017`；本轮交付在 `Paper/revision_story_v4_20261017`。依据用户提供的 Story V3 审稿式评估及作者简介空间要求，完成正文、图、补充材料和版面修改。Response Letter 留待正文确认后撰写。

## 本轮完成的主要修改

| 修改 | 实际处理 | 最终位置 |
|---|---|---|
| Fig.1 对象语义 | 模板证书、客户端 query-scope admission records、物理 `(namespace,Hs)` 身份分别成框；查询记录不再画在签名证书内部。不增加双证书或自动切换。 | 主文 Fig.1，第 2 页 |
| PSTP 边界 | `Private candidate KV` 替换可能误导的 stable-only 标签；提交箭头明确 `certified stable full blocks`，保留整块截断示意。 | 主文 Fig.1，第 2 页 |
| 资格协议比较 | 新增紧凑表，区分见证来源、请求侧准入、身份、摊销单位与实验；正文明确客户端记录不等于另一套服务端签名证书。 | 主文 Table II，第 4 页；§IV.C/E、§V.A |
| 原 V3 Table II | 部署表只保留同一部署 cohort 的 TTFT、Prefill 与 slack；独立零 slack 数据留在另一张补表。两套测量不再同一行并列。 | 主文 Table III，第 7 页；补充 Table S-XIII，第 5 页 |
| 零 slack 成本定义 | 明确为业务 TTFT 加实测注册控制器总成本/未来请求数；核对各重复的公式与比例。不是原部署表的 matched slack ablation，也不是线上逐请求 p99 成本测量。 | §VI.B、补充部署经济性小节与 Table S-XIII |
| Manifest 信任边界 | 单列可信 operator/controller/runtime/cache manager；写出 tenant A 私有 TOOL_OBS 被可信 operator 误标为共享 Stable 的后果；区分 hash 的字节身份与 HMAC 的绑定认证，均不判断保密性。 | §VIII.B，第 11 页 |
| Helper 与 live 区分 | 明确 CPU helper 未接入 live endpoint；九例全部列出：7 拒绝、1 正常通过、1 可信语义误声明仍通过。保留时序侧信道未防御声明。 | §VIII.B；补充 Table S-XVII，第 7 页 |
| 六来源分布 | 从冻结记录重算全部 6 来源 × 3 模型的 raw 绝对分数、策略均值差、编译覆盖、编译子集正分数、全路由分数升降、配对 future p99。 | 补充 Table S-XVI，第 7 页 |
| Goodput 不确定性 | 恢复开放到达 80% load 点的绝对增量：+0.658 req/s，95% 区间 [0.539,0.765]；核对归档区间点值与冻结 aggregate，保留层次重采样单位。 | Fig.5、§VI.D；补充 Table S-XVIII，第 7 页 |
| 叙事精简 | 引言用一个开发反例解释 scope 必要性；用协议表承载重复边界说明，精简输入构造、重复实验总结及限制中的重述，保留四贡献和服务性能主线。 | Introduction、§IV–VI、§VIII–IX |

新加入方法表后，原 V3 的部署 Table II 顺延为 V4 Table III。正文引用和实际编译索引已经更新，不能继续套用旧图表页码。

## 原有证据没有被替换

- 三模型严格主验证仍为 1.619× / 1.109× / 1.070× 全 wall 吞吐；编译未来配对仍为 0/1,296 ID 分歧。
- 第二组 Qwen 1.803× 独立来源结果、成本适配不利结果、p99 上升、L0 波动、零分数见证和长输出失败均保留。
- CALC、Scoped Certification、PSTP 与 Service-Template Certificate 的四贡献结构不变。没有新算法、作用域放宽、阈值变化或新 GPU 实验。
- 冻结主图数据 JSON 的字节身份不变。Fig.2/3/4/6 的 PDF 与 V3 逐字节相同；Fig.1 修对象表达，Fig.5 增加已有区间。未重新加入柱顶空心小点。
- 归档 Goodput CI 没有在本轮重新 bootstrap；本轮做的是区间来源、统计单位与点值核对。逐来源 p99 和分数确实进行了 CPU 重算并核对冻结汇总。

## 版面与验证

主文 **12 页**，补充材料 **7 页**。正文保持 IEEEtran 正常字号和页边距；Fig.1–2 双栏、Fig.3–6 单栏。六图均提供矢量 PDF、可编辑文字 SVG 和 600-dpi PNG。

作者简介在第 12 页右栏**实际预留**单栏宽、348 TeX pt 高的空白区，等于 696-pt 双栏正文页的 25%。编译时记录起止坐标，QA 核实该区为空且未跨页。它不是一句“稍后安排”的注释，也没有填入虚构简介。正式作者文字/照片确认后，替换该占位再编译即可。

检查结果：

- 主文/补充材料均无 Overfull box、超大浮动体、缺失引用、重复标签或 TeX 错误。
- PDF 字体均嵌入，无 Type 3；六图保持矢量，SVG 中有可编辑文本且无嵌入位图。
- 六来源/18 行分组、4,860 future pairs、1,296 compiled pairs、九例 helper、独立成本公式与来源文件哈希均通过核对。
- 在独立目录删除生成图和 PDF 后从源码重建：18 个图形导出加表格、汇总和定位文件共 **27 项逐字节一致**。主文/补充材料分别保持 12/7 页，逐页文本一致。没有声称 LaTeX PDF 文件本身字节相同。
- 最终位置表含 **74 个编译标签、18 项证据主题**，给出实际 PDF 页码、章节/图表号及 TeX 源行。未伪造 PDF 印刷行号。

## 阅读入口与后续边界

主文先看第 2 页 Fig.1、第 4 页协议表、第 7 页部署表，再看第 11 页 Manifest 小节；补充第 7 页集中给出逐来源分布、九例注册边界和 Goodput CI。

本轮正文修改和版面任务已完成。尚未填入作者真实简介，也未撰写 Response Letter；两者均按用户要求留到后续。旧 RULER 宏平均窄 CI、92.90/92.62 所属实验单元等历史问题，仍需在之后的逐点回复中明确说明，不能将本轮正文重排视为已经写完审稿回复。
