# 通用科学网站数据筛选能力设计

本文档是 Phase 10 的架构审计与最小原型规划。目标不是马上做“全网科学爬虫”，而是把前几轮 NASA/ESA/Wikidata 扩源里已经验证过的安全链路，抽象成可复制的数据筛选能力：面对新的科学网站或科普网站时，先发现候选页，再判断质量、证据和准入等级，最后只把通过门禁的数据推进到 triples/narratives、shadow Chroma/Neo4j 和严格评估。

本轮不进行大规模联网爬取，不写正式 Neo4j/Chroma，不改变 `ACTIVE_SOURCE` 或 registry active 状态。

## 1. 当前可泛化能力

| 能力 | 当前实现 | 可泛化价值 | 当前边界 |
|---|---|---|---|
| Source manifest | `configs/source_manifests/*.json` | 用 allowed domain、seed、include/exclude、depth、limit、delay 固定采集边界 | 字段偏 Phase 1/2，缺少 robots、topic taxonomy、source trust、quality gate |
| Frontier preview | `scripts/preview_source_frontier.py` | 默认离线；显式 `--fetch-links` 后做限域链接发现；记录 accepted/skipped reason | 只按 URL/domain/path 过滤，不判断页面内容质量 |
| Raw-only ingest | `scripts/ingest_manifest_frontier.py` | 只写 `data/raw_json/<source>` 和 ingestion report，适合新源试采 | HTML 正文抽取很轻量，质量过滤主要靠 URL 与最短正文 |
| Raw materialization | `scripts/materialize_manifest_raw_records.py` | 把 raw 转 triples/narratives，并保留 source metadata | 转换逻辑强依赖 NASA/ESA/Wikidata 的页面结构和关系类型 |
| Strict/exploratory eval | `scripts/run_source_expansion_eval.py`、`evaluation/source_expansion/<source>/` | 把稳定事实和探索问题分流，避免为了数量牺牲 gate | query schema 和兼容白名单仍按固定 source 写死 |
| Shadow materialization | `scripts/preview_shadow_materialization.py`、`scripts/materialize_shadow_from_preview.py` | 使用 summary/files_written 或 preview selected，避免 stale 文件混入；Chroma/Neo4j shadow 隔离 | source 列表固定，通用新源还缺安全注册流程 |
| Shadow graph probe | `scripts/probe_shadow_graph.py` | 只读验证 Neo4j source namespace、metadata contract、样例关系 | 主要证明已导入 source，不负责新站质量判断 |
| Source status provider | `src/source_expansion_status.py`、`scripts/report_source_expansion_status.py` | 从本地 report 汇总 raw/triples/narratives/gate/shadow 状态 | 默认只看 `nasa`、`esa`、`wikidata` |

结论：现有项目已经具备“限域发现 -> raw-only -> 本地转换 -> strict gate -> shadow materialize -> status”的骨架。通用化的缺口不在“怎么无限多爬”，而在“页面是否值得收、证据是否足够、低质量内容是否能挡住”。

## 2. 当前固定源耦合

| 区域 | 文件 | 固定耦合 |
|---|---|---|
| Source registry | `config.py` | `SOURCE_REGISTRY` 固定为 `zh_wikipedia`、`wikidata`、`nasa`、`esa`；`ACTIVE_SOURCE` 固定 `zh_wikipedia` |
| Router | `src/source_router.py` | `ALL_SOURCES`、ESA/NASA/Wikidata 优先级、关键词路由均写死 |
| Agent | `src/agent/llm_agent.py` | source display name、关系权威顺序、fixture 路径、auto source 顺序、fallback 逻辑按四源枚举 |
| GUI | `src/gui/main_window.py` | source buttons/dropdown、默认 limit、状态展示 source 列表固定 |
| Adapter | `src/source_adapters/nasa.py`、`src/source_adapters/esa.py`、`src/source_adapters/wikidata.py` | NASA fact sheet、ESA mission、Wikidata claims 都是专用解析 |
| Materializer | `scripts/materialize_manifest_raw_records.py` | `FACT_SUBJECTS`、`MISSION_TARGETS`、Wikidata property map、NASA/ESA low-quality URL token 写在脚本里 |
| Eval | `scripts/run_source_expansion_eval.py`、`evaluation/source_expansion/<source>/*` | strict query、compat whitelist、expected relation 和 schema contract 按 source 固定 |

