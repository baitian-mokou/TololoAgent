# Source Conflict Resolution Simple Guide

这份文件是给人看的简化版。你不需要读懂原始 JSON。

当前有 8 条候选冲突。原则是：只批准低风险的“元数据标注”，不要批准事实值修改。

## 你现在应该做什么

只同意 1 条：

- `source_conflict_v4_002`：天王星 / HAS_RADIUS
  - 这条不是改半径数值。
  - 只是标注“这是哪一种半径口径”，例如平均半径、赤道半径、极半径。
  - 建议批准：`approve_measurement_kind_only`

暂缓 6 条：

- `source_conflict_v4_001`：天王星 / HAS_MASS
- `source_conflict_v4_003`：月球 / ORBITS
- `source_conflict_v4_004`：木卫二 / HAS_MASS
- `source_conflict_v4_005`：木卫四 / HAS_MASS
- `source_conflict_v4_007`：火卫一 / HAS_RADIUS
- `source_conflict_v4_008`：金星 / HAS_RADIUS

这些要么需要外部权威来源核验，要么需要 ontology 设计。现在不要改。

不处理 1 条：

- `source_conflict_v4_006`：火卫一 / HAS_MASS
  - 两个来源差异小于 1%。
  - 更像精度或来源粒度差异。
  - 建议本轮不做修复。

## 推荐决策

我已经生成一份推荐决策草案：

`data/quality_patches/source_conflict_resolution_decisions.recommended.json`

它只是草案，不会自动写入正式 triples、Chroma 或 Neo4j。

## 记住一句话

现在只批准“说明这个值是什么口径”，不要批准“把事实值改成另一个来源的值”。
