# 通用科学网站筛选闭环总览

本文用于课程展示，汇总 TololoAgent 从 Phase 18 到 Phase 26 形成的“新科学网站接入前筛选闭环”。它想说明一件事：项目现在不只是能处理 `zh_wikipedia`、`nasa`、`esa`、`wikidata` 四个固定来源，也开始具备一套可复制的科学网站准入流程。

这套流程目前仍是预审、抽样、计划和执行前确认，不是无限制全网爬虫，也不会自动把未知网站写入正式知识库。

## 1. 当前阶段定位

TololoAgent 的默认主源仍是 `zh_wikipedia`。NASA、ESA、Wikidata 扩源已经完成 shadow 数据、strict gate、Chroma/Neo4j 影子验证；在此基础上，Phase 18-26 把经验抽象成“通用科学网站筛选流程”：

```text
Manifest 2.0
  -> validator / preflight
  -> sandbox candidates
  -> fixture candidate pack
  -> sandbox review summary
  -> human review decisions
  -> approved plan preview
  -> manual command skeleton
```

每一步都只推进“证据”和“决策”，不会绕过人工确认直接采集。

## 2. 已完成能力链路

| 阶段 | 能力 | 关键文件 / 报告 | 边界 |
|---|---|---|---|
| Phase 18 | Manifest 2.0 example library | `configs/source_manifests/examples/` | 只提供 academic / publisher / generic_unknown / official_science 模板 |
| Phase 18 | Manifest validator | `scripts/validate_source_manifests.py` | 校验字段、source_mode、quality_gate，不抓取 |
| Phase 19 | `--manifest` 通用离线 preview | `scripts/preview_source_frontier.py` | 未注册 manifest 强制 offline，不进入真实 ingest |
| Phase 20 | 单 manifest sandbox report | `scripts/sandbox_manifest_candidates.py` | 只写 `evaluation/source_quality/sandbox/` |
| Phase 21 | 批量 sandbox review summary | `scripts/report_sandbox_candidate_reviews.py` | 汇总多个 example manifest，生成 JSON/Markdown |
| Phase 22 | Fixture candidate pack | `tests/fixtures/source_quality/` | 用本地样本复现 accepted / review / exploratory / rejected |
| Phase 23 | Review decision loop | `candidate_review_summary_phase23.*` | 自动推荐不等于批准，必须人工抽样 |
| Phase 24 | Review template / 回填 | `candidate_review_decisions_template_phase24.json` | 人工填写只影响报告，不触发 ingest |
| Phase 25 | Approved plan preview | `approved_small_batch_plan_phase25.*` | `execution_status=not_run` |
| Phase 26 | Manual command skeleton | `small_batch_command_skeleton_phase26.*` | 命令草案标注 `NOT EXECUTED / DRY RUN` |

## 3. 当前验证证据

### 固定三源扩源成果

三源 shadow 数据已在早期扩源阶段完成并通过 strict gate：

| Source | raw JSON | triples | narratives | strict gate | Chroma shadow | Neo4j shadow |
|---|---:|---:|---:|---|---:|---:|
| NASA | 79 | 34 | 323 | accuracy 1.0 | 15 | 4 nodes / 3 rels |
| ESA | 73 | 191 | 455 | accuracy 1.0 | 427 | 42 nodes / 41 rels |
| Wikidata | 47 | 228 | 161 | accuracy 1.0 | 161 | 13 nodes / 12 rels |

这些结果说明项目原有扩源不是停在 raw 文件，而是已经走到 shadow materialization、source isolation 和 gate 验证。

### 通用筛选链路证据

关键本地报告：

- `evaluation/source_quality/source_manifest_validation_report.json`
  - `validated=7`
  - `failed=0`
- `evaluation/source_quality/sandbox/candidate_review_summary_phase22.json`
  - example sources: 4
  - fixture candidates: 16
  - recommendations: `manual_sample_first=2`、`needs_manifest_fix=1`、`ready_for_small_batch=1`
- `evaluation/source_quality/sandbox/candidate_review_summary_phase24_filled.json`
  - `official_science_example` 被人工回填为 `approved_for_small_batch`
  - `generic_unknown_example` 被回填为 `needs_manifest_fix`
- `evaluation/source_quality/sandbox/approved_small_batch_plan_phase25.json`
  - approved sources: 1
  - plan items: 1
  - execution status: `not_run`
- `evaluation/source_quality/sandbox/small_batch_command_skeleton_phase26.json`
  - command skeletons: 1
  - execution status: `not_run`
  - safety guards: `NOT EXECUTED`、`DRY RUN`、`manual approval required`、`ACTIVE_SOURCE unchanged`、`formal writes disabled`
- `evaluation/source_quality/sandbox/manual_preview_command_card_phase34.json`
  - command cards: 1
  - approved source: `noaa_climate_candidate`
  - safety guards: `NOT EXECUTED`、`MANUAL ONLY`、`PREVIEW ONLY`、`network=false`、`formal_pipeline_write=false`

