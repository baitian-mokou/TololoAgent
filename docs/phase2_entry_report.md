# Phase 2 Entry Report

## Current Gate Status

- `python scripts/run_all_gates.py` passed before phase 2 work began.
- `single_source_retrieval` exact accuracy remains `1.0`.
- `wikidata` source expansion exact accuracy remains `1.0`.
- `nasa` source expansion exact accuracy remains `1.0`.
- `failure_count = 0`.
- `source_filter_failure_count = 0`.
- `metadata_contract_break_count = 0`.
- `inferred_boundary_break_count = 0`.
- `query_explainability_degraded_count = 0`.

## Source State

- `ACTIVE_SOURCE = zh_wikipedia`.
- `SOURCE_REGISTRY.zh_wikipedia = active`.
- `SOURCE_REGISTRY.wikidata = disabled`.
- `SOURCE_REGISTRY.nasa = disabled`.
- `SOURCE_REGISTRY.esa = disabled`.

## Not Allowed In This Phase

- Do not modify `ACTIVE_SOURCE`.
- Do not switch `wikidata`, `nasa`, or `esa` to active.
- Do not lower gate thresholds.
- Do not delete existing fixtures, query sets, or final acceptance reports.
- Do not break `python scripts/run_all_gates.py`.
- Do not enable `SourceRouter` by default.
- Do not make GUI default behavior multi-source.
- Do not write real API keys.
- Do not read or print secrets from `settings.local.json`.
- If a live fetch fails, fall back to offline/dry-run reporting without breaking acceptance.

## Phase Goal

This phase prepares real source ingestion and audits cross-source disagreement through preview-only paths:

- live fetch preview
- provenance hardening
- source conflict audit

This phase is not a cutover, not GraphRAG, and not default multi-source fusion. Default question answering remains single-source `zh_wikipedia`.
