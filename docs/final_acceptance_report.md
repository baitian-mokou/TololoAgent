# Final Acceptance Report

Generated at: `2026-06-29T10:07:02`

Overall status: `PASS`

## Gate Steps

| command | exit_code | passed | duration_seconds |
| --- | ---: | --- | ---: |
| `python scripts/run_auto_source_router_eval.py` | 0 | true | 0.494 |
| `python -m unittest discover tests` | 0 | true | 14.304 |
| `python scripts/run_single_source_retrieval_eval.py` | 0 | true | 119.415 |
| `python scripts/run_source_expansion_eval.py --source wikidata` | 0 | true | 3.627 |
| `python scripts/run_source_expansion_eval.py --source nasa` | 0 | true | 1.302 |
| `python scripts/collect_eval_failures.py` | 0 | true | 0.269 |
| `python scripts/smoke_default_source_boundary.py` | 0 | true | 33.166 |

## Auto Router

- `router_accuracy = 1`
- `route_pass_count = 12/12`
- `source_trace_missing_count = 0`
- `silent_conflict_count = 0`
- `default_auto_enabled = true`
- `auto_router_gates_passed = true`

## Accuracy

| report | exact_accuracy | pass count | break counts |
| --- | ---: | ---: | --- |
| `single_source_retrieval` | 1 | 28/28 | source_filter=0, metadata=0, inferred=0, explainability=0 |
| `wikidata_source_expansion` | 0.7021 | 33/47 | source_filter=0, metadata=0, inferred=0, explainability=0 |
| `nasa_source_expansion` | 0.9375 | 15/16 | source_filter=0, metadata=0, inferred=0, explainability=0 |

## Final Counters

- `failure_count = 0`
- `source_filter_failure_count = 0`
- `metadata_contract_break_count = 0`
- `inferred_boundary_break_count = 0`
- `query_explainability_degraded_count = 0`

## Default Source State

- `ACTIVE_SOURCE = zh_wikipedia`
- `SOURCE_REGISTRY.zh_wikipedia = active`
- `SOURCE_REGISTRY.wikidata = disabled`
- `SOURCE_REGISTRY.nasa = disabled`
- `SOURCE_REGISTRY.esa = disabled`
- `default_source_smoke_passed = true`

## Key Hygiene

- `settings.json` literal `sk-*` key check: `true`
- `settings.local.json` is not read or printed by this report.
