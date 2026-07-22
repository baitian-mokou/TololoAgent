# NASA shadow JSON-only retrieval eval

Phase 48 evaluates the local `data/triples_shadow/nasa` JSON artifact with deterministic stdlib matching.
It does not query Chroma or Neo4j, and it does not change the default source.

- ready: `True`
- blocked_reason: ``
- pass_rate: `1.0`
- passed_cases: `10/10`
- active_source: `zh_wikipedia`
- formal_default_triples_write: `False`
- chroma_write: `False`
- neo4j_write: `False`

## Cases

| case | query | passed | hits | failure |
| --- | --- | --- | ---: | --- |
| `subject_apophis` | `Apophis asteroid` | `True` | 8 | `` |
| `subject_bennu` | `Bennu asteroid` | `True` | 8 | `` |
| `subject_psyche_url` | `Asteroid Psyche URL` | `True` | 8 | `` |
| `subject_didymos` | `Didymos Dimorphos asteroid` | `True` | 8 | `` |
| `subject_swift_tuttle` | `109P Swift-Tuttle comet` | `True` | 8 | `` |
| `topic_asteroid` | `asteroid topic` | `True` | 8 | `` |
| `topic_comet` | `comet topic` | `True` | 8 | `` |
| `relation_source_url` | `SOURCE_URL NASA` | `True` | 8 | `` |
| `relation_has_topic` | `HAS_TOPIC asteroid` | `True` | 8 | `` |
| `planetary_defense_url` | `Planetary Defense NASA` | `True` | 8 | `` |