这些耦合目前是合理的：它们让三源扩展能低风险落地。但它们不能直接支撑“任意科学网站”。下一步应该新增一层通用质量筛选，不急着把 registry 和 Agent 改成动态插件系统。

## 3. 通用科学网站筛选架构

### 3.1 Source Manifest 2.0

在现有 manifest 基础上扩展，而不是另起一套配置。建议新增字段：

```json
{
  "source_name": "example_science_site",
  "source_mode": "trusted|unknown",
  "allowed_domains": ["example.org"],
  "seed_urls": ["https://example.org/science/"],
  "discovery": {
    "use_sitemap": true,
    "use_internal_links": true,
    "use_rss": false,
    "use_search_pages": false,
    "max_depth": 2,
    "max_pages_per_run": 50,
    "max_discovery_fetch_pages": 10
  },
  "robots": {
    "respect_robots_txt": true,
    "crawl_delay": 1.0,
    "user_agent": "tololo-source-quality-preview/1.0"
  },
  "topic_taxonomy": ["astronomy", "planetary_science", "space_mission"],
  "include_path_keywords": ["science", "planet", "mission"],
  "exclude_path_keywords": ["news", "image", "video", "gallery", "privacy"],
  "quality_gate": {
    "accept_score": 70,
    "review_score": 45,
    "min_text_chars": 500
  },
  "notes": "Generic science source candidate; preview before ingest."
}
```

`trusted` 只表示来源可信度起点更高，不等于页面自动通过。`unknown` 来源必须更依赖引用质量、事实密度和人工抽样。

### 3.2 Page Discovery

Discovery 只负责“候选发现”，不负责准入。所有入口必须限域、限量、限速、可报告：

- Sitemap：读取 `sitemap.xml` 或 sitemap index，最多取 N 条 URL。
- 站内链接：从 accepted seed 页抽取 `<a href>`，应用 domain/path/depth/duplicate 规则。
- RSS/索引页：适合科学机构公告和任务更新，但默认进入 `exploratory`，不要直接升 strict。
- 搜索页：风险最高，容易抓到重复、导航和低质量列表页；默认关闭，只允许 manifest 显式启用。
- URL 去重：规范化 scheme/host/path、去 fragment，保留 query 只在 manifest 允许时使用。

Phase 11 不实现真实 discovery，只用本地 fixture 模拟不同 URL 和 HTML 类型。

### 3.3 Page Quality Classifier

分类器输入应是本地 `PageCandidate`：`url`、`title`、`html`、`text`、`metadata`、`source_mode`、`topic_taxonomy`。输出：

```text
score: 0-100
triage: accepted | review_needed | rejected | exploratory
labels: science_related, fact_page, encyclopedia_page, paper_page, mission_page, news_page, media_page, marketing_page, navigation_page
reasons: short_text, has_fact_table, has_citations, low_science_terms, excluded_media_path, too_many_nav_links ...
```

最低限度的规则：

- 科学相关：标题、正文、URL 命中 taxonomy 词汇。
- 高价值页：fact table、百科式页面、mission overview、paper abstract/reference。
- 探索页：新闻、任务动态、采访、活动页；可入 raw/exploratory，不进 strict。
- 拒绝页：图片/视频/图库、搜索结果、标签页、隐私/政策、纯导航、营销页、正文过短。

### 3.4 Content Extractor

先用标准库 `html.parser` 做小型原型，不引入新依赖。提取：

