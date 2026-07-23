# Phase109 Controlled Deeper Crawl Gate Design

- Gate readiness: ready_to_run_controlled_deeper_crawl_after_review
- Total max batch: 80
- Live fetch in this phase: false
- Production/preflight/apply/ingest: false

## Source Limits
- zh_wikipedia: max 20; gates=['body_extraction', 'template_table_ratio', 'minimum_readable_text']; deny=['infobox', 'table-heavy', 'template-heavy', 'category', 'special']
- nasa: max 10; gates=['endpoint_method_recorded', 'non_navigation_text', 'metadata_not_thin_only']; deny=['search', 'gallery', 'index', 'tag', 'category', 'navigation']
- esa: max 20; gates=['mission_or_science_signal', 'index_listing_filter', 'minimum_readable_text']; deny=['index', 'news listing', 'latest', 'tag', 'category', 'press list']
- wikidata: max 30; gates=['claim_filter', 'reference_or_source_field', 'non_empty_structured_fact']; deny=['no-claim', 'disambiguation', 'unreferenced', 'thin-label-only']
