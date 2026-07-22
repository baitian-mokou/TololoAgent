# Four-source crawler scope expansion preview

- dry_run_preview_default: `True`
- live_fetch_attempted: `False`
- active_source: `zh_wikipedia`

| source | limit | selected | accepted_for_raw_preview | review_needed | rejected | duplicates | recommended_next_batch |
|---|---:|---:|---:|---:|---:|---:|---:|
| zh_wikipedia | 80 | 3 | 3 | 0 | 0 | 0 | 3 |
| nasa | 100 | 92 | 0 | 92 | 0 | 0 | 30 |
| esa | 80 | 30 | 9 | 16 | 5 | 16 | 16 |
| wikidata | 100 | 47 | 25 | 22 | 0 | 0 | 22 |

Boundaries: no data/raw_json, data/triples, Chroma, or Neo4j writes; NASA/ESA/Wikidata remain disabled.
Next: review this scope, then choose bounded raw preview batches per source.
