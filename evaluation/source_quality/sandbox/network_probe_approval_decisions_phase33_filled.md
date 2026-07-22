# Network Probe Approval Decisions

APPROVED DOES NOT EXECUTE NETWORK. 批准只表示未来可由人工手动运行 preview-only 命令；本报告仍是 not_run。

- approval_status: `approved_for_manual_preview`
- execution_status: `not_run`
- network: `False`
- formal_pipeline_write: `False`

| source_id | decision | status | approved_max_pages | execution_status | network | next_action |
|---|---|---|---:|---|---|---|
| data_portal_candidate | pending | pending_user_approval | 0 | not_run | False | wait for reviewer decision; do not run preview command |
| noaa_climate_candidate | approved_for_preview_probe | approved_for_manual_preview | 5 | not_run | False | manual operator may run preview-only command later; this report does not execute network |