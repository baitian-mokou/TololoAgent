# 项目状态索引

- 当前阶段：`Phase 36 index`
- 上一阶段：`Phase 35 complete`
- ACTIVE_SOURCE：`zh_wikipedia`
- Candidate registered：`False`

## 默认源状态

| source | status |
|---|---|
| zh_wikipedia | `active` |
| wikidata | `disabled` |
| nasa | `disabled` |
| esa | `disabled` |

## 关键报告索引

| category | path | status |
|---|---|---|
| final_status | `docs/project_current_stage_final_report.md` | `present` |
| source_expansion_delivery | `docs/source_expansion_delivery_report.md` | `present` |
| general_screening_overview | `docs/general_science_source_screening_overview.md` | `present` |
| source_expansion_status | `evaluation/source_expansion/source_expansion_status_report.json` | `present` |
| shadow_graph_probe | `evaluation/source_expansion/shadow_graph_probe_report.json` | `present` |
| manifest_validation | `evaluation/source_quality/source_manifest_validation_report.json` | `present` |
| candidate_sites_summary | `evaluation/source_quality/sandbox/candidate_science_sites_summary_phase28.json` | `present` |
| candidate_sites_filled_review | `evaluation/source_quality/sandbox/candidate_science_sites_summary_phase29_filled.json` | `present` |
| approved_plan_preview | `evaluation/source_quality/sandbox/candidate_science_sites_approved_plan_phase29.json` | `present` |
| offline_fixture_quality | `evaluation/source_quality/sandbox/offline_fixture_quality_phase30.json` | `present` |
| preview_probe_plan | `evaluation/source_quality/sandbox/preview_network_probe_plan_phase31.json` | `present` |
| network_probe_approval_package | `evaluation/source_quality/sandbox/network_probe_approval_package_phase32.json` | `present` |
| network_probe_approval_decisions | `evaluation/source_quality/sandbox/network_probe_approval_decisions_phase33_filled.json` | `present` |
| manual_preview_command_card | `evaluation/source_quality/sandbox/manual_preview_command_card_phase34.json` | `present` |

## 可复现验证命令

- `venv\Scripts\python.exe -m unittest discover tests`
- `venv\Scripts\python.exe scripts\validate_source_manifests.py`
- `venv\Scripts\python.exe scripts\report_sandbox_candidate_reviews.py --manifest-dir configs\source_manifests\candidates --sandbox-dir evaluation\source_quality\sandbox --out-json evaluation\source_quality\sandbox\candidate_science_sites_summary_phase28.json --out-md evaluation\source_quality\sandbox\candidate_science_sites_summary_phase28.md`
- `venv\Scripts\python.exe scripts\report_offline_fixture_quality.py --manifest-dir configs\source_manifests\candidates --source noaa_climate_candidate --source data_portal_candidate --fixture-dir tests\fixtures\source_quality --out-json evaluation\source_quality\sandbox\offline_fixture_quality_phase30.json --out-md evaluation\source_quality\sandbox\offline_fixture_quality_phase30.md`
- `venv\Scripts\python.exe scripts\render_network_probe_approval_package.py --probe-plan-json evaluation\source_quality\sandbox\preview_network_probe_plan_phase31.json --out-json evaluation\source_quality\sandbox\network_probe_approval_package_phase32.json --out-md evaluation\source_quality\sandbox\network_probe_approval_package_phase32.md`

## 安全红线

- 不直接全网爬取。
- 不执行 fetch / crawl / ingest。
- 不写正式 raw、triples、narratives、Chroma 或 Neo4j。
- 不自动批准 preview-only 网络探测。
- 未注册 candidate source 只能停留在 sandbox / report。
- ACTIVE_SOURCE 必须保持 zh_wikipedia。

## 下一步路线

- **A：继续离线增强** - 扩展 fixture pack、页面类型和人工审阅样本。
- **B：用户明确批准后做 NOAA 5 页 preview-only 网络探测** - 使用 Phase 34 命令卡，仍只写 sandbox 报告。
- **C：准备答辩材料** - 围绕三源 shadow 扩源和通用科学网站筛选闭环组织展示。

## GitHub / Commit 提示

分支和 commit 状态请在计划端或本地 git 命令中确认；本索引不联网查询。
