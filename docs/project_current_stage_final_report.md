# 项目当前阶段最终汇总报告

截至 Phase 35，项目已经从“把原有中文维基知识图谱做稳”推进到“两条并行但隔离的能力”：一条是 NASA / ESA / Wikidata 三源 shadow 扩源验证，另一条是面向通用科学网站的新源筛选、人工审阅、计划预览和执行前确认闭环。当前阶段仍以安全预审和可复现实验为主，没有开启无限制联网爬取，也没有把候选源写入正式数据管线。

## 1. 当前定位

项目现阶段可以这样描述：

> 默认问答和正式图谱仍以 `zh_wikipedia` 为 active source；新增科学数据源先进入 shadow / sandbox 流程，通过质量评分、人工抽样和计划审批后，才可能进入未来的小批量 preview-only 探测。

这意味着系统不是只会处理四个固定来源，而是在形成一套“新科学网站接入前的准入流程”：先验证 manifest，再离线看候选样本，再做人审，再生成计划和命令卡，最后才考虑由用户明确批准的网络 preview。

## 2. 已完成能力

### 工程卫生与默认边界

- `ACTIVE_SOURCE` 保持 `zh_wikipedia`。
- `nasa`、`esa`、`wikidata` 仍是 disabled / shadow 路线，不改变默认回答来源。
- 扩源流程默认不清正式库，不覆盖正式 Chroma / Neo4j，不把实验源直接推到主流程。
- 多阶段回归测试持续覆盖默认源边界、manifest 校验、quality gate、sandbox review 和审批报告。

### 三源 shadow 扩源

三源扩源已经完成 raw / triples / narratives / shadow Chroma / shadow Neo4j 的验证闭环：

| Source | Raw | Triples | Narratives | Strict Gate | Shadow Chroma | Shadow Neo4j |
|---|---:|---:|---:|---|---:|---:|
| NASA | 79 | 34 | 323 | pass | 15 | 4 nodes / 3 rels |
| ESA | 73 | 191 | 455 | pass | 427 | 42 nodes / 41 rels |
| Wikidata | 47 | 228 | 161 | pass | 161 | 13 nodes / 12 rels |

关键证据：

- `docs/source_expansion_delivery_report.md`
- `evaluation/source_expansion/source_expansion_status_report.json`
- `evaluation/source_expansion/shadow_graph_probe_report.json`
- `evaluation/source_expansion/nasa/nasa_report.json`
- `evaluation/source_expansion/esa/esa_report.json`
- `evaluation/source_expansion/wikidata/wikidata_report.json`

### 通用科学网站筛选闭环

从 Phase 18 到 Phase 34，系统已经建立了一条候选科学网站接入前的安全链路：

1. **Manifest 2.0**
   - 支持 `source_mode`、`topic_taxonomy`、`quality_gate`、`quality_notes`。
   - NASA / ESA / Wikidata 已使用 Manifest 2.0 字段。
   - 新候选源保持 unregistered / sandbox only。

2. **Manifest validator / preflight**
   - 校验必需字段、合法 source mode、quality gate 阈值和 `entity_data` 安全规则。
   - 关键报告：`evaluation/source_quality/source_manifest_validation_report.json`。

3. **Sandbox candidates**
   - 未注册 manifest 可以进入 sandbox dry-run / fixture-only 评分。
   - 输出只在 `evaluation/source_quality/sandbox/`，不写正式 `data/raw_json`、triples、Chroma、Neo4j。

4. **Fixture candidate pack**
   - 为 official science、academic、publisher、generic unknown 以及 Phase 28 候选科学网站准备本地 HTML / JSON 样本。
   - 用离线样本验证 accepted / review_needed / exploratory / rejected 的分布。

5. **Review summary**
   - 批量汇总多个 candidate manifest 的评分结果、推荐动作和人工抽样建议。
   - Phase 28 候选包结果：6 个候选源，`manual_sample_first=4`，`ready_for_small_batch=2`。

6. **Review decision 回填**
   - 支持生成待审模板，并读取人工填写的 `pending`、`approved_for_small_batch`、`needs_manifest_fix`、`rejected`。
   - Phase 29 示例中，`noaa_climate_candidate` 和 `data_portal_candidate` 进入 approved small-batch plan preview。

7. **Approved plan preview**
   - 只生成未来计划，不执行抓取。
   - Phase 29 计划包含 2 个 item，`execution_status=not_run`。

8. **Offline fixture quality**
   - 对已批准候选源做离线样本质量验证。
   - Phase 30 样本：2 个 source、6 条样本，分布为 accepted 2 / exploratory 1 / review_needed 1 / rejected 2。

9. **Network probe approval package**
   - Phase 31 / Phase 32 只生成未来 preview-only 网络探测计划和审批包。
   - 每个 item 都保留 `network=false`、`execution_status=not_run`、`formal_pipeline_write=false`。

