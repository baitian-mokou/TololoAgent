# NASA shadow query-chain adapter dry-run

Phase 49 maps NASA shadow JSON eval cases into the payload shape a future retrieval or GUI path could consume.
This is a dry-run report only: no source switch, no database calls, and no data writes.

- ready: `True`
- blocked_reason: ``
- mapping_count: `10`
- active_source: `zh_wikipedia`
- formal_default_triples_write: `False`
- chroma_write: `False`
- neo4j_write: `False`
- data_write: `False`

## Minimal Future Adapter Point

- Add an explicit NASA shadow dry-run branch near LLMAgent._search_single_source_bundle or behind a separate review-only command path.

## Mapping Preview

| case | query | results | source_url |
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