完整回归测试：

```powershell
venv\Scripts\python.exe -m unittest discover tests
```

Phase 26 后结果：

```text
Ran 302 tests ... OK
```

## 4. 用户关心问题的回应

### 为什么不直接无限多爬？

因为“能爬到很多页面”不等于“能进入知识库”。科学网站里混有新闻、图库、搜索页、标签页、隐私政策、活动页、广告页、登录页和重复导航。直接大规模抓取会带来三个问题：

- 低质量文本进入 Chroma 后会污染检索排序。
- 弱规则抽取容易把导航、推荐、新闻摘要误转成 triples。
- 未知网站的版权、robots、可信度和更新语义都需要先审查。

所以当前流程先做 manifest 限域，再做 sandbox 评分，再人工抽样，最后才生成小批量计划。这不是保守到不能扩，而是把扩源变成可解释、可复跑、可回退。

### 为什么需要小批量、人审和质量门？

新源最危险的地方不是第一页，而是第二层、第三层链接里的噪声。质量门和人工抽样的作用是让系统先回答：

- 这个网站的好页面长什么样？
- 噪声页面能不能被挡住？
- include/exclude 规则是否误杀高价值页面？
- accepted 页面是否真的能支撑后续 raw、narratives、triples 和 eval query？

只有这些问题有证据后，才值得进入小批量真实抓取。

### 这是不是说明筛查能力还弱？

不是。相反，筛查能力正在系统化。现在的能力不是“凭一个关键词判断能不能爬”，而是形成了完整闭环：

```text
模板 -> 校验 -> 离线候选 -> 本地样本 -> 自动评分 -> 人工审阅 -> 回填 -> 计划 -> 命令草案
```

这个闭环的价值在于：以后换一个科学网站，不需要重新设计流程，只需要复制 manifest、准备样本、跑同一套预审报告。

## 5. 当前边界

必须如实说明，当前通用科学网站流程还没有做这些事：

- 不做全网爬虫。
- 不对未注册 manifest 真实 ingest。
- 不把未知网站写入 `data/raw_json`、triples、Chroma 或 Neo4j。
- 不改变 `ACTIVE_SOURCE`。
- 不把 `approved_for_small_batch` 自动变成执行命令。
- 不保证所有科学网页都能正确分类。

这些边界是有意保留的。课程展示时可以把它解释为安全设计：项目把“扩得更多”和“不要污染知识库”同时纳入目标。

## 6. 离“完美”的差距

要达到更强的通用科学网站筛选能力，还需要继续补这些方向：

- 更多真实站点模板：NASA/ESA 之外的大学实验室、科研机构、出版社、开放数据平台。
- 更细领域分类：天文、地学、生物、物理、医学科普不能完全共用同一组关键词。
- 更强正文抽取：现在是轻量 HTML/text 规则，后续可加入更稳的正文和表格抽取。
- 去重与可信度：需要 URL canonical、正文相似度、来源层级、引用质量、发布时间等指标。
- 实体对齐：新源里的实体需要和已有图谱实体合并或区分。
- 人工标注反馈：把人工 review 的结果反哺质量规则，而不是只停留在报告里。
- 受控真实小批量执行：从 command skeleton 进入真正 preview / raw-only trial，但仍要限域、限速、限量。
- 评估指标：把 accepted/rejected 的人工抽样准确率变成可量化指标。

## 7. Phase 28+ 路线图

Phase 28 已经把流程从四个 example manifest 扩展到一批更接近真实世界的候选科学网站类型，但仍保持 `candidate / sandbox only`：

- 候选清单：`configs/source_manifests/candidates/science_site_candidates.json`
- 候选 manifest：`configs/source_manifests/candidates/`
- 离线样本包：`tests/fixtures/source_quality/*_candidate_candidates.json`
- 预审报告：`evaluation/source_quality/sandbox/candidate_science_sites_summary_phase28.json`

这批候选覆盖 NOAA/USGS/NIH 类政府科学机构、大学实验室、预印本/论文元数据、期刊 landing、博物馆/天文台科普、标准或数据门户等类型。它们没有进入正式 `SOURCE_REGISTRY`，也不会触发真实抓取；作用是证明同一套 manifest + fixture + sandbox review 流程可以迁移到更宽的科学网站。

Phase 28 预审结果：

| Source | 类型 | candidates | triage 摘要 | recommendation |
|---|---|---:|---|---|
| `noaa_climate_candidate` | government science agency | 3 | accepted 1 / exploratory 1 / rejected 1 | ready_for_small_batch |
| `data_portal_candidate` | standards/data portal | 3 | accepted 1 / review 1 / rejected 1 | ready_for_small_batch |
| `university_lab_candidate` | university lab | 3 | review 3 | manual_sample_first |
| `arxiv_preprint_candidate` | preprint metadata | 3 | review 2 / rejected 1 | manual_sample_first |
| `journal_publisher_candidate` | academic publisher | 3 | review 3 | manual_sample_first |
| `museum_observatory_candidate` | museum/observatory education | 3 | review 1 / exploratory 1 / rejected 1 | manual_sample_first |

