# NASA Live Preview

## Scope

NASA live preview is a fact-source rehearsal for the disabled `nasa` namespace. It is not an active source, not GraphRAG, and not default multi-source fusion.

## CLI

```bash
python scripts/materialize_nasa_namespace.py --mode dry-run
python scripts/materialize_nasa_namespace.py --mode live --entity 火星
```

Default mode remains `offline`. `dry-run` and `live` write preview reports only and do not write official triples, Chroma, or Neo4j data.

## Public Source

The preview prefers public static NASA fact material and does not require an API key.

- Mars fact sheet candidate: `https://nssdc.gsfc.nasa.gov/planetary/factsheet/marsfact.html`
- License hint: `Public domain / NASA content usage guidelines`

## Candidate Relations

- `HAS_MASS`
- `HAS_RADIUS`
- `HAS_ATMOSPHERE`

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

- `evaluation/source_expansion/nasa/nasa_live_preview_report.json`

If live fetch fails, the report records the failure and falls back to offline raw JSON parsing. This fallback is intentional and must not fail acceptance gates.
