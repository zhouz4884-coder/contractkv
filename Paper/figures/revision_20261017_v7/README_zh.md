# ContractKV 主图 V7（2026-10-17）

本版借鉴新修改意见，重新安排 Fig. 2–6 的信息层级；Fig. 1 与正文未改，V6完整保留。

[五图审阅PDF（含独立图注）](ContractKV_Fig2-6_review_v7.pdf) · [总览](all_figures_preview_v7.png) · [图注草稿](captions_v7.md) · [完整配套表](supporting_tables_v7.md)

## 主要变化

- **Fig. 2**：吞吐、业务+认证prefill、Mean Readiness TTFT。加入净工作量下降45.4/14.6/10.9%和平均readiness下降43.9/12.1/4.0%。认证工作数字直接标出。按作者偏好去掉柱顶重复圆点，三次重复数值及范围保存在配套表中。
- **Fig. 3**：模型×HotpotQA/RepoBench覆盖矩阵；继承L0用灰色斜线单独标明。右侧压缩零分歧统计，并保留raw正分子集。下方是真实日志链：7 IDs→PASS→COMMITTED 888块→t3相同7 IDs，附原始记录和哈希。
- **Fig. 4**：25倍调用摊销、7.7倍未隐藏成本摊销成为左侧主视觉；失败候选零提升居中；右侧展示D2保留D1约97.0%的实测均值goodput。零提升仅针对被拒候选，不能解释为raw fallback完全不缓存。
- **Fig. 5**：在80%负载处同时标0.173→0.831和+0.658 req/s，4.81倍限定为该点。右侧突出+381 free blocks，并加入同批80-identity密度单元的1.152→11.033 req/s。右侧是分层SLO wave replay，左侧是500-ms开放到达，不能合并口径或据此把全部吞吐改善归因为headroom。
- **Fig. 6**：保留真实负值，淡色标识50–75%观测跃升区间；右侧改为reuse distance/hot-set skew，并提示round-robin收益接近零。纵轴仍是TTFT reduction。

## 术语、版式和证据取舍

Raw/reference灰色、ContractKV深蓝、qualified reuse青绿、认证成本橙色、拒绝仅少量红色、D1中性蓝灰。每张单图仅包含紧凑图形、必要协议标记和图例，不内嵌长caption；含标题和图注的合订PDF仅用于审阅。PDF/SVG用于LaTeX，PNG为600 dpi预览。

Earlier audit的2,442/2,442 raw正分已逐请求复核，并按任务家族/协议导出`earlier_score_credit_audit_v7.csv`。RULER字符串匹配、QA F1和代码相似度不是统一准确率，因此主图不再把该聚合正分数当作正确回答证据。p99、全路由变化、独立Qwen来源与历史slack、跨栈质量表均保留在配套表。

真实轨迹选择规则是文件顺序中的首个获准证书及其首个同作用域未来请求，不按结果好坏挑选。`trace_log_excerpt_v7.json`保存六条完整选中记录、原文件SHA256和行号；其commit证据来自实际COMMITTED响应与随后native命中，不伪称存在单独的BlockStored事件。完整原日志仍在原实验归档。

## 复现

```powershell
python submission/build_tsc_revision_figure_data_v7.py
python submission/gen_tsc_figures_v7.py
python submission/package_tsc_revision_figures_v7.py
```

`plot_sources_v7.zip`包含所需统计表、V6数据构建依赖、四份V7源码以及实际轨迹选中记录。在独立目录解包后可重画；若要独立重新选择轨迹，请恢复原primary raw/metrics归档后执行`extract_tsc_revision_trace_v7.py`。字体及依赖版本、SHA256、越界/文字碰撞、矢量与字体检查保存在各manifest和QA JSON中。未运行新GPU实验。
