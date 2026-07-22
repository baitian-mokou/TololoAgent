# 扩源阶段总结报告

本文档汇总 TololoAgent 扩源任务 Phase 0-8 的实现与验证结果，用于课程答辩和提交说明。报告只引用本地 JSON、评估报告和 shadow namespace 结果；不包含 Neo4j 密码、API key 或本机私密配置。

## 1. 背景与原始问题

项目原先以 `zh_wikipedia` 为默认主源，`wikidata`、`nasa`、`esa` 作为扩展来源处于 shadow/disabled 状态。Phase 0 审计发现三类问题：

- NASA：早期采集入口很少，raw JSON 数量过低，部分场景只有少量固定页面，无法支撑扩展检索和评估。
- ESA：已有 smoke/query 覆盖较窄，任务页和太阳系相关页面入口分散，数据量与 query 覆盖都不足。
- Wikidata：主要依赖固定 seed/QID，适合结构化扩展，但不能当普通网页无限爬取。

因此后续目标不是“全站无边界爬取”，而是在可解释、可复跑、可限量的前提下扩大入口，并把新增 raw 变成可检索、可评估、可展示的 triples/narratives。

## 2. 方法

### Manifest-driven frontier

为三源新增 `configs/source_manifests/*.json`，用 manifest 明确：

- `allowed_domains`
- `seed_urls` 或 `seed_entities`
- include/exclude path keywords
- `max_depth`
- `max_pages_per_run`
- `crawl_delay`

`scripts/preview_source_frontier.py` 支持默认离线 preview，也支持显式 `--fetch-links` 做限域链接发现。preview 记录 accepted/skipped 及原因，先看 frontier 再采集，避免一口气全站爬。

### Raw-only ingest

`scripts/ingest_manifest_frontier.py` 只写：

- `data/raw_json/<source>/`
- `evaluation/ingestion/<source>_manifest_ingestion_report.json`

它不写 Neo4j/Chroma，不清旧数据，也不调用清理函数。报告记录 fetched/skipped/failed、原因、标题、正文长度和保存路径。

### Raw materialization

`scripts/materialize_manifest_raw_records.py` 将已有 raw JSON 本地转换为 source-isolated triples/narratives：

- `data/triples/<source>/*_triples.json`
- `data/triples/<source>/*_narratives.json`
- `data/triples/<source>/summary.json`
- `evaluation/ingestion/<source>_manifest_materialization_report.json`

该步骤不联网，不写 Neo4j/Chroma，不删除旧数据。

### Strict / exploratory query 分流

三源 evaluation query 被分为 strict gate 和 exploratory query：

- strict query 只验证当前数据已经稳定支持的事实、叙述、source metadata、source isolation、path routing、unit normalization、conflict case。
- exploratory query 保留新增探索问题，但不混入 strict gate，避免为了追求数量破坏稳定验收。

### Shadow materialization

`scripts/preview_shadow_materialization.py` 与 `scripts/materialize_shadow_from_preview.py` 使用 preview selected / summary.files_written 作为输入边界，避免扫入 stale triples。

Chroma shadow 写入隔离目录：

```text
data/chroma_db_shadow/<source>/
```

Neo4j shadow graph 写入 source namespace，不切换 active source，不清默认 `zh_wikipedia` 数据。

### Status provider 与 GUI 可见性

Phase 8 新增 `src/source_expansion_status.py` 和 `scripts/report_source_expansion_status.py`，从本地报告汇总 raw/triples/narratives、strict gate、Chroma shadow、Neo4j import/probe 状态。GUI Agent 页已有 source 下拉框，现可显示选中扩源的 shadow 状态；默认行为仍保持 `zh_wikipedia` / `auto`。

## 3. 数据成果

来源数据取自：

- `evaluation/source_expansion/source_expansion_status_report.json`
- `evaluation/source_expansion/shadow_graph_probe_report.json`
- `evaluation/source_expansion/<source>/<source>_report.json`

| Source | raw JSON | triples | narratives | strict queries | exploratory queries | strict gate | Chroma shadow | Neo4j probe |
|---|---:|---:|---:|---:|---:|---|---:|---|
| NASA | 79 | 34 | 323 | 16 | 16 | passed, accuracy 1.0 | 15 | 4 nodes / 3 rels |
| ESA | 73 | 191 | 455 | 9 | 32 | passed, accuracy 1.0 | 427 | 42 nodes / 41 rels |
| Wikidata | 47 | 228 | 161 | 47 | 16 | passed, accuracy 1.0 | 161 | 13 nodes / 12 rels |

Neo4j shadow probe 关系类型：

- NASA：`HAS_MASS` 3
- ESA：`OPERATED_BY` 41
- Wikidata：`LOCATED_IN` 8、`ORBITS` 2、`PART_OF` 2

## 4. 验证证据

### Source expansion strict gates

三源 strict gate 均通过：

- NASA：`evaluation/source_expansion/nasa/nasa_report.json`
- ESA：`evaluation/source_expansion/esa/esa_report.json`
- Wikidata：`evaluation/source_expansion/wikidata/wikidata_report.json`

关键指标：

