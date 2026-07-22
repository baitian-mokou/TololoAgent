# NASA shadow review-only query bypass

Phase 51 adds an explicit review-only code entry point near the query layer. It is not wired into the default GUI, LLMAgent, Chroma, or Neo4j path.

- ready: `True`
- blocked_reason: ``
- mapping_count: `1`
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
| `apophis` | `Apophis` | 2 | `https://science.nasa.gov/apophis/` |
