# 四源扩批计划

本报告只做 dry-run / preview 计划，不联网、不执行采集、不写正式数据管线。

- phase: `Phase 37`
- active_source: `zh_wikipedia`
- batch_size: `50`
- status_report: `evaluation/source_expansion/source_expansion_status_report.json` (present)

## 当前规模与下一批计划

| source | mode | raw | triples | narratives | next target | scope | action |
|---|---|---:|---:|---:|---:|---|---|
| zh_wikipedia | `active` | 69 | 41 | 69 | 119 | `formal_candidate` | `keep_active_baseline` |
| nasa | `disabled` | 79 | 34 | 323 | 129 | `shadow_only` | `ready_for_batch_preview` |
| esa | `disabled` | 73 | 191 | 455 | 123 | `shadow_only` | `ready_for_batch_preview` |
| wikidata | `disabled` | 47 | 228 | 161 | 97 | `shadow_only` | `ready_for_batch_preview` |

## 安全边界

- This is a dry-run planning report only.
- No network probe, no preview run, no data pipeline write.
- nasa/esa/wikidata remain disabled and shadow-only.
- ACTIVE_SOURCE remains zh_wikipedia.
- Each proposed batch must pass quality review before any later materialization.

## 分源提示

- `zh_wikipedia`: safeguards=dry_run_plan_only, quality_gate_before_materialization, no_default_source_cutover, keep_active_baseline; warnings=zh_wikipedia counts are directory-based baseline estimates; no source expansion status item
- `nasa`: safeguards=dry_run_plan_only, quality_gate_before_materialization, no_default_source_cutover, shadow_namespace_only; warnings=none
- `esa`: safeguards=dry_run_plan_only, quality_gate_before_materialization, no_default_source_cutover, shadow_namespace_only; warnings=none
- `wikidata`: safeguards=dry_run_plan_only, quality_gate_before_materialization, no_default_source_cutover, shadow_namespace_only; warnings=none

## 下一步

- Run per-source frontier preview with explicit limits if a batch is approved.
- Review quality triage and rejected samples before any raw materialization.
- Keep nasa/esa/wikidata in shadow reports until cutover is separately approved.
