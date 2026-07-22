# Sandbox Candidate Review

未注册 Manifest 2.0 候选源的离线预审汇总；不联网，不写正式 raw/triples/Chroma/Neo4j。

| source_id | mode | candidates | accepted | review | exploratory | rejected | skipped | recommendation |
|---|---|---:|---:|---:|---:|---:|---:|---|
| academic_example | academic | 1 | 0 | 1 | 0 | 0 | 0 | manual_sample_first |
| generic_unknown_example | generic_unknown | 1 | 0 | 0 | 1 | 0 | 0 | manual_sample_first |
| official_science_example | official_science | 1 | 0 | 1 | 0 | 0 | 0 | manual_sample_first |
| publisher_example | publisher | 1 | 0 | 1 | 0 | 0 | 0 | manual_sample_first |

## Recommendation Rules

- `needs_manifest_fix`: 候选为空或 rejected 较多，先修 manifest / include-exclude。
- `manual_sample_first`: 候选相关但证据不足，先人工抽样。
- `ready_for_small_batch`: 有 accepted 且无硬风险，可进入小批量 trial。
- `source_specific_gate`: 机器数据 / entity data 走专用 gate，不套普通网页规则。
