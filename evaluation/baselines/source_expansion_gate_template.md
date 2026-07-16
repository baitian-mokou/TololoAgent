# Source Expansion Gate Template

This template defines the minimum prerequisite boundary for the next formal source-expansion candidate.
The current project already has a passing NASA shadow audit; use this template for the next candidate only, not to activate NASA.

Prerequisites:

- the source has a dedicated query set under `evaluation/source_expansion/`
- the query set is auditable and contains structured, narrative, negative, and fallback coverage
- the manifest, descriptor, and schema version agree
- query-level exact accuracy meets the declared minimum
- source-filter failures, metadata-contract breaks, and inferred-boundary breaks remain at zero
- query-level explainability does not degrade
- fallback results do not mix with the active `zh_wikipedia` baseline

Gate requirement:

- the readiness gate must exit with code `0`
- the gate must be auditable from its JSON report

Non-goals:

- this file does not describe implementation steps
- this file does not change the single-source baseline
- this file does not authorize `ACTIVE_SOURCE` changes
