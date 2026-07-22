# Offline Fixture Quality

本报告只验证手工保存或本地构造的 offline fixture；network=false，execution_status=not_run，不写正式数据管线。

| source_id | samples | accepted | review | exploratory | rejected | warnings |
|---|---:|---:|---:|---:|---:|---|
| noaa_climate_candidate | 3 | 1 | 0 | 1 | 1 |  |
| data_portal_candidate | 3 | 1 | 1 | 0 | 1 |  |

## Samples

### noaa_climate_candidate

| title | url | triage | score | reasons |
|---|---|---|---:|---|
| Climate Change: Global Temperature Indicators | https://www.climate.gov/climate-and-energy/topics/climate-change | accepted | 70 | official or academic domain, topic taxonomy hits=4, science keyword hits=5 |
| Seasonal Climate Outlook News | https://www.climate.gov/news/features/new-seasonal-outlook | exploratory | 45 | official or academic domain, topic taxonomy hits=4, science keyword hits=5 |
| Search results | https://www.climate.gov/search?query=climate | rejected | 0 | official or academic domain, topic taxonomy hits=1, science keyword hits=1 |

### data_portal_candidate

| title | url | triage | score | reasons |
|---|---|---|---:|---|
| Solar Irradiance Dataset Metadata | https://data.example.gov/datasets/solar-irradiance | accepted | 77 | official or academic domain, topic taxonomy hits=4, science keyword hits=6 |
| Earth Science Data Catalog | https://data.example.gov/catalog/earth-science | review_needed | 45 | official or academic domain, topic taxonomy hits=3, science keyword hits=7 |
| Data Portal Login | https://data.example.gov/login | rejected | 0 | official or academic domain, very short text, low science signal |

## Fixture Schema

每条样本建议包含 `url`、`title`、`text` 或 `html`，可选 `source_sample_type=offline_fixture/manual_sample`。这些样本只用于离线质量门验证，不能代表已经联网采集。
