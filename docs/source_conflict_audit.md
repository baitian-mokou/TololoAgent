# Source Conflict Audit

This audit is read-only. It compares existing triples in `zh_wikipedia`, `wikidata`, and `nasa`; it does not alter retrieval, fusion, Chroma, Neo4j, or default answers.

## Summary

- `total_records`: 248
- `total_subject_relation_keys`: 188
- `metadata_incomplete_count`: 0
- `value_conflict_count`: 18
- `exact_match_count`: 6
- `unit_equivalent_count`: 15
- `source_missing_count`: 188

## Status Counts

- `source_missing`: 188
- `unit_equivalent`: 15
- `value_conflict`: 18
- `exact_match`: 6

## Notable Value Conflicts

- `冥王星` / `HAS_RADIUS`: {"zh_wikipedia": ["0.8 km"], "wikidata": ["1188.3 km"]}
- `土星` / `HAS_RADIUS`: {"zh_wikipedia": ["232 km", "268 km", "10 km"], "wikidata": ["58232 km"]}
- `地球` / `HAS_ATMOSPHERE`: {"zh_wikipedia": ["N2", "O2", "Ar", "H2O", "CO2"], "wikidata": ["氮气;氧气;氩气"]}
- `地球` / `HAS_MASS`: {"zh_wikipedia": ["5.972 37 × 10 24 kg"], "wikidata": ["5.97237e24 kg"]}
- `天王星` / `HAS_MASS`: {"zh_wikipedia": ["0.0013 × 10 25 kg"], "wikidata": ["8.6810e25 kg"]}
- `天王星` / `HAS_RADIUS`: {"zh_wikipedia": ["4km", "20km"], "wikidata": ["25362 km"]}
- `木卫二` / `HAS_MASS`: {"zh_wikipedia": ["0.000 013 × 10 22 kg"], "wikidata": ["4.7998e22 kg"]}
- `木卫二` / `HAS_RADIUS`: {"zh_wikipedia": ["0.5 km"], "wikidata": ["1560.8 km"]}
- `木卫四` / `HAS_MASS`: {"zh_wikipedia": ["0.000 137 × 10 23 kg"], "wikidata": ["1.0759e23 kg"]}
- `木卫四` / `HAS_RADIUS`: {"zh_wikipedia": ["1.5 km"], "wikidata": ["2410.3 km"]}
- `木星` / `HAS_RADIUS`: {"zh_wikipedia": ["0.4 km"], "wikidata": ["69911 km"]}
- `水星` / `HAS_RADIUS`: {"zh_wikipedia": ["1.0 km"], "wikidata": ["2439.7 km"]}
- `海王星` / `HAS_RADIUS`: {"zh_wikipedia": ["15 km", "30 km"], "wikidata": ["24622 km"]}
- `火卫一` / `HAS_MASS`: {"zh_wikipedia": ["1.072 × 10 16 kg"], "wikidata": ["1.0659e16 kg"]}
- `火卫一` / `HAS_RADIUS`: {"zh_wikipedia": ["11.1km"], "wikidata": ["11.2667 km"]}
- `火星` / `HAS_ATMOSPHERE`: {"zh_wikipedia": ["CO2", "N2", "Ar", "O2"], "wikidata": ["二氧化碳;氮气;氩气"]}
- `谷神星` / `HAS_RADIUS`: {"zh_wikipedia": ["473 km"], "wikidata": ["469.7 km"]}
- `金星` / `HAS_RADIUS`: {"zh_wikipedia": ["1.0km"], "wikidata": ["6051.8 km"]}

## Metadata Issues

- No metadata-incomplete records found.

## Boundary

- Audit results are not used for default answer fusion.
- `ACTIVE_SOURCE` remains `zh_wikipedia`.
