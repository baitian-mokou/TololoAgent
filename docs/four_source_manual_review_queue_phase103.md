# Phase103 Manual Review Queue Report

- queue_verdict: `manual_review_queue_ready_approval_pending`
- queue_count: 27
- production_ready: `False`
- shadow_apply_preflight_recommended: `False`

| source | count |
|---|---:|
| esa | 9 |
| nasa | 5 |
| wikidata | 10 |
| zh_wikipedia | 3 |

Checklist:
- Accept only if provenance, source identity, review text, and triples are human-checkable.
- Reject if the sample is mostly navigation, boilerplate, template, table, JSON wrapper, index, or news-card noise.
- Do not treat this queue as package/apply/preflight approval.
- NASA: Check endpoint/method labels; conditional WP REST items may carry navigation or Photojournal/Earth Observatory residue.
- ESA: Check for index/news-like text even when mission content is readable.
- zh_wikipedia: Check template/table noise and whether triples remain meaningful.
- Wikidata: Thin entity facts are acceptable only for identifier/fact relevance review, not rich narrative approval.

Next: review thread performs sample review; no apply/preflight.
