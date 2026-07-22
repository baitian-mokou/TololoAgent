# Preview Network Probe Plan

NOT EXECUTED: 这是未来 preview-only 网络探测的安全预演，不是执行结果。本阶段不联网、不抓取、不写正式库。

| source_id | max_pages | rate_limit_s | status | network | preview_only | approval | command |
|---|---:|---:|---|---|---|---|---|
| data_portal_candidate | 8 | 1.0 | planned | False | True | True | `NOT EXECUTED / PREVIEW ONLY: python scripts/preview_source_frontier.py --manifest configs/source_manifests/candidates/data_portal_candidate.json --fetch-links --quality-score --limit 8 --json-out evaluation/source_quality/sandbox/data_portal_candidate_preview_network_probe.json` |
| noaa_climate_candidate | 8 | 1.0 | planned | False | True | True | `NOT EXECUTED / PREVIEW ONLY: python scripts/preview_source_frontier.py --manifest configs/source_manifests/candidates/noaa_climate_candidate.json --fetch-links --quality-score --limit 8 --json-out evaluation/source_quality/sandbox/noaa_climate_candidate_preview_network_probe.json` |

## Safety

- `execution_status=not_run`
- `network=false` in this plan
- `formal_pipeline_write=false`
- future command requires explicit user approval
- command is preview-only and writes only sandbox/evaluation reports
