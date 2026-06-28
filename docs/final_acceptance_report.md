# Final Acceptance Report

Generated at: `2026-06-28T10:47:46`

Overall status: `PASS`

## Gate Steps

| command | exit_code | passed | duration_seconds |
| --- | ---: | --- | ---: |
| `python -m unittest discover tests` | 0 | true | 10.307 |
| `python scripts/run_single_source_retrieval_eval.py` | 0 | true | 81.027 |
| `python scripts/run_source_expansion_eval.py --source wikidata` | 0 | true | 1.609 |
| `python scripts/run_source_expansion_eval.py --source nasa` | 0 | true | 0.739 |
| `python scripts/collect_eval_failures.py` | 0 | true | 0.064 |
| `python scripts/smoke_default_source_boundary.py` | 0 | true | 27.393 |

## Accuracy

| report | exact_accuracy | pass count | break counts |
| --- | ---: | ---: | --- |
| `single_source_retrieval` | 1 | 31/31 | source_filter=0, metadata=0, inferred=0, explainability=0 |
| `wikidata_source_expansion` | 1 | 24/24 | source_filter=0, metadata=0, inferred=0, explainability=0 |
| `nasa_source_expansion` | 1 | 22/22 | source_filter=0, metadata=0, inferred=0, explainability=0 |

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
