# Wikidata Live Preview

## Scope

Wikidata live preview is a source-ingestion rehearsal for the disabled `wikidata` namespace. It does not activate Wikidata, does not change `ACTIVE_SOURCE`, and does not participate in default answer fusion.

## CLI

```bash
python scripts/materialize_wikidata_namespace.py --mode dry-run
python scripts/materialize_wikidata_namespace.py --mode live --entity Q111
python scripts/materialize_wikidata_namespace.py --mode live --entity 火星
```

Default mode remains `offline`. `dry-run` and `live` write preview reports only and do not write official triples, Chroma, or Neo4j data.

## Public Source

- API: `https://www.wikidata.org/w/api.php`
- Entity page pattern: `https://www.wikidata.org/wiki/{qid}`
- License hint: `CC0-1.0`

## Relation Mapping

- `P397` -> `ORBITS`
- `P2067` -> `HAS_MASS`
- `P2120` -> `HAS_RADIUS`
- `P523` -> `HAS_ATMOSPHERE`
- `P61` -> `DISCOVERED_BY`
- `P276` -> `LOCATED_IN`
- `P361` -> `PART_OF`

## Provenance Fields

Candidate facts preserve:

- `source_record_id`
- `source_url`
- `source_license`
- `license_hint`
- `fetched_at`
- `raw_value`
- `normalized_value`
- `unit`
- `confidence`

## Output

- `evaluation/source_expansion/wikidata/wikidata_live_preview_report.json`

If live fetch fails, the report records the failure and falls back to offline fixture parsing. This fallback is intentional and must not fail acceptance gates.
