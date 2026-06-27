import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass

ROOT = Path(__file__).resolve().parents[1]
EVALUATION_DIR = ROOT / "evaluation"
DOCS_DIR = ROOT / "docs"
FINAL_JSON = EVALUATION_DIR / "final_acceptance_report.json"
FINAL_MD = DOCS_DIR / "final_acceptance_report.md"

COMMANDS = [
    ("python -m unittest discover tests", [sys.executable, "-m", "unittest", "discover", "tests"]),
    ("python scripts/run_single_source_retrieval_eval.py", [sys.executable, "scripts/run_single_source_retrieval_eval.py"]),
    (
        "python scripts/run_source_expansion_eval.py --source wikidata",
        [sys.executable, "scripts/run_source_expansion_eval.py", "--source", "wikidata"],
    ),
    (
        "python scripts/run_source_expansion_eval.py --source nasa",
        [sys.executable, "scripts/run_source_expansion_eval.py", "--source", "nasa"],
    ),
    ("python scripts/collect_eval_failures.py", [sys.executable, "scripts/collect_eval_failures.py"]),
    ("python scripts/smoke_default_source_boundary.py", [sys.executable, "scripts/smoke_default_source_boundary.py"]),
]

SECRET_PATTERN = re.compile(r"sk-[A-Za-z0-9_-]{8,}")


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {"missing": True, "path": str(path)}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"load_error": str(exc), "path": str(path)}


def _safe_text(text: str, limit: int = 4000) -> str:
    redacted = SECRET_PATTERN.sub("sk-***REDACTED***", text or "")
    return redacted[-limit:]


def _run_command(command: str, argv: List[str]) -> Dict[str, Any]:
    print(f"[gate] running: {command}", flush=True)
    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    started = time.perf_counter()
    completed = subprocess.run(
        argv,
        cwd=ROOT,
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    duration = round(time.perf_counter() - started, 3)
    passed = completed.returncode == 0
    print(f"[gate] {'PASS' if passed else 'FAIL'}: {command} ({duration}s)", flush=True)
    result = {
        "command": command,
        "exit_code": completed.returncode,
        "passed": passed,
        "duration_seconds": duration,
    }
    if not passed:
        result["output_tail"] = _safe_text(completed.stdout)
        print(result["output_tail"], flush=True)
    return result


def _summary_from_report(path: Path) -> Dict[str, Any]:
    report = _read_json(path)
    summary = report.get("summary", {})
    return {
        "path": str(path.relative_to(ROOT)),
        "total_queries": summary.get("total_queries"),
        "exact_pass_count": summary.get("exact_pass_count"),
        "exact_accuracy": summary.get("exact_accuracy"),
        "source_filter_failure_count": summary.get("source_filter_failure_count", 0),
        "metadata_contract_break_count": summary.get("metadata_contract_break_count", 0),
        "inferred_boundary_break_count": summary.get("inferred_boundary_break_count", 0),
        "query_explainability_degraded_count": summary.get("query_explainability_degraded_count", 0),
        "gates_passed": report.get("gates", {}).get("passed"),
    }


def _settings_key_hygiene() -> Dict[str, Any]:
    settings_path = ROOT / "settings.json"
    local_settings_path = ROOT / "settings.local.json"
    result = {
        "name": "settings_key_hygiene",
        "settings_json": str(settings_path.relative_to(ROOT)),
        "settings_local_json_exists": local_settings_path.exists(),
        "allowed_placeholder": "${TOLOLO_REMOTE_API_KEY}",
        "passed": True,
        "errors": [],
    }
    if settings_path.exists():
        text = settings_path.read_text(encoding="utf-8", errors="replace")
        if SECRET_PATTERN.search(text):
            result["passed"] = False
            result["errors"].append("settings.json contains a literal sk-* API key")
    return result


def _default_source_state() -> Dict[str, Any]:
    sys.path.insert(0, str(ROOT))
    import config  # pylint: disable=import-error,import-outside-toplevel

    registry = dict(config.SOURCE_REGISTRY)
    return {
        "active_source": config.ACTIVE_SOURCE,
        "registry": {name: registry.get(name) for name in ("zh_wikipedia", "wikidata", "nasa", "esa")},
        "zh_wikipedia_only_active": config.ACTIVE_SOURCE == "zh_wikipedia"
        and registry.get("zh_wikipedia") == "active"
        and all(registry.get(name) == "disabled" for name in ("wikidata", "nasa", "esa")),
    }


def _build_report(steps: List[Dict[str, Any]], key_hygiene: Dict[str, Any]) -> Dict[str, Any]:
    single = _summary_from_report(EVALUATION_DIR / "single_source_retrieval_report.json")
    wikidata = _summary_from_report(EVALUATION_DIR / "source_expansion" / "wikidata" / "wikidata_report.json")
    nasa = _summary_from_report(EVALUATION_DIR / "source_expansion" / "nasa" / "nasa_report.json")
    triage = _read_json(EVALUATION_DIR / "eval_failure_triage.json")
    smoke = _read_json(EVALUATION_DIR / "default_source_smoke_report.json")
    source_state = _default_source_state()

    report_summaries = {
        "single_source_retrieval": single,
        "wikidata_source_expansion": wikidata,
        "nasa_source_expansion": nasa,
    }
    aggregate_break_counts = {
        "source_filter_failure_count": sum(
            int(item.get("source_filter_failure_count") or 0) for item in report_summaries.values()
        ),
        "metadata_contract_break_count": sum(
            int(item.get("metadata_contract_break_count") or 0) for item in report_summaries.values()
        ),
        "inferred_boundary_break_count": sum(
            int(item.get("inferred_boundary_break_count") or 0) for item in report_summaries.values()
        ),
        "query_explainability_degraded_count": sum(
            int(item.get("query_explainability_degraded_count") or 0) for item in report_summaries.values()
        ),
    }
    acceptance_passed = (
        all(step["passed"] for step in steps)
        and key_hygiene["passed"]
        and triage.get("failure_count") == 0
        and smoke.get("passed") is True
        and source_state["zh_wikipedia_only_active"]
        and all(value == 0 for value in aggregate_break_counts.values())
    )
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "passed": acceptance_passed,
        "steps": steps,
        "reports": report_summaries,
        "failure_count": triage.get("failure_count"),
        "aggregate_break_counts": aggregate_break_counts,
        "default_source": source_state,
        "smoke_report": {
            "path": "evaluation/default_source_smoke_report.json",
            "passed": smoke.get("passed"),
            "errors": smoke.get("errors", []),
        },
        "settings_key_hygiene": key_hygiene,
    }


