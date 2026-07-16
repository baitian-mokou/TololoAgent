# Single-Source Passing Baseline v2

This file freezes the first passing retrieval evaluation state after path-routing repair v1.

Status:

- baseline type: `single-source passing baseline v2`
- system state: `single-source frozen baseline`
- active source: `zh_wikipedia`
- source schema version: `zh_wikipedia_single_source_v1`
- review state: `NASA shadow audit passed; next candidate is Wikidata only`

Evaluation status:

- command: `python scripts/run_single_source_retrieval_eval.py`
- expected gate result: `exit_code = 0`
- expected accuracy state: `exact_accuracy = 1.0`

Scope covered by the repair that produced this baseline:

- `HAS_ATMOSPHERE`
- `HAS_RADIUS`
- `DISCOVERED_BY`

Boundary preserved:

- no new source
- no benchmark expansion
- no pipeline rewrite
- no GraphRAG
- no multi-source implementation

Frozen JSON artifact:

- `evaluation/baselines/single_source_retrieval_eval_passing_baseline_v2.json`

Known non-blocking issue:

- `discover_ceres_graph`
- graph/fallback top-1 inconsistency remains
- current gate does not fail on this
- future handling should be a separate consistency repair task
