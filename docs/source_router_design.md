# SourceRouter / SourcePolicy Design

Status: design only. Do not enable by default.

## Non-goals

- Do not change `ACTIVE_SOURCE`.
- Do not enable GraphRAG, SAG, or free cross-source fusion.
- Do not change `AgentTab` default behavior.
- Do not answer from multiple sources unless an explicit experimental source filter or future owner-approved switch is present.

## Proposed Policy

`SourcePolicy` should resolve a request into one of these modes:

- `single_active`: default, equivalent to `source_filter=["zh_wikipedia"]`.
- `single_shadow_probe`: explicit probe of one disabled source namespace, for evaluation and audit only.
- `explicit_experimental_priority`: future owner-approved mode; disabled until a dedicated gate exists.

Candidate priority, if the future experimental mode is ever approved:

- NASA: numeric authoritative fact checks, such as Planetary Fact Sheet values.
- Wikidata: structured identifiers and auditable graph facts.
- zh_wikipedia: narrative explanation and current default user-facing source.

## Required Guards

- Every result must carry `source`, `source_name`, `source_role`, `origin`, `schema_version`, and `source_title`.
- `source_filter_failure`, `metadata_contract_break`, `inferred_boundary_break`, and `query_explainability_degraded` must remain zero in source expansion gates.
- Shadow source success must not imply active-source cutover.
- Conflict cases must report source-local evidence; they must not synthesize a merged answer by default.
