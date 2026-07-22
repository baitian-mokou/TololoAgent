# Offline Fixture Quality

本报告只验证手工保存或本地构造的 offline fixture；network=false，execution_status=not_run，不写正式数据管线。

| source_id | samples | accepted | review | exploratory | rejected | warnings |
|---|---:|---:|---:|---:|---:|---|
| missing_fixture_candidate | 0 | 0 | 0 | 0 | 0 | fixture not found: F:\知识表示与处理结课作业\TololoAgent\tests\fixtures\source_quality\does_not_exist.json |

## Samples

### missing_fixture_candidate

| title | url | triage | score | reasons |
|---|---|---|---:|---|

## Fixture Schema

每条样本建议包含 `url`、`title`、`text` 或 `html`，可选 `source_sample_type=offline_fixture/manual_sample`。这些样本只用于离线质量门验证，不能代表已经联网采集。
