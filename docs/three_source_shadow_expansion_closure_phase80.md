# Three-source shadow expansion closure

- NASA: `next/nasa-shadow-apply-guarded-2` at `a23d8ee36286ac1a49981027c89cc0937b89ea79`; local shadow `72/288/288`; readiness/eval `10/10`; explicit review-only CLI present.
- ESA: `next/esa-shadow-controlled-preview` at `698b5a0d1e73bb5b11634b56ae0ace18eea5aff5`; local shadow `18/70/71`; readiness/eval `10/10`; explicit review-only CLI present.
- Wikidata: `next/wikidata-shadow-controlled-preview` at `5e1ec5a75f0a6eed966c9f4ab03d508a1d2797fd`; local shadow `25/151/25`; readiness/eval `10/10`; explicit review-only CLI present.
- Boundaries: `ACTIVE_SOURCE=zh_wikipedia`; NASA/ESA/Wikidata disabled; no default triples, Chroma, or Neo4j writes; no shadow data committed.
- Remaining risks: local shadow artifacts need rebuild/verify on other machines; review-only CLIs are not GUI/default query integrations; Chroma shadow indexing has not had a dry-run.
- Next options: GUI review-only integration, Chroma shadow dry-run, broader source filtering before more source expansion.
