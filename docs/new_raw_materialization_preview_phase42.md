# 新增 raw materialization preview

本报告只读取 Phase 41 新增 raw，做质量抽样与内存估算，不写 triples/narratives/Chroma/Neo4j。

- phase: `Phase 42`
- active_source: `zh_wikipedia`
- new raw: `23`
- readable: `23`
- duplicate groups: `0`
- preview triples: `6`
- preview narratives: `87`
- recommended next action: `manual_review_before_materialization`

| source | new raw | readable | triage | preview triples | preview narratives | next action |
|---|---:|---:|---|---:|---:|---|
| nasa | 20 | 20 | `{'accepted': 20}` | 0 | 80 | `ready_for_limited_shadow_triples_trial` |
| esa | 3 | 3 | `{'exploratory': 2, 'rejected': 1}` | 6 | 7 | `manual_review_before_materialization` |

## Sample Items

- `nasa` `accepted` triples=0 narratives=4 Asteroid Facts
- `nasa` `accepted` triples=0 narratives=4 Asteroids: Exploration - NASA Science
- `nasa` `accepted` triples=0 narratives=4 Asteroid 2024 YR4
- `nasa` `accepted` triples=0 narratives=4 Apophis - NASA Science
- `nasa` `accepted` triples=0 narratives=4 Asteroid Psyche
- `nasa` `accepted` triples=0 narratives=4 Bennu - NASA Science
- `nasa` `accepted` triples=0 narratives=4 Dinkinesh - NASA Science
- `nasa` `accepted` triples=0 narratives=4 Asteroid Donaldjohanson
- `nasa` `accepted` triples=0 narratives=4 Didymos & Dimorphos - NASA Science
- `nasa` `accepted` triples=0 narratives=4 4 Vesta - NASA Science
- `nasa` `accepted` triples=0 narratives=4 433 Eros - NASA Science
- `nasa` `accepted` triples=0 narratives=4 243 Ida - NASA Science
- `nasa` `accepted` triples=0 narratives=4 25143 Itokawa - NASA Science
- `nasa` `accepted` triples=0 narratives=4 Planetary Defense at NASA - NASA Science Facebook logo Instagram logo Linkedin logo
- `nasa` `accepted` triples=0 narratives=4 NASA Space Science Data Coordinated Archive Status - NASA
- `nasa` `accepted` triples=0 narratives=4 Comet Facts
- `nasa` `accepted` triples=0 narratives=4 Comet 3I/ATLAS - NASA Science
- `nasa` `accepted` triples=0 narratives=4 Comet 103P/Hartley (Hartley 2) - NASA Science
- `nasa` `accepted` triples=0 narratives=4 109P/Swift-Tuttle - NASA Science
- `nasa` `accepted` triples=0 narratives=4 19P/Borrelly - NASA Science
- `esa` `rejected` triples=2 narratives=0 https://scifleet.esa.int/model/juice/
- `esa` `exploratory` triples=2 narratives=4 10 years since Rosetta
- `esa` `exploratory` triples=2 narratives=3 Rosetta – ESA's comet chaser – Follow ESA's mission to Comet 67P/Churyumov-Gerasimenko

## Safety

- network: `False`
- triples_write: `False`
- narratives_write: `False`
- chroma_write: `False`
- neo4j_write: `False`
- active_source_unchanged: `True`
