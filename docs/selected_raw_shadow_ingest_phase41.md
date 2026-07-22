# selected raw-only shadow ingest

本报告只使用 Phase 40 去重候选，不重新发现 frontier，不写 triples/narratives/Chroma/Neo4j。

- phase: `Phase 41`
- active_source: `zh_wikipedia`

| source | requested | attempted | before raw | after raw | new | duplicate | failed |
|---|---:|---:|---:|---:|---:|---:|---:|
| nasa | 50 | 20 | 95 | 115 | 20 | 0 | 0 |
| esa | 8 | 8 | 168 | 171 | 3 | 0 | 5 |

## Failed URLs

- `esa`: `https://sci.esa.int/web/juice/journal-archive`, `http://sci.esa.int/rosetta`, `http://sci.esa.int/where_is_rosetta/`, `https://www.cosmos.esa.int/web/gaia/data-release-4`, `https://cosmos.esa.int/web/gaia`

## 安全边界

- only Phase 40 selected candidates
- nasa/esa only
- raw JSON only
- no downstream materialization
- ACTIVE_SOURCE remains zh_wikipedia
