# Source Conflict Audit v2

This v2 audit is read-only. It normalizes numeric units and atmosphere synonyms for audit reporting only; it does not alter triples, Chroma, Neo4j, retrieval, GUI behavior, or default answers.

## Summary

- `total_records`: 248
- `total_subject_relation_keys`: 188
- `metadata_incomplete_count`: 0
- `insufficient_metadata_count`: 0
- `value_conflict_count`: 9
- `likely_zhwiki_extraction_error_count`: 7
- `exact_match_count`: 5
- `unit_equivalent_count`: 16
- `normalized_equivalent_count`: 0
- `synonym_equivalent_count`: 2
- `source_missing_count`: 188

## V1 vs V2

- `v1_value_conflict_count`: 19
- `v2_value_conflict_count`: 9
- `v2_unit_equivalent_count`: 16
- `v2_normalized_equivalent_count`: 0
- `v2_synonym_equivalent_count`: 2
- `v2_likely_zhwiki_extraction_error_count`: 7

## Source Missing Breakdown

- `wikidata` missing: 95
- `nasa` missing: 187
- `zh_wikipedia` missing: 55

## Remaining Value Conflicts

- `天王星` / `HAS_MASS`: Missing sources: nasa. Values parse successfully but normalized values differ for HAS_MASS. {"zh_wikipedia": ["0.0013 × 10 25 kg"], "wikidata": ["8.6810e25 kg"]}
- `天王星` / `HAS_RADIUS`: Missing sources: nasa. Values remain different after normalization; at least one source could not be fully parsed for HAS_RADIUS. {"zh_wikipedia": ["4km", "20km"], "wikidata": ["25362 km"]}
- `月球` / `ORBITS`: Missing sources: nasa. Values parse successfully but normalized values differ for ORBITS. {"zh_wikipedia": ["太阳系内密度第二高"], "wikidata": ["地球"]}
- `木卫二` / `HAS_MASS`: Missing sources: nasa. Values parse successfully but normalized values differ for HAS_MASS. {"zh_wikipedia": ["0.000 013 × 10 22 kg"], "wikidata": ["4.7998e22 kg"]}
- `木卫四` / `HAS_MASS`: Missing sources: nasa. Values parse successfully but normalized values differ for HAS_MASS. {"zh_wikipedia": ["0.000 137 × 10 23 kg"], "wikidata": ["1.0759e23 kg"]}
- `火卫一` / `HAS_MASS`: Missing sources: nasa. Values parse successfully but normalized values differ for HAS_MASS. {"zh_wikipedia": ["1.072 × 10 16 kg"], "wikidata": ["1.0659e16 kg"]}
- `火卫一` / `HAS_RADIUS`: Missing sources: nasa. Values remain different after normalization; at least one source could not be fully parsed for HAS_RADIUS. {"zh_wikipedia": ["11.1km"], "wikidata": ["11.2667 km"]}
- `谷神星` / `HAS_RADIUS`: Missing sources: nasa. Values parse successfully but normalized values differ for HAS_RADIUS. {"zh_wikipedia": ["473 km"], "wikidata": ["469.7 km"]}
- `金星` / `HAS_RADIUS`: Missing sources: nasa. Values remain different after normalization; at least one source could not be fully parsed for HAS_RADIUS. {"zh_wikipedia": ["1.0km"], "wikidata": ["6051.8 km"]}

## Likely zh_wikipedia Extraction Errors

- `冥王星` / `HAS_RADIUS`: {"zh_wikipedia": ["0.8 km"], "wikidata": ["1188.3 km"]}
- `土星` / `HAS_RADIUS`: {"zh_wikipedia": ["232 km", "268 km", "10 km"], "wikidata": ["58232 km"]}
- `木卫二` / `HAS_RADIUS`: {"zh_wikipedia": ["0.5 km"], "wikidata": ["1560.8 km"]}
- `木卫四` / `HAS_RADIUS`: {"zh_wikipedia": ["1.5 km"], "wikidata": ["2410.3 km"]}
- `木星` / `HAS_RADIUS`: {"zh_wikipedia": ["0.4 km"], "wikidata": ["69911 km"]}
- `水星` / `HAS_RADIUS`: {"zh_wikipedia": ["1.0 km"], "wikidata": ["2439.7 km"]}
- `海王星` / `HAS_RADIUS`: {"zh_wikipedia": ["15 km", "30 km"], "wikidata": ["24622 km"]}

## Boundary

- Audit results are not used for default answer fusion.
- `ACTIVE_SOURCE` remains `zh_wikipedia`.
