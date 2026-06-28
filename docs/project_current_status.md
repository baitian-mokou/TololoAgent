# Current Project Status

- Stable commit: `7b0df21b95379ceb2a41910e32ecbe5683e09f5d`
- Stable tag: `checkpoint/p26-uranus-radius-dedup-applied-green-20260628`
- Official active source: `zh_wikipedia`
- Default GUI source: `zh_wikipedia`
- GUI explicit single-source options: `zh_wikipedia`, `wikidata`, `nasa`, `esa`
- SourceRouter is not enabled by default.
- Default multi-source fusion is not enabled.

## Formal Quality Fixes

- Moon formal triple is `月球 / ORBITS / 地球`.
- Uranus formal triple is `天王星 / HAS_RADIUS / 25362 km`.
- Uranus `HAS_RADIUS` official triples no longer contain `4km`.
- Uranus `HAS_RADIUS` official triples no longer contain `20km`.
- Uranus `HAS_RADIUS` official triples currently keep one `25362 km` record.

## Backup And Rollback

- Uranus radius apply backup dir: `F:\知识表示与处理结课作业\第二次托洛洛测试 -重大进展\data\backups\quality_review\20260628_132128`
- Uranus radius rollback manifest: `F:\知识表示与处理结课作业\第二次托洛洛测试 -重大进展\data\backups\quality_review\20260628_132128\rollback_manifest.json`
- Current quality-review apply reports still record `chroma_written=false` and `neo4j_written=false`.

## Shadow Source Coverage

- Wikidata shadow namespace is present as disabled optional source `wikidata_shadow_ready_v1`.
- NASA shadow namespace is present as disabled optional source `nasa_shadow_ready_v1`.
- ESA shadow namespace is present as disabled optional source with local materialized files for `SMART-1`, `火星快车号`, and `金星快车号`.
- `python scripts/run_source_expansion_eval.py --source wikidata` currently passes with `27/27` exact pass count.
- `python scripts/run_source_expansion_eval.py --source nasa` currently passes with `26/26` exact pass count.

## Settings And Registry

- `settings.json` is not committed.
- Source registry remains: `zh_wikipedia=active`, `wikidata=disabled`, `nasa=disabled`, `esa=disabled`.

## Remaining Risks And Todo

- Quality review decisions still show `6` pending items.
- Quality review decisions still show `2` approved value-change patches already applied (`source_conflict_v4_002`, `source_conflict_v4_003`).
- ESA shadow coverage is smaller than Wikidata and NASA shadow coverage.
