# ContractKV 六图 V9

按2026-10-17最新反馈更新。Fig.1增加依赖DAG、布局候选、token/EOS校验、证书scope表、PSTP候选块/提交/中止、native prefix index及GPU块池，采用分层架构图表达。没有引入参考图特有的ILP、CPU offloading、调度器或attention算法。

| 图 | 版式 | 原生画布（英寸） |
|---|---|---|
| Fig.1 | 双栏 | 7.16 × 3.85 |
| Fig.2 | 双栏 | 7.16 × 2.80 |
| Fig.3 | 单栏 | 3.45 × 4.30 |
| Fig.4 | 单栏 | 3.45 × 4.55 |
| Fig.5 | 单栏 | 3.45 × 4.70 |
| Fig.6 | 单栏 | 3.45 × 4.30 |

Fig.3–6重新布局和设置字体，并非将通栏图直接缩小。数据与V7/V8保持一致，Fig.2继续省略柱顶重复圆点。PDF/SVG为矢量，PNG为600 dpi。架构与绘图QA记录文字边界、碰撞及输出SHA。

源码：`submission/gen_tsc_architecture_v9.py`与`submission/gen_tsc_figures_v9.py`。完整的独立绘图/编译代码、图注和正文在 `Paper/revision_integrated_20261017/`；该目录的`figures/`是实际嵌入主文的同字节图件。V8目录保留。
