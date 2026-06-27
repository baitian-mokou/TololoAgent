# Source Expansion Status

This document records the final offline fixture-based acceptance state for the current source expansion milestone.

## Current State

- `ACTIVE_SOURCE = zh_wikipedia`.
- `zh_wikipedia` is the only active source.
- `wikidata`, `nasa`, and `esa` remain `disabled` in `SOURCE_REGISTRY`.
- There is no default cross-source fusion.
- `SourceRouter` is design-only and not enabled.
- Default `LLMAgent()` behavior remains the `zh_wikipedia` single-source path unless an explicit experimental `source_filter` is passed.
- Live fetch is not implemented in this pass; this round uses offline fixtures and data-contract materialization only.

## Data Scale

| source | raw files | triple files | narrative files | state |
| --- | ---: | ---: | ---: | --- |
| `zh_wikipedia` | 469 | 63 | 416 | active baseline |
| `wikidata` | 1 | 18 | 18 | disabled formal shadow candidate |
| `nasa` | 2 | 1 | 1 | disabled shadow fact supplement |
| `esa` | 1 | 1 | 1 | disabled smoke-only source |

Counts are file counts under the source-aware `data/raw_json` and `data/triples` namespaces.

## Final Evaluation Results

| report | pass count | exact_accuracy | source_filter_failure_count | metadata_contract_break_count | inferred_boundary_break_count | query_explainability_degraded_count |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `single_source_retrieval` | 31/31 | 1.0 | 0 | 0 | 0 | 0 |
| `wikidata source expansion` | 24/24 | 1.0 | 0 | 0 | 0 | 0 |
| `nasa source expansion` | 22/22 | 1.0 | 0 | 0 | 0 | 0 |

Final triage:

- `failure_count = 0`
- `source_filter_failure_count = 0`
- `metadata_contract_break_count = 0`
- `inferred_boundary_break_count = 0`
- `query_explainability_degraded_count = 0`

## Source Conclusions

- Wikidata shadow source: `24/24` pass, `cutover_ready=false`. It is a formal second-source shadow candidate, not an active source.
- NASA shadow source: `22/22` pass, shadow-only. It remains positioned as an auditable fact supplement, not the next active source.
- ESA: smoke-only and disabled. It validates the source namespace/adapter path and does not enter the default retrieval path.

## Acceptance Command

Run the full gate package with:

```bash
python scripts/run_all_gates.py
```

The command writes:

- `evaluation/final_acceptance_report.json`
- `docs/final_acceptance_report.md`

## Remaining Risks

- Live fetch is still a future enhancement.
- Multi-source fusion is not enabled.
- `SourceRouter` remains design-only and default-off.
- Future cutover work must keep the shadow namespace, source filter, schema version, metadata contract, and readiness gate intact.
