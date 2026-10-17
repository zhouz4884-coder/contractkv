# ContractKV 主图重绘交付记录

2026-10-17。范围：Fig. 2–6 的数据选择、绘图、图注草稿和配套表；Fig. 1 由作者绘制，正文与 LaTeX 引用保持原样。没有运行新 GPU 实验。

## 主线与结果

五图顺序为：**严格服务全成本收益 → 真实输出配对证据 → 认证治理与模板摊销 → 原部署服务规模 → 复用与驻留条件**。

| 图 | 主要视觉与数据 | 处理理由 |
|---|---|---|
| 2 | 三模型完整 wall 倍率 1.619/1.109/1.070×；业务与认证新增 prefill 分开；未来覆盖 42.22/21.11/16.67% | 用共同六新来源、保真16K、零slack和三重复构成性能主证据。每模型覆盖分母1,620；完整服务计时也包含初始业务 |
| 3 | 覆盖柱细分 raw正分/零分/Raw-L0；输出ID差异0/2,442和0/1,296并列 | 补充Fig2没有的参考质量维度，直观显示相对保持与绝对质量的区别。不同协议和来源不相加为独立样本 |
| 4 | D1=1.472、D2=1.428 req/s及五重复范围；两模型各10/10坏布局拒绝、0发布；125→5 calls、25.05→3.24 ms/request分别绘制 | 保留真实治理成本，突出Service-Template证书在授权重复服务中的摊销价值；不以D0小分母制造主要视觉倍率 |
| 5 | 原部署开放到达绝对SLO goodput；530→149已用KV blocks（71.9%），2,386-block pool | 4.81×只作为80%负载的小标注；80个注册identity与同时GPU请求明确区分。旧身份数goodput曲线保存为配套表，保留其分层SLO口径 |
| 6 | 授权共享比例与工作集/Zipf、round-robin两面板 | 用集中一张图说明适用条件；frozen gate的2/4结果移入配套表 |

## 自主调整与数据核查

1. 复用`submission/gen_tsc_figures_v5.py`的配色及style，所有新输出放入单独目录。首版出现标题/图例越界，随后使用`scientific-figure-making`的图例分区与版面规则修正；五图最终均无canvas越界，逐张查看了图和审阅PDF。
2. Fig3增加参考分数分层，避免只把Fig2覆盖率再画一遍。新保真获准子集中，raw正分为Qwen 684/684、Mistral 258/342、Llama 90/270；零分子集没有删除。
3. Fig6不再照搬旧脚本手写近似数：配对源CSV在0%共享处为−3.1998%，旧脚本写成0。75/100%按源表显示93.3%，替代旧粗略93.4%。原始实验文件未修改。
4. 历史TTFT的slack核对为Qwen/Mistral/14B 2,000 ms、Llama 6,000 ms。另六来源Qwen 1.803×独立列入配套表。原成本适配负结果、全路由分数变化和p99代价也保留，不能用吞吐主图宣称普遍尾延迟改善。
5. CacheBlend移入各自matched baseline的质量分布表；不使用跨栈速度柱形排序。4.81×未沿用尚未闭合来源链的旧区间。

## 交付与验收

全部文件位于[新主图目录说明](../Paper/figures/revision_20261017/README_zh.md)。主要入口：

- [五页矢量审阅PDF](../Paper/figures/revision_20261017/ContractKV_Fig2-6_review.pdf)
- [五图总览](../Paper/figures/revision_20261017/all_figures_preview.png)
- [英文图注草稿](../Paper/figures/revision_20261017/captions_v6.md)
- [配套表格](../Paper/figures/revision_20261017/supporting_tables_v6.md)
- [源码与所用统计表快照](../Paper/figures/revision_20261017/plot_sources_v6.zip)

每图均为7.16英寸双栏宽，导出矢量PDF、可编辑文字SVG、600-dpi PNG。实际PDF文本已核对关键数值；字体嵌入、无Type3、PDF/SVG均无内嵌位图；源文件23项SHA256保持一致。检查结果见`publication_QA_v6.json`。

从26成员源码/数据快照解包到独立目录，重新执行数据构建、绘图和封装，五图的15份PDF/SVG/PNG全部逐字节相同，数据JSON与source manifest也逐字节相同。结果见`reproduction_audit_v6.json`。这证明本机相同字体/依赖下的复现，不代替审稿人对图形论证的判断。

原目录中10个Git已跟踪的旧图文件与此前HEAD逐字节一致；本轮没有修改任何`.tex`。旧图和正文引用可在正式修稿阶段按`manuscript_figure_map_v6.json`逐项替换。

绘图源码：

- `submission/build_tsc_revision_figure_data_v6.py`：从原始结果表构建数据和来源清单。
- `submission/gen_tsc_figures_v6.py`：沿用v5配色，绘制全部五图。
- `submission/package_tsc_revision_figures_v6.py`：图注、配套表、审阅PDF、源数据快照及导出验收。
