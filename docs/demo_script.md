# Demo Script

This script is for the project demo or defense. It describes what to show and, just as importantly, what not to claim.

## Start The GUI

From the project root:

```bash
python main.py
```

If the local environment uses the project virtual environment, run the same command with that interpreter. Keep the demo on the default settings unless you are explicitly showing a source-filter experiment.

## Explain The Default Single-Source Boundary

Start by stating:

- `ACTIVE_SOURCE = zh_wikipedia`.
- `zh_wikipedia` is the only active source.
- `wikidata`, `nasa`, and `esa` are registered but disabled.
- Default GUI and default `LLMAgent()` retrieval do not perform cross-source fusion.

Recommended default-path questions:

- `火卫一绕谁公转`
- `为什么太阳会发光`
- `火星大气成分`

When answering, point out that default results should come from the `zh_wikipedia` baseline path, not from Wikidata or NASA.

## Show Wikidata And NASA As Shadow Sources

Explain that Wikidata and NASA are not active sources. They are audited shadow namespaces with their own `source_filter`, `schema_version`, metadata contract, and readiness gates.

Useful talking points:

- Wikidata is the formal second-source shadow candidate.
- Wikidata currently passes `24/24` source-expansion queries, but `cutover_ready=false`.
- NASA currently passes `22/22` source-expansion queries, but remains shadow-only.
- ESA is smoke-only and does not enter the default path.

## Run One-Key Acceptance

From the project root:

```bash
python scripts/run_all_gates.py
```

This command runs:

- `python -m unittest discover tests`
- `python scripts/run_single_source_retrieval_eval.py`
- `python scripts/run_source_expansion_eval.py --source wikidata`
- `python scripts/run_source_expansion_eval.py --source nasa`
- `python scripts/collect_eval_failures.py`
- `python scripts/smoke_default_source_boundary.py`

Then show:

- `evaluation/final_acceptance_report.json`
- `docs/final_acceptance_report.md`

The key acceptance numbers to cite are:

- `single_source_retrieval exact_accuracy = 1.0`
- `wikidata source expansion exact_accuracy = 1.0`
- `nasa source expansion exact_accuracy = 1.0`
- `failure_count = 0`
- all source boundary and metadata break counts are `0`
- default source remains `zh_wikipedia`

## Do Not Claim

- Do not claim multi-source fusion is enabled.
- Do not claim live fetch is implemented.
- Do not claim Wikidata, NASA, or ESA are active sources.
- Do not claim NASA passing its gate authorizes cross-source answers.
- Do not claim SourceRouter is enabled; it is design-only and default-off.
