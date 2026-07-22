# raw-only shadow ingest 小批次试跑

本报告只覆盖 `nasa` / `esa`，不处理 `zh_wikipedia` 或 `wikidata`。

- phase: `Phase 39`
- active_source: `zh_wikipedia`
- dry_run: `False`

| source | status | before raw | after raw | new | duplicate/existing | failed | network |
|---|---|---:|---:|---:|---:|---:|---|
| nasa | `completed_with_failures` | 95 | 95 | 0 | 19 | 1 | `True` |
| esa | `completed_with_failures` | 168 | 168 | 0 | 18 | 2 | `True` |

## 安全边界

- nasa/esa only
- raw JSON only
- no downstream materialization
- ACTIVE_SOURCE remains zh_wikipedia
