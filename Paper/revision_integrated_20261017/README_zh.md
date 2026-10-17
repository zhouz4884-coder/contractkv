# ContractKV 重构与嵌图稿（2026-10-17）

主文围绕“有行为证据和事务边界的可复用KV服务对象”重构；保留原四项贡献、真实性能和所有主要限制。本轮没有运行新实验。

## 直接阅读

- [12页主文 PDF](contractkv_tsc_integrated.pdf)：嵌入图形化重绘的Fig.1和重新排布的Fig.2–6；Fig.1/2双栏，Fig.3–6单栏。
- [补充实验记录 PDF](contractkv_supplement.pdf)：保留上传初稿的详细实验表、成本变体和历史结果。
- [重构、删减和配图决策](audit/restructure_decisions_zh.md)。
- [实际编译、数值和图形检查](audit/manuscript_QA.json)。

## 源文件

`contractkv_tsc_integrated.tex`为主入口，`sections/00_abstract.tex`至`09_conclusion.tex`为可编辑正文；`references.tex`为主文参考文献。`contractkv_supplement.tex`和`supplement_evaluation.tex`为补充材料。`figures/`包含六张图的PDF/SVG/PNG及冻结绘图数据。

```powershell
# 重画六图：Python + matplotlib + numpy，使用本机Arial字体
python scripts/plot_figures.py
python scripts/plot_architecture.py

# 编译两份PDF：正常TeX Live/MiKTeX，需IEEEtran等包
python scripts/build.py
```

`scripts/compile.py`来自本次使用的latex-paper-en编译包装器；build脚本以禁用shell-escape的方式运行它。绘图数据可以独立重画，但不冒称这一小包包含全部GPU原始日志。原始实验的来源、SHA和协议由`audit/source_manifest_v7.json`、原证据索引及项目归档定位。

Fig.1为机制示意，没有虚构性能数值；Fig.2–6的统计没有改变。PDF/SVG为矢量，PNG为600 dpi；柱顶重复圆点继续省略，三重复统计保留在`audit/supporting_tables_v7.md`。

本稿为作者审阅用的完整重构稿。保留原署名/单位；原上传压缩包、旧V7图和旧论文不覆盖。正式Response Letter及作者简介另行处理。