def _fmt_accuracy(value: Optional[float]) -> str:
    if value is None:
        return "n/a"
    return f"{value:.4f}".rstrip("0").rstrip(".")


def _write_markdown(report: Dict[str, Any]) -> None:
    reports = report["reports"]
    breaks = report["aggregate_break_counts"]
    source = report["default_source"]
    lines = [
        "# Final Acceptance Report",
        "",
        f"Generated at: `{report['generated_at']}`",
        "",
        f"Overall status: `{'PASS' if report['passed'] else 'FAIL'}`",
        "",
        "## Gate Steps",
        "",
        "| command | exit_code | passed | duration_seconds |",
        "| --- | ---: | --- | ---: |",
    ]
    for step in report["steps"]:
        lines.append(
            f"| `{step['command']}` | {step['exit_code']} | {str(step['passed']).lower()} | {step['duration_seconds']} |"
        )
    lines.extend(
        [
            "",
            "## Accuracy",
            "",
            "| report | exact_accuracy | pass count | break counts |",
            "| --- | ---: | ---: | --- |",
        ]
    )
    for name, item in reports.items():
        break_text = (
            f"source_filter={item.get('source_filter_failure_count', 0)}, "
            f"metadata={item.get('metadata_contract_break_count', 0)}, "
            f"inferred={item.get('inferred_boundary_break_count', 0)}, "
            f"explainability={item.get('query_explainability_degraded_count', 0)}"
        )
        lines.append(
            f"| `{name}` | {_fmt_accuracy(item.get('exact_accuracy'))} | "
            f"{item.get('exact_pass_count')}/{item.get('total_queries')} | {break_text} |"
        )
    lines.extend(
        [
            "",
            "## Final Counters",
            "",
            f"- `failure_count = {report.get('failure_count')}`",
            f"- `source_filter_failure_count = {breaks['source_filter_failure_count']}`",
            f"- `metadata_contract_break_count = {breaks['metadata_contract_break_count']}`",
            f"- `inferred_boundary_break_count = {breaks['inferred_boundary_break_count']}`",
            f"- `query_explainability_degraded_count = {breaks['query_explainability_degraded_count']}`",
            "",
            "## Default Source State",
            "",
            f"- `ACTIVE_SOURCE = {source['active_source']}`",
            f"- `SOURCE_REGISTRY.zh_wikipedia = {source['registry'].get('zh_wikipedia')}`",
            f"- `SOURCE_REGISTRY.wikidata = {source['registry'].get('wikidata')}`",
            f"- `SOURCE_REGISTRY.nasa = {source['registry'].get('nasa')}`",
            f"- `SOURCE_REGISTRY.esa = {source['registry'].get('esa')}`",
            f"- `default_source_smoke_passed = {str(report['smoke_report']['passed']).lower()}`",
            "",
            "## Key Hygiene",
            "",
            f"- `settings.json` literal `sk-*` key check: `{str(report['settings_key_hygiene']['passed']).lower()}`",
            "- `settings.local.json` is not read or printed by this report.",
        ]
    )
    FINAL_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    EVALUATION_DIR.mkdir(parents=True, exist_ok=True)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    steps = [_run_command(command, argv) for command, argv in COMMANDS]
    key_hygiene = _settings_key_hygiene()
    if not key_hygiene["passed"]:
        print("[gate] FAIL: settings_key_hygiene", flush=True)
    else:
        print("[gate] PASS: settings_key_hygiene", flush=True)

    report = _build_report(steps, key_hygiene)
    FINAL_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _write_markdown(report)

    print(
        json.dumps(
            {
                "passed": report["passed"],
                "final_acceptance_report_json": str(FINAL_JSON),
                "final_acceptance_report_md": str(FINAL_MD),
                "failure_count": report["failure_count"],
                "aggregate_break_counts": report["aggregate_break_counts"],
                "active_source": report["default_source"]["active_source"],
            },
            ensure_ascii=False,
            indent=2,
        ),
        flush=True,
    )
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