- 标题：`<title>`、`h1`。
- 正文：跳过 `script/style/nav/footer/header` 的文本。
- 表格：`tr/th/td` 行，用于高置信 triple candidate。
- 元数据：canonical URL、description、published/modified time、作者/机构。
- 引用：`a[href]`、`cite`、reference heading 附近链接。

后续如果确实需要更强正文抽取，再考虑接入已有依赖或专用库；Phase 11 不新增依赖。

### 3.5 Evidence Scoring

建议用可解释加权分，不上机器学习模型：

| 维度 | 示例规则 |
|---|---|
| 来源可信度 | `trusted` 起点更高；政府/大学/机构域名可加分，未知商业站不加 |
| 文本长度 | 过短直接拒绝；中等长度进入 review；长正文不自动通过 |
| 事实密度 | 数值+单位、表格、定义句、任务参数、实体关系越多越好 |
| 重复率 | 与已收页面标题/正文高度重复则降分 |
| 更新时间 | 有明确 modified/published 时间加分；太旧不一定拒绝，但标记 |
| 引用质量 | 指向论文、机构、数据页、DOI、NASA/ESA/Wikidata 等加分 |
| 领域相关度 | 与 topic taxonomy 命中越强越好 |
| 低质量信号 | 导航链接密集、推荐列表、图库、视频、营销 CTA、cookie/privacy 降分或拒绝 |

评分只决定 triage，不直接写正式库。

### 3.6 Data Triage

- `accepted`：高分事实/百科/任务页，可进入 raw-only ingest，后续生成 triples/narratives。
- `review_needed`：分数中等或证据不足，允许保存到 review report，不进入 strict。
- `rejected`：明显低质量或越界页面，只记录原因。
- `exploratory`：科学相关但新闻性、动态性或证据不稳定；可做探索 query，不进入 strict gate。

### 3.7 Triple Confidence

Triple candidate 要带置信度和来源证据：

- 高置信：HTML 表格、结构化 metadata、Wikidata/API claims、清晰字段名和值。
- 中置信：正文里的稳定定义句和任务目标句，需要 relation whitelist。
- 低置信：普通段落关键词推断，只能进入 exploratory，不进入 strict。
- 拒绝：导航、相关推荐、广告、页脚、搜索摘要、媒体说明中的弱关系。

建议 metadata 包含：`source_name`、`source_url`、`page_title`、`schema_version`、`origin`、`confidence`、`evidence_text`、`quality_score`、`triage`。

### 3.8 Promotion Gate

新站数据不应直接成为 strict source。升级路径：

1. `candidate`：只跑本地 quality scoring 和 preview report。
2. `raw_exploratory`：只写 raw 和 exploratory report。
3. `shadow_materialized`：只写 shadow triples/narratives/Chroma/Neo4j namespace。
4. `strict_candidate`：人工抽样通过，新增 strict query，source/metadata/boundary breaks 为 0。
5. `strict_passed`：strict eval 通过，但 registry 仍 disabled。
6. `active_candidate`：只有用户明确批准后，才讨论切换 active 或 GUI 默认接入。

## 4. Phase 11 最小原型

Phase 11 建议只做纯本地、可测、无网络的页面质量评分原型。

### 文件规划

- 新增 `src/source_quality/page_quality.py`
  - 定义 `PageQualityResult` dataclass。
  - 提供 `score_page(url, html="", text="", title="", source_mode="unknown", topic_taxonomy=None) -> PageQualityResult`。
  - 使用标准库 `html.parser` 提取标题、正文、链接、表格行。
  - 输出 `score`、`triage`、`labels`、`reasons`。
- 新增 `scripts/score_candidate_pages.py`
  - 参数：`--input path`、`--json-out path`。
  - 输入可以是单个 HTML 文件、目录，或 raw JSON。
  - 只打印/写 scoring report，不写 `data/`、Neo4j、Chroma。
