# Single-Source Baseline Freeze Report

Date: 2026-06-24

## Freeze Decision

Baseline Frozen: YES

This repository remains a frozen single-source baseline for the active runtime.
The only allowed active source remains `zh_wikipedia`.
No new source was introduced into the active path, and no retrieval, graph, embedding, or pipeline logic was changed.

## Baseline Statistics

- `active_source`: `zh_wikipedia`
- `source_schema_version`: `zh_wikipedia_single_source_v1`
- `raw_json count`: `458`
- `triples file count`: `63`
- `triples record count`: `154`
- `narratives file count`: `416`
- `narratives record count`: `3193`
- `Neo4j relationship count`: `161`
- `Chroma total count`: `3193`
- `source isolation validation status`: `PASS`
- `graph bad relation types count`: `0`
- `graph bad metadata count`: `0`

## Validation Closure

- `data/triples/summary.json` is present and aligned with the current pipeline output:
  - `total_triples = 154`
  - `total_narratives = 3193`
  - `pipeline = preprocess_v2`
  - `active_source = zh_wikipedia`
  - `source_schema_version = zh_wikipedia_single_source_v1`
- Local source metadata audit passed:
  - raw JSON source drift: `0`
  - raw JSON missing `source_role`: `0`
  - raw JSON missing `origin`: `0`
  - triple bad metadata: `0`
  - narrative bad metadata: `0`
- Graph/source filter probes passed:
  - `火卫一绕谁公转` with `source_filter=['zh_wikipedia']`: graph returns `1`
  - `火卫一绕谁公转` with `source_filter=['nasa']`: returns `0`
- Chroma/source filter probes passed:
  - `火星大气成分` with `source_filter=['zh_wikipedia']`: returns results
  - `火星大气成分` with `source_filter=['nasa']`: returns `0`
- `scripts/verify_active_path.py` latest run:
  - direct graph path active for `海王星在哪里` / `火卫一绕谁公转` / `木卫一属于什么系统`
  - `dirty_terms` counts are all `0`
  - crawler network branch is blocked by the current sandbox, which does not indicate source isolation drift

## Preserved Regression Entrypoints

- Baseline audit:
  - `python scripts/audit_single_source_baseline.py`
- Active path validation:
  - `python scripts/verify_active_path.py`
- Pipeline rebuild from current raw JSON:
  - `python -c "from src.nlp.nlp_pipeline import NlpPipeline; print(NlpPipeline().process_all())"`
- Single-source convergence entry:
  - `python scripts/p5_converge_single_source.py`
  - use only when regeneration is explicitly intended; prefer the audit script for freeze checks

## Regression Scope Mapping

- `graph`:
  - `python scripts/audit_single_source_baseline.py`
  - `python scripts/verify_active_path.py`
- `embedding`:
  - `python scripts/audit_single_source_baseline.py`
  - `python scripts/verify_active_path.py`
- `fallback`:
  - `python scripts/verify_active_path.py`
- `source_filter`:
  - `python scripts/audit_single_source_baseline.py`
- `Neo4j`:
  - `python scripts/audit_single_source_baseline.py`
- `Chroma`:
  - `python scripts/audit_single_source_baseline.py`
  - `python scripts/verify_active_path.py`

## Stage Status

- `P5`: `COMPLETE`
- `Step 2`: `COMPLETE`
- Current system state: `single-source frozen baseline`
- Current review state: `NASA shadow audit passed; next-phase request may be prepared`

## Still Forbidden

- Do not introduce `NASA`, `Wikidata`, `ESA`, or any new active source into the frozen baseline.
- Do not implement a multi-source crawler.
- Do not enter GraphRAG, SAG, or cross-source fusion.
- Do not modify retrieval, graph, embedding, or pipeline core logic.
- Do not reopen work outside the single-source freeze scope.

## Next Approval Boundary

Allowed next step:

- formal next-phase request review for `Wikidata` only

Not allowed:

- multi-source implementation
- GraphRAG implementation
- SAG implementation
- source expansion rollout
