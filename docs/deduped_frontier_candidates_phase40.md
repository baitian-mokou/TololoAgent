# 去重后的 frontier 扩批候选

Phase 39 前 20 候选几乎全是重复记录；本报告先按已入库 raw URL/title 和失败 URL 做去重，选择下一批真正值得 raw-only trial 的候选。

- phase: `Phase 40`
- limit: `50`

| source | existing raw | frontier total | duplicate | failed/blocked | selected | next action |
|---|---:|---:|---:|---:|---:|---|
| nasa | 95 | 150 | 79 | 1 | 50 | `ready_for_raw_shadow_trial` |
| esa | 168 | 150 | 140 | 2 | 8 | `ready_for_raw_shadow_trial` |

## Selected Candidates

### nasa
- https://science.nasa.gov/solar-system/asteroids/facts/ - `https://science.nasa.gov/solar-system/asteroids/facts/`
- https://science.nasa.gov/solar-system/asteroids/exploration/ - `https://science.nasa.gov/solar-system/asteroids/exploration/`
- https://science.nasa.gov/solar-system/asteroids/2024-yr4/ - `https://science.nasa.gov/solar-system/asteroids/2024-yr4/`
- https://science.nasa.gov/solar-system/asteroids/apophis/ - `https://science.nasa.gov/solar-system/asteroids/apophis/`
- https://science.nasa.gov/solar-system/asteroids/16-psyche/ - `https://science.nasa.gov/solar-system/asteroids/16-psyche/`
- https://science.nasa.gov/solar-system/asteroids/101955-bennu/ - `https://science.nasa.gov/solar-system/asteroids/101955-bennu/`
- https://science.nasa.gov/solar-system/asteroids/dinkinesh/ - `https://science.nasa.gov/solar-system/asteroids/dinkinesh/`
- https://science.nasa.gov/solar-system/asteroids/donaldjohanson/ - `https://science.nasa.gov/solar-system/asteroids/donaldjohanson/`
- https://science.nasa.gov/solar-system/asteroids/didymos/ - `https://science.nasa.gov/solar-system/asteroids/didymos/`
- https://science.nasa.gov/solar-system/asteroids/4-vesta/ - `https://science.nasa.gov/solar-system/asteroids/4-vesta/`
- ... and 40 more

### esa
- https://sci.esa.int/web/juice/journal-archive - `https://sci.esa.int/web/juice/journal-archive`
- https://scifleet.esa.int/model/juice/ - `https://scifleet.esa.int/model/juice/`
- https://blogs.esa.int/10-years-since-rosetta/ - `https://blogs.esa.int/10-years-since-rosetta/`
- http://blogs.esa.int/rosetta/ - `http://blogs.esa.int/rosetta/`
- http://sci.esa.int/rosetta - `http://sci.esa.int/rosetta`
- http://sci.esa.int/where_is_rosetta/ - `http://sci.esa.int/where_is_rosetta/`
- https://www.cosmos.esa.int/web/gaia/data-release-4 - `https://www.cosmos.esa.int/web/gaia/data-release-4`
- https://cosmos.esa.int/web/gaia - `https://cosmos.esa.int/web/gaia`

## 安全边界

- selection report only
- no raw writes
- no downstream materialization
- nasa/esa remain shadow-only candidates
