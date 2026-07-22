# Formal source production gate

This gate promotes shadow-source evidence into a formal production-review standard.
It is review-only: a passing result means NASA, ESA, and Wikidata shadow artifacts may be submitted for human review, not that production write or cutover is authorized.

## Required gate

Run:

```bash
python scripts/run_production_source_gate.py
```

The gate must pass with `decision = review_ready_not_authorized`.

## Evidence requirements

- `ACTIVE_SOURCE` remains `zh_wikipedia`, and `zh_wikipedia` remains the only active source.
- `nasa`, `esa`, and `wikidata` remain `disabled` shadow sources in `SOURCE_REGISTRY`.
- Each source has a passing shadow readiness report.
- Each source has a review-only CLI report with satisfied oracle mappings.
- Data quality thresholds pass with no readiness issues, no blocked reason, and no duplicate/noise exception.
- Output paths are limited to `data/triples_shadow/<source>`.
- Formal source writes, default `data/triples` writes, Chroma writes, and Neo4j writes remain unauthorized unless a separate explicit approval exists.

## Prohibited before approval

- Do not change `ACTIVE_SOURCE`.
- Do not enable NASA, ESA, or Wikidata in `SOURCE_REGISTRY`.
- Do not write default `data/triples`, Chroma, or Neo4j.
- Do not call `clear_source_ingestion_outputs`.
- Do not treat a passing shadow/readiness/review CLI gate as production cutover approval.

## Rollback and review blockers

Block review or roll back the production-gate proposal if any source is enabled early, a readiness or review-only CLI report fails, output escapes its shadow path, duplicate/noise controls report issues, or production write authorization is missing/ambiguous.

