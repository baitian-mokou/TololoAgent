# Sandbox Candidate Review

未注册 Manifest 2.0 候选源的离线预审汇总；不联网，不写正式 raw/triples/Chroma/Neo4j。

| source_id | mode | candidates | accepted | review | exploratory | rejected | skipped | recommendation |
|---|---|---:|---:|---:|---:|---:|---:|---|
| academic_example | academic | 4 | 0 | 2 | 1 | 1 | 0 | manual_sample_first |
| generic_unknown_example | generic_unknown | 4 | 0 | 0 | 1 | 3 | 0 | needs_manifest_fix |
| official_science_example | official_science | 4 | 2 | 0 | 0 | 2 | 0 | ready_for_small_batch |
| publisher_example | publisher | 4 | 0 | 2 | 0 | 2 | 0 | manual_sample_first |

## Manual Review Decisions

| source_id | recommendation | review_decision | sample_size | approved_size | reviewer_notes | top reasons | next_action |
|---|---|---|---:|---:|---|---|---|
| academic_example | manual_sample_first | pending | 5-10 | 0 |  | academic or preprint domain, short text, reference signal present | manual sample 5-10 candidates before ingest |
| generic_unknown_example | needs_manifest_fix | needs_manifest_fix | 0 | 0 | Fixture review: too many search/tag/privacy samples; tighten include/exclude before any trial. | news/update signal, topic taxonomy hits=1, very short text | fix manifest before any ingest trial |
| official_science_example | ready_for_small_batch | approved_for_small_batch | 10-20 | 12 | Fixture review: accepted mission/fact samples look usable; rejected samples are expected gallery/privacy noise. | official or academic domain, science keyword hits=11, fact or overview page signal | plan small-batch ingest for approved_sample_size=12; do not auto-run ingest |
| publisher_example | manual_sample_first | pending | 5-10 | 0 |  | organization domain, publication/abstract signal, reference signal present | manual sample 5-10 candidates before ingest |

## Candidate Samples

### academic_example

| title | url | triage | score | reasons |
|---|---|---|---:|---|
| Planetary Spectroscopy Laboratory Project | https://astro.example.edu/research/planetary-lab/mars-spectroscopy | review_needed | 65 | academic or preprint domain, topic taxonomy hits=4, science keyword hits=12 |
| Exoplanet Atmosphere Abstract | https://astro.example.edu/papers/exoplanet-atmosphere-abstract | review_needed | 57 | academic or preprint domain, topic taxonomy hits=1, science keyword hits=7 |
| Lab open day news | https://astro.example.edu/news/lab-open-day | exploratory | 8 | academic or preprint domain, topic taxonomy hits=2, science keyword hits=3 |
| People index | https://astro.example.edu/people | rejected | 0 | academic or preprint domain, very short text, low science signal |

### generic_unknown_example

| title | url | triage | score | reasons |
|---|---|---|---:|---|
| Jupiter moon update | https://science-blog.example.com/news/jupiter-moon-update | exploratory | 27 | topic taxonomy hits=1, science keyword hits=8, mission page signal |
| Search results | https://science-blog.example.com/search?q=mars | rejected | 0 | topic taxonomy hits=1, science keyword hits=2, publication/abstract signal |
| Mars tag archive | https://science-blog.example.com/tag/mars | rejected | 0 | topic taxonomy hits=2, science keyword hits=4, very short text |
| Privacy and cookie settings | https://science-blog.example.com/privacy | rejected | 0 | topic taxonomy hits=1, science keyword hits=1, very short text |

### official_science_example

| title | url | triage | score | reasons |
|---|---|---|---:|---|
| Mars Fact Sheet | https://agency.example.gov/solar-system/mars-fact-sheet | accepted | 86 | official or academic domain, topic taxonomy hits=2, science keyword hits=11 |
| Jupiter Orbiter Mission Overview | https://agency.example.gov/missions/jupiter-orbiter | accepted | 84 | official or academic domain, topic taxonomy hits=3, science keyword hits=11 |
| Mars image gallery | https://agency.example.gov/gallery/mars-images | rejected | 0 | official or academic domain, science keyword hits=1, very short text |
| Privacy policy | https://agency.example.gov/privacy | rejected | 0 | official or academic domain, very short text, blocked path/content signal |

### publisher_example

| title | url | triage | score | reasons |
|---|---|---|---:|---|
| Planetary Atmosphere Paper Abstract | https://journal.example.org/articles/planetary-atmosphere-abstract | review_needed | 53 | organization domain, topic taxonomy hits=3, science keyword hits=8 |
| Comet Orbit Dataset Article | https://journal.example.org/articles/comet-orbit-dataset | review_needed | 38 | organization domain, science keyword hits=6, reference signal present |
| Subscribe | https://journal.example.org/subscribe | rejected | 0 | organization domain, publication/abstract signal, very short text |
| Journal catalog | https://journal.example.org/catalog | rejected | 0 | organization domain, publication/abstract signal, very short text |


## Recommendation Rules

- `needs_manifest_fix`: 候选为空或 rejected 较多，先修 manifest / include-exclude。
- `manual_sample_first`: 候选相关但证据不足，先人工抽样。
- `ready_for_small_batch`: 有 accepted 且无硬风险，可进入小批量 trial。
- `source_specific_gate`: 机器数据 / entity data 走专用 gate，不套普通网页规则。
