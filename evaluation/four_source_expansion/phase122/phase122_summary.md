# Phase122 ZH External Seed Package Spec

Required seed fields: `source_url`, `title`, `retrieved_at`, `license_or_terms`, `body`, `expected_sha256`.
Optional field: `provenance_notes` for operator/tool/API/export details.

Checksum: compute `sha256` over the exact UTF-8 `body` string.
Body requirements: readable Chinese article text only; no table/infobox/template/caption-heavy text, mojibake, or numeric-heavy dumps.
Naming: one `.json` seed per article, or one JSON list file; keep files outside repo `data/` paths.

Run later review-only intake: `python scripts/zh_multi_seed_review_package_phase121.py --input-dir <seed-dir> --write`.

Flags: queue=False, production=False, preflight=False, apply=False, ingest=False.
This spec does not approve queue/apply/preflight/ingest/production.