10. **Approval decisions 与单源命令卡**
    - Phase 33 示例：`noaa_climate_candidate` 被回填为 `approved_for_preview_probe`，`data_portal_candidate` 保持 pending。
    - Phase 34 只为 NOAA 生成手动命令卡，命令文本明确标注 `NOT EXECUTED / MANUAL ONLY / PREVIEW ONLY`。

关键证据：

- `docs/general_science_source_screening_overview.md`
- `docs/general_science_source_quality_design.md`
- `evaluation/source_quality/sandbox/candidate_science_sites_summary_phase28.json`
- `evaluation/source_quality/sandbox/candidate_science_sites_summary_phase29_filled.json`
- `evaluation/source_quality/sandbox/candidate_science_sites_approved_plan_phase29.json`
- `evaluation/source_quality/sandbox/offline_fixture_quality_phase30.json`
- `evaluation/source_quality/sandbox/preview_network_probe_plan_phase31.json`
- `evaluation/source_quality/sandbox/network_probe_approval_package_phase32.json`
- `evaluation/source_quality/sandbox/network_probe_approval_decisions_phase33_filled.json`
- `evaluation/source_quality/sandbox/manual_preview_command_card_phase34.json`

## 3. 回答用户关心的问题

### 为什么不一次性大规模爬取？

科学网站结构差异很大：有事实页、任务页、论文摘要、新闻、图库、搜索页、隐私页、导航页和商业介绍页。直接大爬会把噪声和低质量页面带进 raw、triples、向量库甚至图谱，后续清理成本很高，也容易破坏默认问答稳定性。

当前做法是先用 Manifest 2.0 描述边界，再用质量评分和 sandbox report 做预审。只有通过离线样本、人审和命令卡确认的源，才考虑进入下一步小限额 preview。

### 这是不是说明筛查能力还弱？

不是。现在的重点不是“抓得多”，而是“知道什么该进、什么不该进、为什么不该进”。项目已经能把候选源拆成 manifest、样本、评分、recommendation、review decision、plan preview 和 manual command card。这比直接扩数据更适合课程展示，因为它证明系统有可复制的准入方法。

### 这如何通向更通用的科学网站筛查？

新增候选源不需要直接改正式 registry。可以先复制 example manifest，准备本地 fixture，跑 sandbox summary，得到 recommendation，再由人工审阅决定是否生成 preview-only plan。这个流程能迁移到 NOAA、数据门户、大学实验室、论文平台、博物馆/天文台、出版平台等不同类型的网站。

## 4. 当前边界

- 没有执行真实联网 preview。
- 没有执行 fetch / crawl / ingest。
- 未注册候选源没有写入正式 `data/raw_json`、triples、narratives、Chroma 或 Neo4j。
- `ACTIVE_SOURCE` 仍是 `zh_wikipedia`。
- Phase 34 的 NOAA 命令卡只是人工操作卡，不是执行结果。
- `approved_for_preview_probe` 只表示“未来可以由用户手动批准后运行 preview-only 探测”，不会自动触发任何网络请求。

## 5. 距离“完美”的差距

- 真实站点样本还需要用户或人工流程提供，不应由系统默认大规模抓取。
- 不同科学领域需要更细的 source-specific extractor，例如气候数据、论文摘要、实验室项目页、数据门户元数据。
- 需要更强的去重、引用可信度、更新时间、实体对齐和冲突处理。
- 需要把人工 review decision 变成可累计的评估集，用来反哺质量规则。
- 需要受控真实小批量 preview 后，统计误拒、误收、抽样准确率和页面类型覆盖率。
- 需要在 shadow namespace 内进一步验证从 raw 到 triples / narratives / retrieval 的质量。

## 6. 下一步路线

### 路线 A：继续离线增强

适合答辩前求稳。继续扩展 fixture pack，增加更多页面类型和中文/英文科学网站样本，完善质量评分报告与人工审阅模板。

### 路线 B：用户明确批准后，NOAA 5 页 preview-only 网络探测

使用 Phase 34 生成的命令卡作为人工确认材料。执行前需要再次确认 allowed domains、max pages、rate limit、输出路径和 no formal write。执行后仍只写 `evaluation/source_quality/sandbox/`。

### 路线 C：准备答辩材料

把 `source_expansion_delivery_report.md`、`general_science_source_screening_overview.md` 和本报告整理为展示材料：先讲默认系统稳定，再讲三源 shadow 扩源，最后讲通用科学网站准入闭环。

## 7. 一句话结论

项目当前最重要的成果不是“已经把所有科学网站都爬进来”，而是已经把扩源变成一套可验证、可审阅、可回退、不会污染正式知识库的工程流程。下一步只有在用户明确批准后，才应进入小限额 preview-only 网络探测。
