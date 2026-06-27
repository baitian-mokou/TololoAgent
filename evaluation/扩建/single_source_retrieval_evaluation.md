# Single-Source Retrieval Evaluation

This is the minimal retrieval-quality evaluation layer for the frozen single-source baseline.

It does **not** introduce new sources.
It does **not** change retrieval, graph, embedding, or pipeline core logic.
It only evaluates and guards the current single-source behavior.

## Files

- Query set: `evaluation/single_source_retrieval_queries.json`
- Runner: `scripts/run_single_source_retrieval_eval.py`
- Default JSON report: `evaluation/single_source_retrieval_report.json`
- Frozen failing baseline v1: `evaluation/baselines/single_source_retrieval_eval_baseline_v1.json`
- Frozen passing baseline v2: `evaluation/baselines/single_source_retrieval_eval_passing_baseline_v2.json`

## Default Regression Gate

The runner is now the default regression gate for single-source retrieval.

Required command:

```powershell
python scripts/run_single_source_retrieval_eval.py
```

This command must be run before merge whenever we touch:

- `src/agent/llm_agent.py`
- `src/knowledge_graph/neo4j_loader.py`
- retrieval-related logic

Gate rule:

- non-zero exit code means the change is not mergeable

Optional manual output override:

```powershell
python scripts/run_single_source_retrieval_eval.py --queryset evaluation/single_source_retrieval_queries.json --output evaluation/single_source_retrieval_report.json
```

## Current Coverage

- `ORBITS`
- `PART_OF`
- `LOCATED_IN`
- `HAS_MASS`
- `HAS_RADIUS`
- `HAS_ATMOSPHERE`
- `DISCOVERED_BY`
- `narrative explanation`
- `source isolation`

The runner evaluates:

- graph retrieval via `LLMAgent.search_neo4j_trace(...)`
- embedding retrieval via `LLMAgent.search_chroma(...)`
- fallback retrieval via the existing local fallback paths
- graph / embedding / fallback consistency
- source filter boundary behavior
- query-level exact pass vs top-k hit
- metadata contract completeness
- inferred boundary compliance

## Gold Fields

The gold set includes:

- `expected_path`
- `expected_top_k_hit`
- `allowed_final_sources`
- `normalized_expected_value` for quantity queries
- `expected_page_title`
- `expected_section_any_of`

## Output Shape

Each query result includes at least:

- `query`
- `expected_path`
- `actual_path`
- `expected_result`
- `returned_result`
- `top_k_results`
- `pass`
- `failure_category`
- `source_metadata`

The summary includes at least:

- `total_queries`
- `exact_pass_count`
- `exact_accuracy`
- `top_k_hit_rate`
- `path_selection_correctness`
- `graph_embedding_fallback_inconsistency_count`
- `source_filter_failure_count`
- `metadata_contract_break_count`
- `inferred_boundary_break_count`

The report also includes gate results:

- `exact_accuracy_min`
- `source_filter_failure_max`
- `metadata_contract_break_max`
- `inferred_boundary_break_max`

If any gate fails, the runner writes the JSON report first and then exits non-zero.

## Baselines

Baseline v1:

- `evaluation/baselines/single_source_retrieval_eval_baseline_v1.json`
- frozen failing baseline before path-routing repair v1

Baseline v2:

- `evaluation/baselines/single_source_retrieval_eval_passing_baseline_v2.json`
- frozen passing baseline after path-routing repair v1
- current passing state: `exact_accuracy = 1.0`, `gate exit_code = 0`

## Path-Routing Repair v1 Coverage

This passing baseline reflects only the narrow repair scope below:

- `HAS_ATMOSPHERE`
- `HAS_RADIUS`
- `DISCOVERED_BY`

Boundary kept unchanged:

- no new source
- no benchmark expansion
- no pipeline rewrite
- no GraphRAG
- no multi-source implementation

## Known Issue

Remaining known issue:

- `discover_ceres_graph`

Current state:

- graph top-1 is correct
- fallback top-1 still differs from graph top-1
- this is a real graph/fallback consistency tail issue

Current decision:

- does not block the current gate
- was not part of path-routing repair v1 scope
- if addressed later, it should be handled as a separate `consistency repair` task

## Deferred Direction

After baseline v2 is frozen, the next acceptable step is:

- `source-expansion readiness review`

That review has now passed for NASA shadow mode. The next formal request, if any, is `Wikidata` only; this document still does not authorize implementation.
