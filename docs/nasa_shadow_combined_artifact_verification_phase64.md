# NASA combined shadow artifact verification

- ready: `True`
- blocked_reason: ``
- counts: `{'items': 72, 'triples': 288, 'narratives': 288}`
- expected_counts: `{'items': 72, 'triples': 288, 'narratives': 288}`
- duplicate_triples: `0`
- rebuild_command: `python scripts\merge_nasa_shadow_packages.py --report-phase "Phase 62" --base-package-dir data\triples_shadow\nasa --next-package-dir evaluation\four_source_expansion\nasa_fourth_shadow_package_phase60 --next-approval evaluation\four_source_expansion\nasa_fourth_shadow_package_approval_phase60.json --shadow-output-dir data\triples_shadow\nasa --report-json evaluation\four_source_expansion\nasa_shadow_combined_merge_apply_phase62.json --report-md docs\nasa_shadow_combined_merge_apply_phase62.md --execute`
- formal_default_triples_write: `False`
- chroma_write: `False`
- neo4j_write: `False`
- active_source_unchanged: `True`