Phase 29 已把这批 candidates 接入人审回填和计划预览闭环：

- 人审模板：`evaluation/source_quality/sandbox/candidate_science_sites_review_template_phase29.json`
- 示例回填：`tests/fixtures/source_quality/candidate_review_decisions_phase29.json`
- 回填汇总：`evaluation/source_quality/sandbox/candidate_science_sites_summary_phase29_filled.json`
- 计划预览：`evaluation/source_quality/sandbox/candidate_science_sites_approved_plan_phase29.json`

示例回填把 `noaa_climate_candidate` 和 `data_portal_candidate` 标为 `approved_for_small_batch`，每个 approved sample size 为 8；其余四个候选仍为 `pending`。计划预览只包含这两个 approved source，且 `execution_status=not_run`、`network=false`、`formal_pipeline_write=false`。

建议后续按这个顺序推进：

1. **Phase 30：真实站点小样本 offline fixture**
   - 已新增 `scripts/report_offline_fixture_quality.py` 和 `docs/offline_fixture_quality_schema.md`。
   - 对 `noaa_climate_candidate` / `data_portal_candidate` 的本地样本输出离线质量门报告。
   - 报告固定标记 `network=false`、`execution_status=not_run`、`formal_pipeline_write=false`。

2. **Phase 31：受控 preview-only 网络探测**
   - 已新增 `scripts/render_preview_network_probe_plan.py`。
   - 把 Phase 29 approved plan 和 Phase 30 offline quality 合并成 future preview-only 网络探测计划。
   - 输出 `evaluation/source_quality/sandbox/preview_network_probe_plan_phase31.json`，但仍固定 `network=false`、`execution_status=not_run`、`formal_pipeline_write=false`。
   - 每个计划项默认 `max_pages<=10`，并要求显式人工批准后才可能进入未来网络 preview。

3. **Phase 32：preview-only 网络探测执行前审批包**
   - 已新增 `scripts/render_network_probe_approval_package.py`。
   - 读取 Phase 31 plan，生成 `evaluation/source_quality/sandbox/network_probe_approval_package_phase32.json`。
   - 每项列出 allowed domains、seed URL、max pages、rate limit、quality gate、风险和人工确认清单。
   - 仍固定 `approval_status=pending_user_approval`、`execution_status=not_run`、`network=false`、`formal_pipeline_write=false`。

4. **Phase 33：审批包签收 / approval decisions**
   - 已新增 `scripts/render_network_probe_approval_decisions.py`。
   - 可生成 `network_probe_approval_decisions_template_phase33.json`，让人工填写 `pending` / `approved_for_preview_probe` / `rejected` / `needs_revision`。
   - 示例回填见 `tests/fixtures/source_quality/network_probe_approval_decisions_phase33.json`。
   - 即使被批准，报告仍固定 `execution_status=not_run`、`network=false`，只表示未来可人工运行 preview-only 命令。

5. **Phase 34：approved preview-only 单源手动命令卡**
   - 已新增 `scripts/render_manual_preview_command_card.py`。
   - 读取 Phase 33 filled approval report，只为 `approved_for_manual_preview` 的源生成命令卡。
   - 当前示例只生成 `noaa_climate_candidate`：`evaluation/source_quality/sandbox/manual_preview_command_card_phase34.json`。
   - 命令卡仍固定 `execution_status=not_run`、`network=false`、`formal_pipeline_write=false`，命令文本标注 `NOT EXECUTED / MANUAL ONLY / PREVIEW ONLY`。

6. **Phase 35：raw-only sandbox ingest**
   - 只有用户显式批准后，才考虑真正 preview-only 网络探测或 raw-only sandbox trial。
   - 仍只写 sandbox 或 isolated raw report，不进 triples/Chroma/Neo4j。

7. **Phase 36：source-specific extractor / eval**
   - 对通过筛选的新源设计最小抽取器和 evaluation query。
   - 仍先走 shadow namespace。

7. **后续：扩大真实站点 fixture 覆盖**
   - 手动保存少量 HTML/JSON fixture。
   - 不联网批量爬。
   - 用人工标注结果反哺评分规则。

## 8. 展示时的一句话总结

TololoAgent 现在的扩源能力不再只是“多写几个爬虫入口”，而是在形成一套新科学网站进入知识库之前的安全准入流程：先用 Manifest 2.0 定义边界，再用本地质量门筛候选，用人工抽样做决策，最后只生成未执行的小批量计划和命令草案。它牺牲了一点速度，换来的是可解释、可复现、可审计，也更适合课程项目长期演进。
