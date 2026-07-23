# Phase114 zh/NASA/ESA Source Strategy Repair Preview

- overall_status: source_strategy_repair_preview_ready_for_review
- live_probe_used: false
- probe_limits: {'per_source_max': 3, 'total_max': 9, 'total_attempted': 9}
- source_counts: {'zh_wikipedia': {'attempted': 3, 'accepted_strategy_candidates': 1, 'conditional_strategy_candidates': 0, 'blocked_strategy_candidates': 2}, 'nasa': {'attempted': 3, 'accepted_strategy_candidates': 1, 'conditional_strategy_candidates': 1, 'blocked_strategy_candidates': 1}, 'esa': {'attempted': 3, 'accepted_strategy_candidates': 0, 'conditional_strategy_candidates': 2, 'blocked_strategy_candidates': 1}}
- source_verdicts: {'zh_wikipedia': 'strategy_ready_for_small_controlled_plaintext_api_preview', 'nasa': 'strategy_ready_with_images_api_preferred_wp_rest_conditional', 'esa': 'strategy_conditional_needs_specific_article_page_type_gate'}
- production/preflight/apply/ingest: False/False/False/False

## Source Strategy Notes
- zh_wikipedia: strategy_ready_for_small_controlled_plaintext_api_preview; rules=['use MediaWiki plaintext extract API', 'reject infobox/table/template/caption-heavy text']
- nasa: strategy_ready_with_images_api_preferred_wp_rest_conditional; rules=['prefer Images API structured description', 'allow WP REST only with body-field and navigation residue gates']
- esa: strategy_conditional_needs_specific_article_page_type_gate; rules=['use specific mission/article pages', 'reject index/news/listing pages before extraction']

Next: review Phase114 strategy verdicts before any controlled deeper crawl preview rerun.
