# 质量复查操作员指南

这套流程的目标是让人审批有争议数据，同时避免系统自动改掉正式事实值。

## 日常顺序

1. 生成队列：

```bash
python scripts/build_quality_review_queue.py
```

2. 打开 GUI，进入“数据工程 / 质量复查”。

3. 逐条看详情。每条记录是一件真实问题；外部来源复核会显示在同一条记录的证据里，不会另开重复审批行。

4. 做决定：

- 通过：只表示允许进入下一步处理。metadata-only 项可以 dry-run 或正式写本地 triples 元数据；高风险改值仍默认不写。
- 暂缓：证据不足，等待外部来源、ontology 设计或人工判断。
- 拒绝：候选不成立，或不需要修复。

5. 先 dry-run：

```bash
python scripts/apply_quality_patches.py --dry-run
```

6. 只有确认是安全 metadata-only 变更时，才考虑正式合并低风险标注：

```bash
python scripts/apply_quality_patches.py --apply-metadata-only
```

正式写入前会自动生成备份目录和 `rollback_manifest.json`。不要为普通复查任务使用 `--allow-value-change`。高风险 value change 需要单独的来源证据、回滚方案和明确批准。

## 安全验收

P10 的 smoke 脚本会在临时副本里模拟通过、暂缓、拒绝，不会改正式数据：

```bash
python scripts/smoke_quality_review_workflow.py
```

它检查：

- pending 不写入
- deferred 不写入
- rejected 不写入
- approved metadata-only 只生成 dry-run plan
- high risk value change 默认被阻止
- 不写 Chroma
- 不写 Neo4j
- `ACTIVE_SOURCE` 仍是 `zh_wikipedia`
- 最近一次 `run_all_gates.py` 报告仍是 passed

输出报告在 `evaluation/quality_review_workflow_smoke_report.json`。

正式合并或预演合并的 apply report 在 `evaluation/quality_review_apply_report.json`。如果发生正式 metadata-only 写入，报告里会记录 `backup_dir` 和 `rollback_manifest`。

## 不变边界

质量复查流程不启用默认 SourceRouter，不做默认多源融合，不接入 GUI 默认问答流程，不写 Chroma 或 Neo4j。它只管理复查队列、审批状态和本地预览报告。
