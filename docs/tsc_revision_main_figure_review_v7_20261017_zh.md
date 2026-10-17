# ContractKV Fig. 2–6：反馈吸收与V7交付

日期：2026-10-17。已完整阅读本次修改意见，并在保留V6和所有实验结果的条件下完成V7。Fig. 1及正文未修改，没有追加GPU实验。

## 采纳与调整

| 修改意见 | 本版处理 | 数据及口径核对 |
|---|---|---|
| Fig2覆盖率子图信息单一，缺少平均服务延迟 | 改为Mean Readiness TTFT；prefill增加净下降百分比、认证工作数字；按作者最新偏好去掉柱顶重复圆点 | 均值下降43.87/12.09/3.99%，对应同一冻结wave时钟；三次重复数值、范围、p99及来源簇区间保存在表中 |
| Fig3跨任务差异不足，右侧空旷 | 左侧模型×任务覆盖矩阵，右侧紧凑ID分歧统计及raw正分子集，下方增加真实请求链 | 每模型/家族810对；Mistral/Llama RepoBench由开发catalog明确继承L0，不能叫GPU认证失败 |
| Earlier audit raw正分聚合可能误读 | 重新逐请求计数，按家族和single-session/template-fanout拆分 | 2,442/2,442计数无误；RULER字符串匹配、QA F1和代码相似度是不同credit，主图不再将该聚合数作为统一正确率 |
| Fig4主次反转、拒绝表占地 | 将25×调用和7.7×成本摊销移到左侧；中间压缩为FAIL→零候选块提升；右侧97.0%均值goodput保留 | 保留D1=1.472、D2=1.428 req/s；五重复范围明确是min–max，没有补造未恢复的逐次点或非劣效区间 |
| “Tokens published on rejection”含义过宽 | 改为“0 rejected-candidate KV blocks promoted” | 由FAIL/ABORT下0 committed candidate tokens核对；不指代raw fallback的原生APC行为 |
| Fig5服务收益缺乏绝对增量 | 80%负载标0.173→0.831，突出+0.658 req/s；移除大面积填充；右侧增加同批密度goodput | block与1.152→11.033 req/s已在同一六个density cell核对。右侧是分层SLO wave replay，左侧是500-ms开放到达，图上直接分开 |
| Fig6应强化机制而非再堆数据 | 50–75%范围标“Observed transition”；右侧改reuse distance/hot-set skew，标round-robin近零收益 | 纵轴保持TTFT reduction，未误称驻留比例；−3.2%负点保留，也不把观测区间当理论阈值 |
| 配色、误差表达和版面统一 | Raw/reference灰、CKV深蓝、qualified reuse青绿、认证成本橙、拒绝少量红、D1蓝灰；去掉重复长脚注 | 单图PDF/SVG仅紧凑图形及必要协议标记，长caption单独保存；含caption的五页PDF是审阅版 |

## 真实请求轨迹的证据边界

Earlier编译子集进一步分解为2,178条RULER、174条NarrativeQA和90条RepoBench；其raw正分不能代表一个均衡跨任务的准确率。新主图因此将共同保真HotpotQA/RepoBench覆盖放在前面，Earlier audit仅保留为独立协议下的有限输出ID证据。

选择规则是primary Qwen第1重复中按文件顺序的首个issued certificate、其同作用域raw witness和首个compiled future；没有按评分或是否相同挑选案例。

该HotpotQA doc69实例中：t0实际raw流返回7个IDs（含自然结束）；验证载荷引用同一IDs；live回复为PASS/COMMITTED、888完整候选块（14,208 tokens）；t3同作用域compiled流返回相同7个IDs，初次native观测命中14,240 tokens。

这条图中链条使用实际COMMITTED响应及后续native可用性，不伪称原日志存在独立的BlockStored事件，也不单凭一例证明全部业务安全。六条选中记录及其原始行号、行SHA256、上游文件SHA256保存在`trace_log_excerpt_v7.json`，本地对完整原日志逐行核对通过，raw SHA亦匹配原cell summary。

## 交付与验证

入口：[V7说明与文件](../Paper/figures/revision_20261017_v7/README_zh.md)；[五图审阅PDF](../Paper/figures/revision_20261017_v7/ContractKV_Fig2-6_review_v7.pdf)；[完整配套表](../Paper/figures/revision_20261017_v7/supporting_tables_v7.md)。

- 五图均导出7.16英寸宽PDF、可编辑SVG、600-dpi PNG，PDF字体嵌入，无Type3或内嵌位图。
- 实际PDF文本中的核心数值均核对；canvas越界与文字碰撞为0；逐张查看图形和审阅PDF。
- 32项输入/风格/协议依据保持SHA256一致；36成员源数据及源码快照可独立解包重画。
- 在独立目录运行三步构建，五图共15份PDF/SVG/PNG逐字节相同，数据JSON、source manifest与评分credit审计CSV也逐字节相同。独立复现使用源数据快照内的exact selected trace records；完整上游日志的独立重选仍以原实验归档为依据。
- V6目录内29个已跟踪文件保持原字节，旧版本留作比较。

源码为`submission/extract_tsc_revision_trace_v7.py`、`build_tsc_revision_figure_data_v7.py`、`gen_tsc_figures_v7.py`及`package_tsc_revision_figures_v7.py`。本轮只提升信息组织和表达，不更换实验算法、样本或结果。