- `exact_accuracy = 1.0`
- `source_filter_failure_count = 0`
- `metadata_contract_break_count = 0`
- `inferred_boundary_break_count = 0`
- `query_explainability_degraded_count = 0`

### Shadow graph probe

`evaluation/source_expansion/shadow_graph_probe_report.json` 显示：

- Neo4j connection ok
- `active_source = zh_wikipedia`
- `zh_wikipedia` registry active
- `nasa`、`esa`、`wikidata` registry disabled
- 三源 `contract_checks.passed = true`
- `bad_source_count = 0`
- `missing_metadata_count = 0`
- `missing_schema_count = 0`

### Default source boundary smoke

`scripts/smoke_default_source_boundary.py` 通过，报告路径：

```text
evaluation/default_source_smoke_report.json
```

它验证默认主源边界仍然可用，扩源 shadow 状态没有破坏 `zh_wikipedia` 默认行为。

### Unit tests

完整测试命令：

```powershell
venv\Scripts\python.exe -m unittest discover tests
```

Phase 8 收口时结果为：

```text
Ran 246 tests ... OK
```

## 5. 安全边界

本轮扩源全程保持以下边界：

- `ACTIVE_SOURCE` 仍为 `zh_wikipedia`。
- `nasa`、`esa`、`wikidata` 仍为 `disabled` / shadow。
- 不删除、不移动、不清空 `data/`、`venv/`、`models/`、Chroma 或生成数据。
- 不调用 `clear_source_ingestion_outputs`。
- Chroma shadow 写入 `data/chroma_db_shadow/<source>/`，不替换正式 Chroma 库。
- Neo4j graph import/probe 使用 source namespace，不清默认图数据。
- Neo4j 密码只通过环境变量使用，不写入配置、README 或报告。

## 6. 复现命令

以下命令展示从 preview 到验证的最小复现路径。真实运行时请按 source 分批执行，避免一次性全站爬取。

### Frontier preview

```powershell
python scripts/preview_source_frontier.py --source nasa --limit 20
python scripts/preview_source_frontier.py --source esa --limit 20
python scripts/preview_source_frontier.py --source wikidata --limit 20
```

### Fetch-links preview

```powershell
python scripts/preview_source_frontier.py --source nasa --fetch-links --limit 150 --json-out evaluation/source_frontiers/nasa_frontier.json
python scripts/preview_source_frontier.py --source esa --fetch-links --limit 150 --json-out evaluation/source_frontiers/esa_frontier.json
python scripts/preview_source_frontier.py --source wikidata --limit 150 --json-out evaluation/source_frontiers/wikidata_frontier.json
```

### Raw-only ingest

```powershell
python scripts/ingest_manifest_frontier.py --source nasa --limit 80 --frontier-json evaluation/source_frontiers/nasa_frontier.json
python scripts/ingest_manifest_frontier.py --source esa --limit 80 --frontier-json evaluation/source_frontiers/esa_frontier.json
python scripts/ingest_manifest_frontier.py --source wikidata --limit 80 --frontier-json evaluation/source_frontiers/wikidata_frontier.json
```

### Raw materialization

```powershell
python scripts/materialize_manifest_raw_records.py --source nasa --limit 120
python scripts/materialize_manifest_raw_records.py --source esa --limit 120
python scripts/materialize_manifest_raw_records.py --source wikidata --limit 120
```

### Strict eval

```powershell
python scripts/run_source_expansion_eval.py --source nasa
python scripts/run_source_expansion_eval.py --source esa
python scripts/run_source_expansion_eval.py --source wikidata
```

### Shadow materialization

```powershell
python scripts/preview_shadow_materialization.py --source nasa
python scripts/materialize_shadow_from_preview.py --source nasa --apply
```

ESA/Wikidata 同理替换 `--source`。`materialize_shadow_from_preview.py` 默认 dry-run，只有显式 `--apply` 才写 shadow Chroma / Neo4j。

### Shadow graph probe

```powershell
$env:NEO4J_PASSWORD="your-password"
python scripts/probe_shadow_graph.py --source all
```

### Status report

```powershell
python scripts/report_source_expansion_status.py
```

输出报告：

```text
evaluation/source_expansion/source_expansion_status_report.json
```

### Default smoke 与完整测试

```powershell
python scripts/smoke_default_source_boundary.py
python -m unittest discover tests
```

## 7. 剩余风险与下一步

当前扩源已经达到课程展示的稳定点：数据量明显增加，strict gates 全过，shadow Chroma/Neo4j 均有可验证结果，默认主源保持不变。

后续可选方向：

- 更多数据批次：继续用 manifest + frontier + raw-only ingest 分批扩展 NASA/ESA，优先保留限域、限速、限量。
- 质量抽样：对新增 narratives 做人工抽样，减少导航文本、新闻页和低价值页面对检索排序的影响。
- Exploratory query 收敛：把已经稳定命中的 exploratory query 提升进 strict gate，失败项继续保留为探索集。
- GUI/Agent 深度接入：让用户在 GUI 中看到更详细的扩源状态表，并在回答中更清楚地区分 default source 与 shadow source。

建议课程提交时停在当前稳定点；如需要展示“还可以继续扩”，用下一批小规模 manifest frontier 作为增量演示即可。
