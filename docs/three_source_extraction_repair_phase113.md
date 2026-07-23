# Phase113 zh/NASA/ESA Extraction Repair Preview

- overall_status: three_source_repair_preview_ready_for_review
- source_counts: {'zh_wikipedia': {'total': 3, 'repaired_preview_count': 3, 'rejected_remaining': 0}, 'nasa': {'total': 5, 'repaired_preview_count': 2, 'rejected_remaining': 3}, 'esa': {'total': 7, 'repaired_preview_count': 0, 'rejected_remaining': 7}}
- source_readiness: {'zh_wikipedia': 'can_reenter_controlled_preview_after_review', 'nasa': 'can_reenter_controlled_preview_after_review', 'esa': 'blocked_needs_source_strategy_repair'}
- root_cause_counts: {'zh_json_template_table_noise': 3, 'nasa_url_array_or_meta_thin': 2, 'nasa_html_boilerplate': 3, 'esa_html_listing_or_index': 7}
- production/preflight/apply/ingest: false

## Next Candidate Rules
### zh_wikipedia
- use article body extraction before templates/tables/infobox
- reject JSON-wrapped previews unless narrative_excerpt is extracted
- require readable paragraph text
### nasa
- use structured endpoint/body fields only
- reject image URL arrays and generic HTML pages
- require non-boilerplate mission/science body text
### esa
- use mission/science article body extraction
- reject HTML shell, news/listing/index pages
- require body paragraph after page-type filter
