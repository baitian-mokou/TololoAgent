# Sandbox Candidate Review

未注册 Manifest 2.0 候选源的离线预审汇总；不联网，不写正式 raw/triples/Chroma/Neo4j。

| source_id | mode | candidates | accepted | review | exploratory | rejected | skipped | recommendation |
|---|---|---:|---:|---:|---:|---:|---:|---|
| arxiv_preprint_candidate | academic | 3 | 0 | 2 | 0 | 1 | 0 | manual_sample_first |
| data_portal_candidate | official_science | 3 | 1 | 1 | 0 | 1 | 0 | ready_for_small_batch |
| journal_publisher_candidate | publisher | 3 | 0 | 3 | 0 | 0 | 0 | manual_sample_first |
| museum_observatory_candidate | generic_unknown | 3 | 0 | 1 | 1 | 1 | 0 | manual_sample_first |
| noaa_climate_candidate | official_science | 3 | 1 | 0 | 1 | 1 | 0 | ready_for_small_batch |
| university_lab_candidate | academic | 3 | 0 | 3 | 0 | 0 | 0 | manual_sample_first |

## Manual Review Decisions

| source_id | recommendation | review_decision | sample_size | approved_size | reviewer_notes | top reasons | next_action |
|---|---|---|---:|---:|---|---|---|
| arxiv_preprint_candidate | manual_sample_first | pending | 5-10 | 0 | 预印本元数据应先设计 paper-specific gate；本阶段不接 API。 | academic or preprint domain, publication/abstract signal, reference signal present | manual sample 5-10 candidates before ingest |
| data_portal_candidate | ready_for_small_batch | approved_for_small_batch | 10-20 | 8 | 示例回填：dataset metadata page 有 table/reference 信号，login 噪声被拒绝；仅用于计划预览。 | official or academic domain, short text, topic taxonomy hits=4 | plan small-batch ingest for approved_sample_size=8; do not auto-run ingest |
| journal_publisher_candidate | manual_sample_first | pending | 5-10 | 0 | publisher landing、abstract、author guideline 混杂，需人工抽样判断。 | organization domain, publication/abstract signal, short text | manual sample 5-10 candidates before ingest |
| museum_observatory_candidate | manual_sample_first | pending | 5-10 | 0 | 教育内容可能有用，但 generic_unknown 需要更保守抽样。 | organization domain, short text, topic taxonomy hits=4 | manual sample 5-10 candidates before ingest |
| noaa_climate_candidate | ready_for_small_batch | approved_for_small_batch | 10-20 | 8 | 示例回填：NOAA-style fixture 中 fact/data page 可用，rejected search 噪声符合预期；仅用于计划预览，不代表已执行抓取。 | official or academic domain, topic taxonomy hits=4, science keyword hits=5 | plan small-batch ingest for approved_sample_size=8; do not auto-run ingest |
| university_lab_candidate | manual_sample_first | pending | 5-10 | 0 | 需要人工抽样实验室项目页和 publication abstract，确认是否适合进入小批量。 | academic or preprint domain, short text, topic taxonomy hits=3 | manual sample 5-10 candidates before ingest |

## Candidate Samples

### arxiv_preprint_candidate

| title | url | triage | score | reasons |
|---|---|---|---:|---|
| A Survey of Small Bodies in the Outer Solar System | https://arxiv.org/abs/2601.00001 | review_needed | 67 | academic or preprint domain, topic taxonomy hits=3, science keyword hits=9 |
| Exoplanet Atmosphere Retrieval with Telescope Spectroscopy | https://arxiv.org/abs/2601.00002 | review_needed | 57 | academic or preprint domain, topic taxonomy hits=1, science keyword hits=7 |
| arXiv Search | https://arxiv.org/search/?query=mars&searchtype=all | rejected | 45 | academic or preprint domain, science keyword hits=1, publication/abstract signal |

### data_portal_candidate

| title | url | triage | score | reasons |
|---|---|---|---:|---|
| Solar Irradiance Dataset Metadata | https://data.example.gov/datasets/solar-irradiance | accepted | 77 | official or academic domain, topic taxonomy hits=4, science keyword hits=6 |
| Earth Science Data Catalog | https://data.example.gov/catalog/earth-science | review_needed | 45 | official or academic domain, topic taxonomy hits=3, science keyword hits=7 |
| Data Portal Login | https://data.example.gov/login | rejected | 0 | official or academic domain, very short text, low science signal |

### journal_publisher_candidate

| title | url | triage | score | reasons |
|---|---|---|---:|---|
| Review Article: Planetary Atmospheres | https://journal.example.org/articles/planetary-atmospheres-review | review_needed | 54 | organization domain, topic taxonomy hits=4, science keyword hits=8 |
| Solar System Science Collection | https://journal.example.org/collections/solar-system-science | review_needed | 34 | organization domain, topic taxonomy hits=3, science keyword hits=6 |
| Author Guidelines | https://journal.example.org/authors/guidelines | review_needed | 20 | organization domain, topic taxonomy hits=1, science keyword hits=1 |

### museum_observatory_candidate

| title | url | triage | score | reasons |
|---|---|---|---:|---|
| Planets of the Solar System | https://observatory.example.org/education/solar-system/planets | review_needed | 40 | organization domain, topic taxonomy hits=4, science keyword hits=13 |
| New Telescope Night | https://observatory.example.org/news/new-telescope-night | exploratory | 0 | organization domain, topic taxonomy hits=2, science keyword hits=3 |
| Nebula Image Gallery | https://observatory.example.org/gallery/nebula-images | rejected | 0 | organization domain, very short text, media/gallery signal |

### noaa_climate_candidate

| title | url | triage | score | reasons |
|---|---|---|---:|---|
| Climate Change: Global Temperature Indicators | https://www.climate.gov/climate-and-energy/topics/climate-change | accepted | 70 | official or academic domain, topic taxonomy hits=4, science keyword hits=5 |
| Seasonal Climate Outlook News | https://www.climate.gov/news/features/new-seasonal-outlook | exploratory | 45 | official or academic domain, topic taxonomy hits=4, science keyword hits=5 |
| Search results | https://www.climate.gov/search?query=climate | rejected | 0 | official or academic domain, topic taxonomy hits=1, science keyword hits=1 |

### university_lab_candidate

| title | url | triage | score | reasons |
|---|---|---|---:|---|
| Exoplanet Spectroscopy Research Lab | https://astro.example.edu/lab/exoplanet-spectroscopy | review_needed | 60 | academic or preprint domain, topic taxonomy hits=3, science keyword hits=13 |
| Abstract: Atmospheric Retrievals for Exoplanets | https://astro.example.edu/publications/planetary-atmospheres-abstract | review_needed | 63 | academic or preprint domain, topic taxonomy hits=3, science keyword hits=7 |
| Lab Open House Event | https://astro.example.edu/events/open-house | review_needed | 14 | academic or preprint domain, topic taxonomy hits=1, science keyword hits=1 |


## Recommendation Rules

- `needs_manifest_fix`: 候选为空或 rejected 较多，先修 manifest / include-exclude。
- `manual_sample_first`: 候选相关但证据不足，先人工抽样。
- `ready_for_small_batch`: 有 accepted 且无硬风险，可进入小批量 trial。
- `source_specific_gate`: 机器数据 / entity data 走专用 gate，不套普通网页规则。
