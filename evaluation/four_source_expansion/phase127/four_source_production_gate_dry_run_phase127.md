# Phase127 Four-source Production Gate Dry-run Design

- dry_run_only: `True`
- zh_wikipedia: `manual_review_queue_candidate_not_production_ready`
- esa: `manual_review_pending_not_production_ready`
- nasa: `conditional_not_strong_blocked`
- wikidata: `thin_conditional_only_blocked`
- queue/apply/preflight/ingest/production: `False/False/False/False/False`
- formal/default triples/Chroma/Neo4j writes: `False/False/False/False`

## Blockers
- zh_wikipedia: manual_review_required, queue_not_approved, production_write_not_approved
- esa: manual_review_pending, production_write_not_approved
- nasa: conditional_not_strong, no_strong_accepted_items, production_write_not_approved
- wikidata: thin_conditional_only, needs_stronger_evidence, production_write_not_approved

## Required Evidence
- zh_wikipedia: manual review approval for 10/10 Phase126 accepted items, dedupe/noise check, explicit production write approval
- esa: manual review approval for Phase116 pending items, dedupe/noise check, explicit production write approval
- nasa: replace conditional_not_strong with strong accepted source evidence
- wikidata: promote thin conditional records to stronger reviewed evidence

## Next Minimal Steps
- review ZH Phase126 accepted items into a manual review queue candidate
- finish ESA manual review
- keep NASA and thin Wikidata blocked until stronger evidence exists
- rerun this dry-run gate before any apply/preflight/ingest request
