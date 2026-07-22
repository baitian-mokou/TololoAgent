# NASA shadow review-only query bypass

Phase 51 adds an explicit review-only code entry point near the query layer. It is not wired into the default GUI, LLMAgent, Chroma, or Neo4j path.

- ready: `True`
- blocked_reason: ``
- mapping_count: `10`
- review_only_required: `True`
- review_only: `True`
- active_source: `zh_wikipedia`
- default_query_path_changed: `False`
- gui_default_behavior_changed: `False`
- formal_default_triples_write: `False`
- chroma_write: `False`
- neo4j_write: `False`
- data_write: `False`

## Review Payload Preview

| case | query | results | top source URL |
| --- | --- | ---: | --- |
| `subject_apophis` | `Apophis asteroid` | 8 | `https://science.nasa.gov/solar-system/asteroids/apophis/` |
| `subject_bennu` | `Bennu asteroid` | 8 | `https://science.nasa.gov/solar-system/asteroids/101955-bennu/` |
| `subject_psyche_url` | `Asteroid Psyche URL` | 8 | `https://science.nasa.gov/solar-system/asteroids/16-psyche/` |
| `subject_didymos` | `Didymos Dimorphos asteroid` | 8 | `https://science.nasa.gov/solar-system/asteroids/didymos/` |
| `subject_swift_tuttle` | `109P Swift-Tuttle comet` | 8 | `https://science.nasa.gov/solar-system/comets/109p-swift-tuttle/` |
| `topic_asteroid` | `asteroid topic` | 8 | `https://nssdc.gsfc.nasa.gov/planetary/planets/asteroidpage.html` |
| `topic_comet` | `comet topic` | 8 | `https://science.nasa.gov/solar-system/comets/103p-hartley-hartley-2/` |
| `relation_source_url` | `SOURCE_URL NASA` | 8 | `https://nssdc.gsfc.nasa.gov/planetary/planets/asteroidpage.html` |
| `relation_has_topic` | `HAS_TOPIC asteroid` | 8 | `https://nssdc.gsfc.nasa.gov/planetary/planets/asteroidpage.html` |
| `planetary_defense_url` | `Planetary Defense NASA` | 8 | `https://science.nasa.gov/planetary-defense/` |
