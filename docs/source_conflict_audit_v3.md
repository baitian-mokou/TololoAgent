# Source Conflict Audit v3

This v3 audit is read-only. It adds Wikidata unit-QID normalization, entity alias/QID normalization, and measurement-kind explanations for audit reporting only.

## V1/V2/V3 Comparison

| Metric | V1 | V2 | V3 |
| --- | ---: | ---: | ---: |
| `value_conflict` | 18 | 8 | 7 |
| `unit_equivalent` | 15 | 16 | 16 |
| `synonym_equivalent` | 0 | 2 | 2 |
| `entity_alias_equivalent` | 0 | 0 | 0 |
| `same_quantity_different_measurement_kind` | 0 | 0 | 1 |
| `likely_zhwiki_extraction_error` | 0 | 7 | 7 |

## Entity Alias Equivalent


## Same Quantity Different Measurement Kind

- `谷神星` / `HAS_RADIUS`: {"zh_wikipedia": ["mean_radius"], "wikidata": ["unspecified"]}

## Remaining True Conflicts

- `天王星` / `HAS_MASS`: Missing sources: nasa. Values parse successfully but normalized values differ for HAS_MASS. Values parse successfully but normalized values differ for HAS_MASS. {"zh_wikipedia": ["0.0013 × 10 25 kg"], "wikidata": ["8.6810e25 kg"]}
- `天王星` / `HAS_RADIUS`: Missing sources: nasa. Values remain different after normalization; at least one source could not be fully parsed for HAS_RADIUS. Values remain different after normalization; at least one source could not be fully parsed for HAS_RADIUS. {"zh_wikipedia": ["4km", "20km"], "wikidata": ["25362 km"]}
- `木卫二` / `HAS_MASS`: Missing sources: nasa. Values parse successfully but normalized values differ for HAS_MASS. Values parse successfully but normalized values differ for HAS_MASS. {"zh_wikipedia": ["0.000 013 × 10 22 kg"], "wikidata": ["4.7998e22 kg"]}
- `木卫四` / `HAS_MASS`: Missing sources: nasa. Values parse successfully but normalized values differ for HAS_MASS. Values parse successfully but normalized values differ for HAS_MASS. {"zh_wikipedia": ["0.000 137 × 10 23 kg"], "wikidata": ["1.0759e23 kg"]}
- `火卫一` / `HAS_MASS`: Missing sources: nasa. Values parse successfully but normalized values differ for HAS_MASS. Values parse successfully but normalized values differ for HAS_MASS. {"zh_wikipedia": ["1.072 × 10 16 kg"], "wikidata": ["1.0659e16 kg"]}
- `火卫一` / `HAS_RADIUS`: Missing sources: nasa. Values remain different after normalization; at least one source could not be fully parsed for HAS_RADIUS. Values remain different after normalization; at least one source could not be fully parsed for HAS_RADIUS. {"zh_wikipedia": ["11.1km"], "wikidata": ["11.2667 km"]}
- `金星` / `HAS_RADIUS`: Missing sources: nasa. Values remain different after normalization; at least one source could not be fully parsed for HAS_RADIUS. Values remain different after normalization; at least one source could not be fully parsed for HAS_RADIUS. {"zh_wikipedia": ["1.0km"], "wikidata": ["6051.8 km"]}

## zh_wikipedia Extraction Errors

- `冥王星` / `HAS_RADIUS`: {"zh_wikipedia": ["0.8 km"], "wikidata": ["1188.3 km"]}
- `土星` / `HAS_RADIUS`: {"zh_wikipedia": ["232 km", "268 km", "10 km"], "wikidata": ["58232 km"]}
- `木卫二` / `HAS_RADIUS`: {"zh_wikipedia": ["0.5 km"], "wikidata": ["1560.8 km"]}
- `木卫四` / `HAS_RADIUS`: {"zh_wikipedia": ["1.5 km"], "wikidata": ["2410.3 km"]}
- `木星` / `HAS_RADIUS`: {"zh_wikipedia": ["0.4 km"], "wikidata": ["69911 km"]}
- `水星` / `HAS_RADIUS`: {"zh_wikipedia": ["1.0 km"], "wikidata": ["2439.7 km"]}
- `海王星` / `HAS_RADIUS`: {"zh_wikipedia": ["15 km", "30 km"], "wikidata": ["24622 km"]}

## NASA Relation Semantics Warnings

- `火星` / `ORBITS` from `Distance from Sun (10^6 km)`: Distance from Sun is an orbital-distance field, not a direct ORBITS ontology assertion.

## Boundary

- Audit results are not used for default answer fusion.
- `ACTIVE_SOURCE` remains `zh_wikipedia`.
