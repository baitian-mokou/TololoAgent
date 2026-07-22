# NASA combined shadow artifact verification

- ready: `True`
- blocked_reason: ``
- counts: `{'items': 48, 'triples': 192, 'narratives': 192}`
- expected_counts: `{'items': 48, 'triples': 192, 'narratives': 192}`
- duplicate_triples: `0`
- rebuild_command: `python scripts\merge_nasa_shadow_packages.py --phase45-package-dir evaluation\four_source_expansion\nasa_limited_shadow_package_phase45 --phase52-package-dir evaluation\four_source_expansion\nasa_second_shadow_package_phase52 --phase52-approval evaluation\four_source_expansion\nasa_second_shadow_package_approval_phase52.json --shadow-output-dir data\triples_shadow\nasa --report-json evaluation\four_source_expansion\nasa_shadow_combined_merge_apply_phase54.json --report-md docs\nasa_shadow_combined_merge_apply_phase54.md --execute`
- formal_default_triples_write: `False`
- chroma_write: `False`
- neo4j_write: `False`
- active_source_unchanged: `True`
