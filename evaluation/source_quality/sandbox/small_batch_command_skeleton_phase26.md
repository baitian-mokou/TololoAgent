# Small-Batch Command Skeleton

NOT EXECUTED / DRY RUN: 这是人工执行前的操作包，不是执行结果；不联网、不抓取、不写正式库。

闭环：自动筛查 -> 人审 -> 计划预览 -> 手动确认命令。

| source_id | approved_size | execution_status | manual approval | proposed command |
|---|---:|---|---|---|
| official_science_example | 12 | not_run | True | `NOT EXECUTED / DRY RUN ONLY: python scripts/preview_source_frontier.py --manifest configs/source_manifests/examples/official_science_example.json --quality-score --limit 12 --json-out evaluation/source_quality/sandbox/official_science_example_future_frontier_preview.json` |

## Pre-Run Checklist

### official_science_example
- [ ] operator manually approves this command
- [ ] run preview before any future ingest
- [ ] keep output under evaluation/source_quality/sandbox for this stage
- [ ] do not write data/raw_json, triples, Chroma, or Neo4j from this skeleton
