# P8 External Source Review

Generated at: 2026-06-27T13:23:44.630265+00:00

This is a preview/audit report only. It does not apply patches, write Chroma, write Neo4j, or mutate formal triples.

## Summary

- Reviewed conflicts: 6
- Requires human approval: 6
- Comparison results: `{"likely_zhwiki_extraction_error": 3, "ontology_rule_needed": 1, "unresolved": 2}`
- Recommendations: `{"mark_extraction_error": 4, "defer_unresolved": 2}`

## Records

### source_conflict_v4_001 天王星 / HAS_MASS

- comparison_result: `likely_zhwiki_extraction_error`
- recommendation: `mark_extraction_error`
- confidence: 0.8
- requires_human_approval: `True`
- current_values_by_source: `{"zh_wikipedia": ["0.0013 × 10 25 kg"], "wikidata": ["8.6810e25 kg"]}`
- evidence_source: `wikidata_live_preview`
- evidence_url/source_record_id: `https://www.wikidata.org/wiki/Q324`
- fetch_errors: `[]`

### source_conflict_v4_003 月球 / ORBITS

- comparison_result: `ontology_rule_needed`
- recommendation: `mark_extraction_error`
- confidence: 0.86
- requires_human_approval: `True`
- current_values_by_source: `{"zh_wikipedia": ["太阳系内密度第二高"], "wikidata": ["地球"]}`
- evidence_source: `wikidata_live_preview`
- evidence_url/source_record_id: `https://www.wikidata.org/wiki/Q405`
- fetch_errors: `[]`

### source_conflict_v4_004 木卫二 / HAS_MASS

- comparison_result: `likely_zhwiki_extraction_error`
- recommendation: `mark_extraction_error`
- confidence: 0.78
- requires_human_approval: `True`
- current_values_by_source: `{"zh_wikipedia": ["0.000 013 × 10 22 kg"], "wikidata": ["4.7998e22 kg"]}`
- evidence_source: `wikidata_live_preview`
- evidence_url/source_record_id: `https://www.wikidata.org/wiki/Q17439`
- fetch_errors: `[]`

### source_conflict_v4_005 木卫四 / HAS_MASS

- comparison_result: `likely_zhwiki_extraction_error`
- recommendation: `mark_extraction_error`
- confidence: 0.78
- requires_human_approval: `True`
- current_values_by_source: `{"zh_wikipedia": ["0.000 137 × 10 23 kg"], "wikidata": ["1.0759e23 kg"]}`
- evidence_source: `wikidata_live_preview`
- evidence_url/source_record_id: `https://www.wikidata.org/wiki/Q16898`
- fetch_errors: `[]`

### source_conflict_v4_007 火卫一 / HAS_RADIUS

- comparison_result: `unresolved`
- recommendation: `defer_unresolved`
- confidence: 0.35
- requires_human_approval: `True`
- current_values_by_source: `{"zh_wikipedia": ["11.1km"], "wikidata": ["11.2667 km"]}`
- evidence_source: ``
- evidence_url/source_record_id: ``
- fetch_errors: `[]`

### source_conflict_v4_008 金星 / HAS_RADIUS

- comparison_result: `unresolved`
- recommendation: `defer_unresolved`
- confidence: 0.35
- requires_human_approval: `True`
- current_values_by_source: `{"zh_wikipedia": ["1.0km"], "wikidata": ["6051.8 km"]}`
- evidence_source: ``
- evidence_url/source_record_id: ``
- fetch_errors: `[{"source": "wikidata_live_preview", "error": "HTTP Error 429: Too Many Requests"}]`
