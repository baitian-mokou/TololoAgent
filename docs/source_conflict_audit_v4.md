# Source Conflict Audit v4

This v4 audit creates evidence packets and candidate quality patches only. It does not mutate formal triples, Chroma, Neo4j, GUI behavior, or default answers.

## Summary

- `metadata_incomplete_count`: 0
- `evidence_packet_count`: 7
- `quality_patch_candidate_count`: 7
- `requires_human_approval_count`: 7

## Evidence Packets

- `天王星` / `HAS_MASS`: `true_value_conflict`; no_action_manual_review; confidence `0.6`
- `天王星` / `HAS_RADIUS`: `measurement_kind_mismatch`; add_measurement_kind; confidence `0.78`
- `木卫二` / `HAS_MASS`: `true_value_conflict`; no_action_manual_review; confidence `0.6`
- `木卫四` / `HAS_MASS`: `true_value_conflict`; no_action_manual_review; confidence `0.6`
- `火卫一` / `HAS_MASS`: `source_granularity_mismatch`; no_action_manual_review; confidence `0.76`
- `火卫一` / `HAS_RADIUS`: `true_value_conflict`; no_action_manual_review; confidence `0.6`
- `金星` / `HAS_RADIUS`: `true_value_conflict`; no_action_manual_review; confidence `0.6`

## Candidate Patches

- `source_conflict_v4_001` `no_action_manual_review` -> `zh_wikipedia`; approval required `True`
- `source_conflict_v4_002` `add_measurement_kind` -> `zh_wikipedia`; approval required `True`
- `source_conflict_v4_003` `no_action_manual_review` -> `zh_wikipedia`; approval required `True`
- `source_conflict_v4_004` `no_action_manual_review` -> `zh_wikipedia`; approval required `True`
- `source_conflict_v4_005` `no_action_manual_review` -> `zh_wikipedia`; approval required `True`
- `source_conflict_v4_006` `no_action_manual_review` -> `zh_wikipedia`; approval required `True`
- `source_conflict_v4_007` `no_action_manual_review` -> `zh_wikipedia`; approval required `True`

## Boundary

- Candidate patches are not applied.
- `ACTIVE_SOURCE` remains `zh_wikipedia`.
