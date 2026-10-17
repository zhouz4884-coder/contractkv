# ContractKV 主图重绘（2026-10-17）

已完成 Fig. 2–6，Fig. 1 留给作者。所有旧图和正文保留，新文件集中于本目录。

[五页矢量审阅 PDF](ContractKV_Fig2-6_review.pdf) · [五图总览](all_figures_preview.png) · [英文图注草稿](captions_v6.md) · [配套表格](supporting_tables_v6.md)

## 故事主线与设计决定

| 图 | 要回答的问题 | 绘制方式 |
|---|---|---|
| Fig. 2 | 严格作用域、真实任务、零 slack 下能否有全成本收益？ | 双栏宽三面板；1.619/1.109/1.070×；prefill 加入认证；未来覆盖分母 1,620/model |
| Fig. 3 | 收益对应哪些获准请求，真实输出是否变化？ | 路由堆叠再区分 raw 正分/零分；并列 0/2,442 和 0/1,296，保留来源数 |
| Fig. 4 | 治理开销如何进入服务，模板共享为什么值得？ | D1/D2 真值及重复范围；两组 live 坏布局拒绝；次数和毫秒分别画 |
| Fig. 5 | 原部署协议能否产生实际服务与物理复用收益？ | 绝对 SLO goodput；530→149 allocator-used blocks；4.81×仅小标单点 |
| Fig. 6 | 什么复用密度和驻留条件支持收益？ | 授权共享曲线与工作集曲线；gate 移入配套表 |

保持原 v5 的蓝/青/灰语义配色，复用其 set_style，增加明确的浅蓝斜线编码。先以原绘图方法生成，再按 scientific-figure-making 的图例和边界规则修正首版拥挤；未使用生成式位图代替实验曲线。

## 与最初建议相比的调整

- Fig. 3 不只重复 Fig. 2 覆盖率：额外分出 684/684、258/342、90/270 的 raw 正分子集，行为一致与参考质量同时可见。
- Fig. 5 将身份数 goodput 的完整旧曲线留在配套表，主图聚焦开放到达的绝对 goodput 和实际物理 block 数。两者属于原部署协议，主图与 Fig. 2 的新保真闭环协议明确分开。
- Fig. 6 直接从配对 CSV 计算共享收益：0% 共享为 −3.20%，旧生成器写成 0；75/100% 由原粗略 93.4% 改为源 CSV 的 93.3%。没有改实验记录或截去负值。
- 旧 TTFT 对照的工具 slack 分别为 Qwen/Mistral/14B 的 2,000 ms、Llama 的 6,000 ms；均移入配套表。另六来源 Qwen 1.803×单列，没有混入三模型柱图。
- 4.81×使用其绝对曲线的均值单点，不沿用来源链未闭合的旧区间。新 Fig. 2/4 的 whisker 是进程重复 min–max，图注明确该定义。
- 全路由变化、p99 代价、未选成本变体和 CacheBlend 各自 native baseline 的质量分布都保留在配套表。

## 文件与复现

- 每图 PDF / SVG / 600-dpi PNG，统一双栏宽 7.16 英寸。PDF 字体嵌入；SVG 文字可编辑。
- `figure_data_v6.json`：所有绘图值与协议边界。
- `source_manifest_v6.json`：23 个原始数据/风格依据的路径和 SHA256。
- `plot_sources_v6.zip`：所用原始统计表、v5 配色代码及三份新脚本的完整快照，便于在独立目录复现。
- `render_manifest_v6.json` / `publication_QA_v6.json`：字体、尺寸、向量文本与越界检查。
- `manuscript_figure_map_v6.json`：旧图文件名与新图的映射，尚未修改 LaTeX 引用。

从仓库根目录运行：

```powershell
python submission/build_tsc_revision_figure_data_v6.py
python submission/gen_tsc_figures_v6.py
python submission/package_tsc_revision_figures_v6.py
```

生成依赖：Matplotlib、NumPy、Pillow、PyMuPDF。绘图沿用本机 Arial，实际字体身份记录于 manifest。全程未启动 GPU 实验。
