from __future__ import annotations

import argparse
from collections import Counter
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.preview_source_frontier import load_manifest_from_path, manifest_validation_report, quality_context_from_manifest
from scripts.sandbox_manifest_candidates import REGISTERED_SOURCES, SANDBOX_DIR, is_sandbox_path, write_json
from scripts.score_candidate_pages import candidates_from_payload
from src.source_quality.page_quality import score_page


DEFAULT_JSON = SANDBOX_DIR / "offline_fixture_quality.json"
DEFAULT_MD = SANDBOX_DIR / "offline_fixture_quality.md"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def manifest_path(manifest_dir: Path, source_id: str) -> Path:
    return Path(manifest_dir) / f"{source_id}.json"


def fixture_path(manifest: Dict[str, Any], fixture_dir: Path, source_id: str) -> Path:
    value = str(manifest.get("offline_fixture_candidates") or manifest.get("fixture_candidates") or "").strip()
    if value:
        path = Path(value)
        return path if path.is_absolute() else ROOT / path
    return Path(fixture_dir) / f"{source_id}_candidates.json"


def sample_record(candidate: Dict[str, Any], result: Dict[str, Any], index: int) -> Dict[str, Any]:
    return {
        "index": index,
        "source_sample_type": str(candidate.get("source_sample_type") or "offline_fixture/manual_sample"),
        "url": candidate.get("url") or candidate.get("source_url") or "",
        "title": candidate.get("title") or candidate.get("source_title") or "",
        "score": result["score"],
        "triage": result["triage"],
        "labels": result["labels"],
        "reasons": result["reasons"][:5],
        "metrics": result["metrics"],
    }


def source_report(manifest_dir: Path, fixture_dir: Path, source_id: str) -> Dict[str, Any]:
    path = manifest_path(manifest_dir, source_id)
    warnings: List[str] = []
    if not path.exists():
        return {
            "source_id": source_id,
            "registered": False,
            "network": False,
            "execution_status": "not_run",
            "formal_pipeline_write": False,
            "offline_fixture_only": True,
            "sample_count": 0,
            "triage_counts": {},
            "top_reasons": {},
            "warnings": [f"manifest not found: {path}"],
            "samples": [],
        }
    manifest = load_manifest_from_path(path)
    validation = manifest_validation_report(manifest, path)
    source_id = str(manifest.get("source_name") or source_id)
    fixture = fixture_path(manifest, fixture_dir, source_id)
    if not fixture.exists():
        warnings.append(f"fixture not found: {fixture}")
        candidates: List[Dict[str, Any]] = []
    else:
        candidates = candidates_from_payload(read_json(fixture), source_id)
    context = quality_context_from_manifest(manifest)
    triage_counts: Counter[str] = Counter()
    reason_counts: Counter[str] = Counter()
    samples: List[Dict[str, Any]] = []
    for index, candidate in enumerate(candidates, start=1):
        scored = dict(candidate)
        scored.setdefault("source_name", source_id)
        scored.setdefault("source_sample_type", "offline_fixture/manual_sample")
        result = score_page(scored, quality_context=context)
        triage_counts[result["triage"]] += 1
        reason_counts.update(result.get("reasons", []))
        samples.append(sample_record(scored, result, index))
    return {
        "source_id": source_id,
        "source_mode": manifest.get("source_mode", ""),
        "registered": source_id in REGISTERED_SOURCES,
        "network": False,
        "execution_status": "not_run",
        "formal_pipeline_write": False,
        "offline_fixture_only": True,
        "manifest_path": str(path),
        "fixture_path": str(fixture),
        "manifest_validation": validation,
        "sample_count": len(samples),
        "triage_counts": dict(sorted(triage_counts.items())),
        "top_reasons": dict(reason_counts.most_common(10)),
        "warnings": warnings,
        "samples": samples,
    }


def build_report(manifest_dir: Path, fixture_dir: Path, sources: Sequence[str]) -> Dict[str, Any]:
    items = [source_report(manifest_dir, fixture_dir, source_id) for source_id in sources]
    triage_counts: Counter[str] = Counter()
    for item in items:
        triage_counts.update(item.get("triage_counts", {}))
    return {
        "mode": "offline_fixture_quality_report",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "manifest_dir": str(manifest_dir),
        "fixture_dir": str(fixture_dir),
        "network": False,
        "execution_status": "not_run",
        "formal_pipeline_write": False,
        "summary": {
            "sources": len(items),
            "total_samples": sum(int(item.get("sample_count", 0) or 0) for item in items),
            "triage_counts": dict(sorted(triage_counts.items())),
        },
        "items": items,
    }


def markdown(report: Dict[str, Any]) -> str:
    lines = [
        "# Offline Fixture Quality",
        "",
        "本报告只验证手工保存或本地构造的 offline fixture；network=false，execution_status=not_run，不写正式数据管线。",
        "",
        "| source_id | samples | accepted | review | exploratory | rejected | warnings |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for item in report["items"]:
        counts = item.get("triage_counts", {})
        lines.append(
            "| {source_id} | {sample_count} | {accepted} | {review} | {exploratory} | {rejected} | {warnings} |".format(
                source_id=item.get("source_id", ""),
                sample_count=item.get("sample_count", 0),
                accepted=counts.get("accepted", 0),
                review=counts.get("review_needed", 0),
                exploratory=counts.get("exploratory", 0),
                rejected=counts.get("rejected", 0),
                warnings="; ".join(item.get("warnings", [])),
            )
        )
    lines.extend(["", "## Samples", ""])
    for item in report["items"]:
        lines.extend([
            f"### {item.get('source_id', '')}",
            "",
            "| title | url | triage | score | reasons |",
            "|---|---|---|---:|---|",
        ])
        for sample in item.get("samples", []):
            lines.append(
                "| {title} | {url} | {triage} | {score} | {reasons} |".format(
                    title=str(sample.get("title", "")).replace("|", "\\|"),
                    url=str(sample.get("url", "")).replace("|", "\\|"),
                    triage=sample.get("triage", ""),
                    score=sample.get("score", ""),
                    reasons=", ".join(sample.get("reasons", [])[:3]).replace("|", "\\|"),
                )
            )
        lines.append("")
    lines.extend([
        "## Fixture Schema",
        "",
        "每条样本建议包含 `url`、`title`、`text` 或 `html`，可选 `source_sample_type=offline_fixture/manual_sample`。这些样本只用于离线质量门验证，不能代表已经联网采集。",
        "",
    ])
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Report quality for local offline fixture samples.")
    parser.add_argument("--manifest-dir", default=str(ROOT / "configs" / "source_manifests" / "candidates"))
    parser.add_argument("--source", action="append", default=[])
    parser.add_argument("--fixture-dir", default=str(ROOT / "tests" / "fixtures" / "source_quality"))
    parser.add_argument("--out-json", default=str(DEFAULT_JSON))
    parser.add_argument("--out-md", default=str(DEFAULT_MD))
    args = parser.parse_args(argv)

    out_json = Path(args.out_json)
    out_md = Path(args.out_md)
    for path in (out_json, out_md):
        if not is_sandbox_path(path):
            print("outputs must stay under evaluation/source_quality/sandbox", file=sys.stderr)
            return 2
    sources = args.source or ["noaa_climate_candidate", "data_portal_candidate"]
    report = build_report(Path(args.manifest_dir), Path(args.fixture_dir), sources)
    write_json(out_json, report)
    write_text(out_md, markdown(report))
    print(f"sources={report['summary']['sources']} total_samples={report['summary']['total_samples']} triage={report['summary']['triage_counts']} execution_status=not_run")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
