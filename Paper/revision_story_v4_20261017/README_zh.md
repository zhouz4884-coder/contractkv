# ContractKV 第三版正文：服务对象与服务收益（2026-10-17）

本版以7月25日实际投稿的四项贡献为锚点，以保真自由生成和完整成本实证为基础，恢复Service-Template Certificate、认证摊销、SLO与跨租户扩展的叙事位置。没有新GPU实验、模型推理、认证算法或阈值调整。

## 阅读入口

- [12页主文](contractkv_tsc_story_v4.pdf)
- [6页补充材料](contractkv_supplement.pdf)
- [修改与取舍记录](audit/story_v3_decisions_zh.md)
- [证据位置索引](audit/evidence_locations.csv)：实际PDF页码、章节/图表号和TeX源行，供正文确认后写Response Letter使用；不是已完成的回复信。
- [实际QA](audit/manuscript_QA.json)与[独立复现](audit/independent_reproduction.json)

## 主要变化

摘要、Introduction、Contribution 4和Conclusion明确连接模板身份、授权生命周期、25倍调用摊销与7.7倍未隐藏成本优势。主文保留严格全wall结果和真实负面数据；p99、作用域及归因限制放在实验和Discussion中集中解释。

Fig.1精修证书治理关系和block-aligned certified prefix；Fig.2保留；Fig.3增加分协议RULER条；Fig.4保留D1/D2治理代价及低调D0绝对参照，不写21.5倍标题；Fig.5/6保留，另以表恢复10–80身份扩展与四点冻结收益门禁。Fig.1/2双栏，Fig.3–6单栏。

补充材料正式交付五家族原始顺序、4695条segment位移及定义、密度趋势、RULER分组、执行时钟SLO、方法职责比较、冻结门禁和四方法matched-native质量分布。CPU聚合检查了原位移记录的算术和完整性，没有重新运行tokenizer来替代原测量。

## 源码与复现

入口为`contractkv_tsc_story_v4.tex`；`sections/`为正文及生成表；`figures/`为实际嵌入的矢量PDF、SVG与600-dpi PNG；`evidence/`保存本次恢复分析使用的冻结输入和表。

```powershell
python scripts/restore_evidence.py
python scripts/plot_figures.py
python scripts/plot_architecture.py
python scripts/build.py
python scripts/qa.py
```

绘图和QA依赖见`requirements.txt`，字体为当前Windows的Arial。编译使用随包的禁用shell-escape包装器，需要TeX Live/MiKTeX与IEEEtran。`evidence/run_tsc_multi_tenant.sh`仅作历史配置来源，复现上述图表不运行GPU脚本。

`input_*`审计文件是历史输入快照；当前导航以`evidence_locations.csv`为准。旧7月投稿、V9图和12页整合稿均保留。正文尚待作者审阅，正式Response Letter按当前计划在正文确认后逐条撰写。
