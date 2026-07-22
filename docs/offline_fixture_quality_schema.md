# Offline Fixture Quality Schema

用于 Phase 30 的手工保存样本验证。它只服务于质量门报告，不代表已经联网抓取，也不会写入正式 `data/raw_json`、triples、Chroma 或 Neo4j。

最小 JSON 结构是一个数组：

```json
[
  {
    "url": "https://example.org/science/page",
    "title": "Science Page Title",
    "text": "Extracted page text, or omit this when html is provided.",
    "html": "<html>optional saved html</html>",
    "source_sample_type": "offline_fixture/manual_sample"
  }
]
```

字段说明：

| 字段 | 必需 | 说明 |
|---|---|---|
| `url` | 是 | 原页面 URL，用于 path/domain 质量信号；可以来自人工保存记录。 |
| `title` | 建议 | 页面标题，用于 fact/mission/news/gallery 等信号判断。 |
| `text` | `text`/`html` 二选一 | 人工保存或抽取出的正文。 |
| `html` | `text`/`html` 二选一 | 保存的页面片段；脚本会抽取文本、表格数等轻量指标。 |
| `source_sample_type` | 否 | 默认补为 `offline_fixture/manual_sample`。 |

运行示例：

```powershell
python scripts/report_offline_fixture_quality.py --manifest-dir configs/source_manifests/candidates --source noaa_climate_candidate --source data_portal_candidate --fixture-dir tests\fixtures\source_quality --out-json evaluation\source_quality\sandbox\offline_fixture_quality_phase30.json --out-md evaluation\source_quality\sandbox\offline_fixture_quality_phase30.md
```

报告会固定标记 `network=false`、`execution_status=not_run`、`formal_pipeline_write=false`。
