# Final Acceptance Report

Generated at: `2026-06-28T15:50:04`

Overall status: `PASS`

## Gate Steps

| command | exit_code | passed | duration_seconds |
| --- | ---: | --- | ---: |
| `python scripts/run_auto_source_router_eval.py` | 0 | true | 0.351 |
| `python -m unittest discover tests` | 0 | true | 12.428 |
| `python scripts/run_single_source_retrieval_eval.py` | 0 | true | 98.331 |
| `python scripts/run_source_expansion_eval.py --source wikidata` | 0 | true | 3.792 |
| `python scripts/run_source_expansion_eval.py --source nasa` | 0 | true | 2.49 |
| `python scripts/collect_eval_failures.py` | 0 | true | 0.187 |
| `python scripts/smoke_default_source_boundary.py` | 0 | true | 25.115 |

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
| `single_source_retrieval` | 1 | 31/31 | source_filter=0, metadata=0, inferred=0, explainability=0 |
| `wikidata_source_expansion` | 1 | 47/47 | source_filter=0, metadata=0, inferred=0, explainability=0 |
| `nasa_source_expansion` | 1 | 42/42 | source_filter=0, metadata=0, inferred=0, explainability=0 |

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
