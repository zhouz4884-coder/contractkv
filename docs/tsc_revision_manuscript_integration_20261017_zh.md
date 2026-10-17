# ContractKV：重构稿、图形与版面交付

日期：2026-10-17。以作者提供的round1压缩包为基线，完成正文重构、Fig.1重绘、Fig.2–6微调和实际编译；不新增实验，不改变测量结果。

入口：[主文与源码说明](../Paper/revision_integrated_20261017/README_zh.md)；[主文PDF](../Paper/revision_integrated_20261017/contractkv_tsc_integrated.pdf)；[补充实验PDF](../Paper/revision_integrated_20261017/contractkv_supplement.pdf)；[详细决策](../Paper/revision_integrated_20261017/audit/restructure_decisions_zh.md)。

## 这次叙事调整

主线不再按补实验的时间顺序展开，而是先让读者看到同一RAG模板的前缀断点，再解释为什么合法重排还需要行为准入和原子发布，最后用真实全成本性能、自由生成、治理摊销和驻留证据闭合论证。四项贡献不变。

主性能采用共同来源的保真三模型实验。另六来源Qwen 1.803倍保持独立；历史slack、开放到达、密度回放和严格闭环分别标识。没有把不同协议画成一条因果收益曲线。

## 对最新反馈的处理

- R1关于删减的建议已核对原信第115行，并用于压缩segment/dependency/layout定义、重复scope/证书说明、协议和图表报数，以及相关工作列表。
- 新Fig.1以三段结构表达断点、资格与发布、同模板授权复用。区别两个witness协议，不写semantic equivalence或multiple witnesses，不重复做模型验证，不暗示不同任务共用同一前缀。
- Fig.2认证工作保留真实比例并强调橙色顶边；(c)图内注明future requests/frozen wave clock；没有恢复柱顶小圆点。
- Fig.3主任务仍为HotpotQA/RepoBench；RULER仅在历史审计中保留，正文说明其2178/2442构成。正分计数与正确性严格区分，实际轨迹说明缩短。
- Fig.4采用Goodput under governance。Fig.5直接注明registered tenants并非concurrent GPU requests。Fig.6核心内容不改。

## 交付口径

主文12页，含六张图、两表、算法和参考文献。补充实验记录5页保留详细原结果。源码、绘图脚本、实际依赖、SHA清单、编译与版面检查一并提供。原上传29个文件逐字节核对未变，旧V7图不覆盖。

核心数值和编译检查见`audit/manuscript_QA.json`，独立解包重画/编译见`audit/independent_reproduction.json`。外部出版元数据沿用上传稿；本轮核对的是引用键、首次出现顺序、标签及编译一致性，不宣称重新核查了每项参考文献。

正式Response Letter与作者简介未在本轮代写；当前是完整的作者审阅稿，不代替作者最终确认或期刊提交。

最新图形版为V9：Fig.1增加依赖图、布局梯、token校验、证书索引和物理KV结构；Fig.1/2双栏，Fig.3–6单栏，非直接缩图。所有实验数字不变，重新编译和独立复核。
