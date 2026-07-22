# NASA limited shadow materialization package

本包合并 Phase 43 narratives 与 Phase 44 accepted triples，仅用于人工审阅和下一步审批；当前不写正式 shadow 目录。

- source: `nasa`
- items: `20`
- triples: `80`
- narratives: `80`
- approval_status: `pending`
- quality_flags: `0`
- next_action: `ready_for_manual_approval_to_write_formal_shadow_directory`

## Relation Counts

- `HAS_TOPIC`: 20
- `INSTANCE_OF`: 40
- `SOURCE_URL`: 20

## Type Distribution

- `asteroid`: 30
- `comet`: 10
- `small body`: 20

## Approval Template

- `evaluation\four_source_expansion\nasa_limited_shadow_package_approval_phase45.json`

## Formal Shadow Write Plan

- execution_status: `not_run`
- requires_manual_approval: `True`
- allowed_scope: `shadow materialization path only`
- planned_triples: `80`
- planned_narratives: `80`

Safety guards:
- ACTIVE_SOURCE remains zh_wikipedia
- nasa remains disabled/shadow
- no Chroma write
- no Neo4j write
- manual approval file required before any formal shadow write

## Review Samples

- NASA Space Science Data Coordinated Archive Status - `https://nssdc.gsfc.nasa.gov/planetary/planets/asteroidpage.html` triples=4 narratives=1
- Planetary Defense at NASA - `https://science.nasa.gov/planetary-defense/` triples=4 narratives=1
- Bennu - `https://science.nasa.gov/solar-system/asteroids/101955-bennu/` triples=4 narratives=1
- Asteroid Psyche - `https://science.nasa.gov/solar-system/asteroids/16-psyche/` triples=4 narratives=1
- Asteroid 2024 YR4 - `https://science.nasa.gov/solar-system/asteroids/2024-yr4/` triples=4 narratives=1

## Safety

- formal_triples_write: `False`
- formal_narratives_write: `False`
- chroma_write: `False`
- neo4j_write: `False`
- network: `False`
- active_source_unchanged: `True`
