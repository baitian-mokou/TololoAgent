# 质量复查工作流

质量复查队列是给“有问题但不能自动改”的数据准备的待办清单。

这些数据通常来自来源冲突审计，例如中文维基和影子来源给出了不同的质量、半径、轨道对象，或者同一个数值缺少测量口径。系统会把它们整理到 `data/quality_review/quality_review_queue.json`，再把人的审批记录写到 `data/quality_review/quality_review_decisions.json`。用户不需要直接编辑 JSON，可以在 GUI 的“数据工程 / 质量复查”页面里逐条处理。

如果后续生成了外部来源复核结果，例如 `external_source_review_candidates.json`，它会作为同一问题的补充证据合并进原来的 review item，不会再生成一条重复审批行。也就是说，`source_conflict_v4_001` 和 `external_review_source_conflict_v4_001` 代表同一个真实问题时，用户只会看到一条待复查记录，详情里会同时显示 v4 审计证据和外部复核证据。

## 三种决定

- 通过：表示这条复查项可以进入下一步处理。通过时必须记录原因；GUI 会自动写入 `approved_in_gui` 这类说明。只有通过的项才会被 `apply_quality_patches.py` 读取。
- 暂缓：表示现在证据还不够，例如需要 NASA、ESA、论文或人工 ontology 设计。暂缓不会写正式 triples。
- 拒绝：表示这条候选不应修复，例如只是来源精度差异，或者当前候选判断不可靠。拒绝也不会写正式 triples。

`pending` 是默认状态。队列刚生成时全部都是 pending，不会被合并。

## 为什么默认只 dry-run

这些记录本质上都是质量风险项。即使系统能看出“可能哪里错了”，也不能自动替换正式事实值。

所以 `scripts/apply_quality_patches.py` 默认只生成预览报告：

```bash
python scripts/apply_quality_patches.py
```

预览报告写到 `evaluation/quality_review_apply_report.json`。它会告诉你哪些 approved 项准备怎么处理、哪些被跳过、是否会写正式数据。它不会写 Chroma，也不会写 Neo4j。

## 什么情况下才正式合并

正式合并低风险标注必须显式加 `--apply-metadata-only`：

```bash
python scripts/apply_quality_patches.py --apply-metadata-only
```

正式写入前，脚本会先把即将修改的 triples 文件备份到 `data/backups/quality_review/YYYYMMDD_HHMMSS/`，并生成 `rollback_manifest.json`。默认只允许安全的 metadata-only 变更写入本地 triples JSON，例如给半径记录补充 `measurement_kind` 或质量状态标注。这类变更不修改 `subject`、`relation`、`object`。

高风险 value change 即使已经通过，也只会生成 apply plan，不会直接改正式值。要允许改值必须再显式传入类似 `--allow-value-change` 的参数，并且应先由人确认来源证据和回滚方案。

GUI 的“正式合并”按钮也会二次确认，并且默认不启用高风险 value change。

## 常用命令

```bash
python scripts/build_quality_review_queue.py
python scripts/validate_quality_patch_decisions.py
python scripts/apply_quality_patches.py
python scripts/apply_quality_patches.py --apply-metadata-only
```

当前边界保持不变：`ACTIVE_SOURCE` 仍是 `zh_wikipedia`，`wikidata`、`nasa`、`esa` 仍是 disabled；质量复查不会启用默认 SourceRouter，不做默认多源融合，也不会自动写 Chroma 或 Neo4j。
