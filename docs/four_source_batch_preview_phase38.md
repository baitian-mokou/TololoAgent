# 四源 batch preview 质量报告

本报告复用本地已有 frontier quality preview，不联网、不执行采集、不写正式数据管线。

- phase: `Phase 38`
- active_source: `zh_wikipedia`
- batch_size: `50`
- offline_only: `True`

## Preview 摘要

| source | mode | execution | candidates | accepted | review_needed | exploratory | rejected | action |
|---|---|---|---:|---:|---:|---:|---:|---|
| zh_wikipedia | `active` | `skipped_with_reason` | 0 | 0 | 0 | 0 | 0 | `keep_baseline` |
| nasa | `disabled` | `offline_reused` | 20 | 0 | 20 | 0 | 0 | `raw_shadow_ingest_candidate` |
| esa | `disabled` | `offline_reused` | 17 | 0 | 15 | 2 | 0 | `raw_shadow_ingest_candidate` |
| wikidata | `disabled` | `offline_reused` | 20 | 0 | 20 | 0 | 0 | `needs_manual_review` |

## 可进入下一步的源

- raw shadow candidate: `nasa`, `esa`
- needs manual review: `wikidata`

## 安全边界

- offline-only report reuse; no network call
- no collection execution
- no formal raw/triples/vector/graph writes
- nasa/esa/wikidata remain disabled and shadow-only
- zh_wikipedia remains active baseline
