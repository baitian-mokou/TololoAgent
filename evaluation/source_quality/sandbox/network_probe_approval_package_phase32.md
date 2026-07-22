# Network Probe Approval Package

NOT EXECUTED / REQUIRES EXPLICIT USER APPROVAL. 本报告是 future preview-only 网络探测的人审材料，不是执行结果。

- approval_status: `pending_user_approval`
- execution_status: `not_run`
- network: `False`
- formal_pipeline_write: `False`

## data_portal_candidate

| field | value |
|---|---|
| allowed_domains | `data.example.gov` |
| seed_urls | `https://data.example.gov/datasets/solar-irradiance` |
| max_pages | `8` |
| rate_limit_seconds | `1.0` |
| quality_gate_required | `True` |
| preview_only | `True` |
| execution_status | `not_run` |
| network | `False` |
| preview_command | `NOT EXECUTED / PREVIEW ONLY: python scripts/preview_source_frontier.py --manifest configs/source_manifests/candidates/data_portal_candidate.json --fetch-links --quality-score --limit 8 --json-out evaluation/source_quality/sandbox/data_portal_candidate_preview_network_probe.json` |

### Manual Checklist

- [ ] confirm_domains: confirm_domains match the intended candidate source
- [ ] confirm: confirm rate limit is acceptable before any future network preview
- [ ] confirm_output_path: confirm_output_path stays under evaluation/source_quality/sandbox
- [ ] confirm: confirm no formal write to data/raw_json, triples, Chroma, or Neo4j
- [ ] confirm_quality_gate: confirm_quality_gate remains enabled for preview-only results

### Risks

- future preview command would use network if manually run
- seed pages may link to off-topic pages even under allowed domains
- quality scoring still needs rejected-sample review after preview

## noaa_climate_candidate

| field | value |
|---|---|
| allowed_domains | `climate.gov, www.climate.gov, noaa.gov` |
| seed_urls | `https://www.climate.gov/climate-and-energy/topics/climate-change` |
| max_pages | `8` |
| rate_limit_seconds | `1.0` |
| quality_gate_required | `True` |
| preview_only | `True` |
| execution_status | `not_run` |
| network | `False` |
| preview_command | `NOT EXECUTED / PREVIEW ONLY: python scripts/preview_source_frontier.py --manifest configs/source_manifests/candidates/noaa_climate_candidate.json --fetch-links --quality-score --limit 8 --json-out evaluation/source_quality/sandbox/noaa_climate_candidate_preview_network_probe.json` |

### Manual Checklist

- [ ] confirm_domains: confirm_domains match the intended candidate source
- [ ] confirm: confirm rate limit is acceptable before any future network preview
- [ ] confirm_output_path: confirm_output_path stays under evaluation/source_quality/sandbox
- [ ] confirm: confirm no formal write to data/raw_json, triples, Chroma, or Neo4j
- [ ] confirm_quality_gate: confirm_quality_gate remains enabled for preview-only results

### Risks

- future preview command would use network if manually run
- seed pages may link to off-topic pages even under allowed domains
- quality scoring still needs rejected-sample review after preview
