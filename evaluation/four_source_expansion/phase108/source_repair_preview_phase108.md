# Phase108 Source-Specific Repair Preview

- Overall status: source_repair_preview_ready_for_review
- Readiness for deeper crawl gate: ready_for_controlled_deeper_crawl_gate_with_review
- Production/apply/preflight: false

## Repair Counts
- zh_wikipedia: {'repaired_candidates': 0, 'rejected_remaining': 3}
- esa: {'repaired_candidates': 0, 'conditional_preserved': 8, 'rejected_remaining': 1}
- nasa: {'conditional_preserved': 2, 'rejected_remaining': 3}
- wikidata: {'repaired_candidates': 10, 'conditional_preserved': 10}

## Blockers
- zh_wikipedia needs better body extraction or resampling after template/table removal.
- ESA needs index/news/listing URL filters before adding rejected page back.
- NASA needs stronger official body/API source before expanding beyond 2 conditional items.
- Wikidata needs enrichment beyond thin QID/source facts.