- 新增 `tests/test_page_quality.py`
  - 用 5-10 个内联 HTML fixture，不访问网络。
  - 覆盖 `accepted`、`review_needed`、`rejected`、`exploratory`。
  - 覆盖脚本源码不包含删除调用，或测试输出路径在临时目录。

### Fixture 建议

| Fixture | 预期 |
|---|---|
| 行星 fact table 页 | `accepted`，labels 包含 `science_related`、`fact_page` |
| 任务 overview 页 | `accepted` 或 `review_needed`，labels 包含 `mission_page` |
| 论文 abstract + references 页 | `accepted`，labels 包含 `paper_page` |
| 新闻稿 | `exploratory`，不进 strict |
| 图片图库 | `rejected`，reason `media_or_gallery` |
| 搜索结果页 | `rejected`，reason `search_or_index_page` |
| 隐私/政策页 | `rejected`，reason `policy_page` |
| 短营销页 | `rejected` 或 `review_needed`，reason `short_text`、`marketing_page` |

### 最小评分规则

Phase 11 不追求智能，只要可解释：

- 初始分：`trusted=20`，`unknown=0`。
- 科学 taxonomy 命中：最多 +25。
- fact table：+25。
- mission/paper/encyclopedia 信号：+15。
- 引用/外部证据：最多 +10。
- 正文长度：足够 +10，过短 -30。
- URL/标题含 news：标为 `exploratory`，除非同时是明显 fact page。
- URL/标题含 image/video/gallery/search/privacy/tag：直接 `rejected`。

默认阈值：

- `score >= 70`：`accepted`
- `45 <= score < 70`：`review_needed`
- 科学相关但新闻/动态页：`exploratory`
- 明确低质量或 `score < 45`：`rejected`

## 5. 当前系统离“通用科学网站筛选”还差什么

- 缺少内容级质量分类：现在 URL include/exclude 很强，但正文质量判断弱。
- 缺少通用 evidence score：现有三源 gate 验证结果质量，但不负责新页面准入。
- 缺少新源生命周期：registry 只有固定四源，没有 candidate/review/shadow/strict 的通用状态机。
- 缺少通用 extractor contract：NASA/ESA/Wikidata 转换器可用，但不是通用网页解析器。
- 缺少人工抽样接口：目前报告可读，但还没有 review queue 或抽样标注文件。
- 缺少动态 source UI：GUI/Agent 仍按固定 source 枚举显示和路由。

## 6. 不要现在做的事

- 不要做全网或“任意域名”爬取。
- 不要把未知网站数据直接写入正式 Neo4j/Chroma。
- 不要把 `SOURCE_REGISTRY` 改成自动激活新源。
- 不要把新闻、图库、搜索结果靠关键词硬转 triples。
- 不要引入机器学习分类器或大依赖；课程项目先用可解释规则更稳。
- 不要追求 100% 自动化准入；未知来源至少要保留 `review_needed` 和抽样门禁。

## 7. 验证策略

Phase 11 验证只跑本地：

```powershell
venv\Scripts\python.exe scripts\score_candidate_pages.py --input tests\fixtures\source_quality --json-out evaluation\source_quality\fixture_quality_report.json
venv\Scripts\python.exe -m unittest discover tests
```

验收标准：

- 不联网。
- 不写 `data/`、Neo4j、Chroma。
- accepted/review_needed/rejected/exploratory 都有测试覆盖。
- 每个结果都有 score、labels、reasons。
- 明确低质量页面不会进入 accepted。
- 默认 source 仍为 `zh_wikipedia`，三扩源仍 disabled/shadow。

## 8. 推荐路线

推荐 Phase 11 采用“本地 fixture + 规则评分器 + 只读 scoring report”。它最小，但能补上当前系统最关键的缺口：在采集之前判断页面是否值得收。等该评分器稳定后，再把它接到 `preview_source_frontier.py` 或 `ingest_manifest_frontier.py` 的显式参数中，例如 `--quality-gate`，并继续保持 raw-only、shadow-first 的边界。
