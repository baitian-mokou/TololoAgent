# Manual Preview Command Card

NOT EXECUTED / MANUAL ONLY / PREVIEW ONLY. 本卡片只供未来人工确认后手动执行 preview-only 探测。

- execution_status: `not_run`
- network: `False`
- formal_pipeline_write: `False`

## noaa_climate_candidate

| field | value |
|---|---|
| approved_max_pages | `5` |
| allowed_domains | `climate.gov, www.climate.gov, noaa.gov` |
| seed_urls | `https://www.climate.gov/climate-and-energy/topics/climate-change` |
| rate_limit_seconds | `1.0` |
| manual_command | `NOT EXECUTED / MANUAL ONLY / PREVIEW ONLY: python scripts/preview_source_frontier.py --manifest configs/source_manifests/candidates/noaa_climate_candidate.json --fetch-links --quality-score --limit 5 --json-out evaluation/source_quality/sandbox/noaa_climate_candidate_manual_preview_probe.json` |

### Preflight Checklist

- [ ] confirm ACTIVE_SOURCE remains zh_wikipedia
- [ ] confirm allowed domains and seed URLs are still intended
- [ ] confirm rate limit and approved page limit before manual execution
- [ ] confirm quality gate remains enabled
- [ ] confirm no formal write to data/raw_json, triples, Chroma, or Neo4j
- [ ] confirm output path stays under evaluation/source_quality/sandbox

### Expected Outputs

- `evaluation/source_quality/sandbox/noaa_climate_candidate_manual_preview_probe.json`
