from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Callable, Dict, List, Sequence, Tuple


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import ACTIVE_SOURCE, SOURCE_REGISTRY
from scripts.ingest_manifest_frontier import fetch_url, payload_for_record, quality_fields_for_payload
from scripts.materialize_manifest_raw_records import clean_text, convert_raw_payload, safe_name
from scripts.preview_nasa_text_relation_extraction import extract_text_relations, normalize_title, validate_triples
from scripts.select_deduped_frontier_candidates import canonical_url, normalized_title
from scripts.build_nasa_limited_shadow_package import approval_payload, formal_shadow_plan, render_review_sample, utc_now


SOURCE_ID = "nasa"
Fetcher = Callable[[str, int], Dict[str, str]]


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def under_four_source_expansion(path: Path) -> bool:
    parts = list(path.resolve().parts)
    return any(parts[i : i + 2] == ["evaluation", "four_source_expansion"] for i in range(len(parts) - 1))


def output_allowed(path: Path, *, allow_docs: bool = False) -> bool:
    parts = list(path.resolve().parts)
    if allow_docs and "docs" in parts:
        return True
    return under_four_source_expansion(path)


def source_candidates(phase40: Dict[str, Any]) -> List[Dict[str, Any]]:
    for source in phase40.get("sources", []) if isinstance(phase40.get("sources"), list) else []:
        if source.get("source_id") == SOURCE_ID:
            candidates = source.get("selected_candidates", [])
            return candidates if isinstance(candidates, list) else []
    return []


def raw_candidates(raw_root: Path) -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []
    for path in sorted(raw_root.glob("*.json")) if raw_root.exists() else []:
        payload = read_json(path)
        if not isinstance(payload, dict):
            continue
        url = str(payload.get("source_url") or payload.get("url") or "").strip()
        title = str(payload.get("title") or path.stem).strip()
        if url or title:
            candidates.append({"title": title, "url": url, "source_reason": "existing_raw", "raw_path": str(path)})
    return candidates


def package_fingerprints(package_dir: Path) -> Tuple[set[str], set[str], set[str]]:
    urls: set[str] = set()
    titles: set[str] = set()
    subjects: set[str] = set()
    for filename in ("triples_preview.json", "narratives_preview.json"):
        payload = read_json(package_dir / filename)
        for item in payload if isinstance(payload, list) else []:
            url = canonical_url(str(item.get("source_url") or item.get("url") or item.get("object") or ""))
            title = normalized_title(str(item.get("source_title") or item.get("page_title") or item.get("title") or ""))
            subject = normalized_title(str(item.get("subject") or ""))
            if url:
                urls.add(url)
            if title:
                titles.add(title)
            if subject:
                subjects.add(subject)
    return urls, titles, subjects


def candidate_key(candidate: Dict[str, Any]) -> Tuple[str, str]:
    return canonical_url(str(candidate.get("url") or "")), normalized_title(str(candidate.get("title") or ""))


def combined_package_fingerprints(package_dirs: Sequence[Path]) -> Tuple[set[str], set[str], set[str]]:
    urls: set[str] = set()
    titles: set[str] = set()
    subjects: set[str] = set()
    for package_dir in package_dirs:
        package_urls, package_titles, package_subjects = package_fingerprints(package_dir)
        urls.update(package_urls)
        titles.update(package_titles)
        subjects.update(package_subjects)
    return urls, titles, subjects


def report_status_fingerprints(report_paths: Sequence[Path]) -> Tuple[set[str], set[str], set[str]]:
    urls: set[str] = set()
    titles: set[str] = set()
    subjects: set[str] = set()
    for path in report_paths:
        report = read_json(path)
        for status in report.get("candidate_statuses", []) if isinstance(report, dict) else []:
            if status.get("status") not in {"rejected", "failed", "duplicate_skipped"}:
                continue
            url = canonical_url(str(status.get("url") or ""))
            title = normalized_title(str(status.get("title") or ""))
            if url:
                urls.add(url)
            if title:
                titles.add(title)
                subjects.add(title)
    return urls, titles, subjects


def select_second_batch(candidates: Sequence[Dict[str, Any]], package_dir: Path, target_count: int) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    return select_batch(candidates, [package_dir], target_count, "phase40_remaining_after_phase45_exclusion")


def select_batch(
    candidates: Sequence[Dict[str, Any]],
    exclude_package_dirs: Sequence[Path],
    exclude_report_paths: Sequence[Path],
    target_count: int,
    selection_reason: str,
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    packaged_urls, packaged_titles, packaged_subjects = combined_package_fingerprints(exclude_package_dirs)
    report_urls, report_titles, report_subjects = report_status_fingerprints(exclude_report_paths)
    packaged_urls.update(report_urls)
    packaged_titles.update(report_titles)
    packaged_subjects.update(report_subjects)
    selected: List[Dict[str, Any]] = []
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    excluded_packaged = duplicate = 0
    for candidate in candidates:
        url_key, title_key = candidate_key(candidate)
        if url_key in packaged_urls or title_key in packaged_titles or title_key in packaged_subjects:
            excluded_packaged += 1
            continue
        if (url_key and url_key in seen_urls) or (title_key and title_key in seen_titles):
            duplicate += 1
            continue
        if url_key:
            seen_urls.add(url_key)
        if title_key:
            seen_titles.add(title_key)
        selected.append({**candidate, "selection_reason": selection_reason})
        if len(selected) >= target_count:
            break
    return selected, {"excluded_phase45": excluded_packaged, "duplicate_candidates": duplicate}


def overlaps_phase45_item(item: Dict[str, Any], packaged_titles: set[str], packaged_subjects: set[str]) -> bool:
    title_key = normalized_title(str(item.get("title") or ""))
    if title_key and (title_key in packaged_titles or title_key in packaged_subjects):
        return True
    for triple in item.get("triples", []) if isinstance(item.get("triples"), list) else []:
        subject_key = normalized_title(str(triple.get("subject") or ""))
        source_title_key = normalized_title(str(triple.get("source_title") or ""))
        if subject_key and (subject_key in packaged_titles or subject_key in packaged_subjects):
            return True
        if source_title_key and (source_title_key in packaged_titles or source_title_key in packaged_subjects):
            return True
    return False


def record_for_candidate(candidate: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "kind": "url",
        "url": str(candidate.get("url") or "").strip(),
        "depth": int(candidate.get("depth", 0) or 0),
        "reason": candidate.get("source_reason") or candidate.get("selection_reason") or "phase52_second_batch",
    }


def raw_by_url(raw_root: Path) -> Dict[str, Path]:
    records: Dict[str, Path] = {}
    for path in sorted(raw_root.glob("*.json")) if raw_root.exists() else []:
        payload = read_json(path)
        if not isinstance(payload, dict):
            continue
        url = canonical_url(str(payload.get("source_url") or payload.get("url") or ""))
        if url:
            records.setdefault(url, path)
    return records


def load_or_fetch_raw(candidate: Dict[str, Any], raw_lookup: Dict[str, Path], fetcher: Fetcher) -> Tuple[Dict[str, Any], str, bool]:
    url_key = canonical_url(str(candidate.get("url") or ""))
    if url_key in raw_lookup:
        return read_json(raw_lookup[url_key]), str(raw_lookup[url_key]), False
    payload = payload_for_record(SOURCE_ID, record_for_candidate(candidate), fetcher)
    return payload, "fetched_selected_candidate", True


def narrative_preview(raw: Dict[str, Any], candidate: Dict[str, Any]) -> Dict[str, Any]:
    converted = convert_raw_payload(SOURCE_ID, raw)
    title = str(converted.get("title") or raw.get("title") or candidate.get("title") or "NASA item")
    return {
        "trial": True,
        "phase": "Phase 52",
        "source_id": SOURCE_ID,
        "source_url": converted.get("source_url") or raw.get("source_url") or raw.get("url") or candidate.get("url", ""),
        "title": title,
        "quality_triage": raw.get("quality_triage"),
        "quality_score": raw.get("quality_score"),
        "triples": converted.get("triples", []),
        "narratives": converted.get("narratives", []),
        "formal_write": False,
    }


def sample_items(items: Sequence[Dict[str, Any]], count: int = 5) -> List[Dict[str, Any]]:
    return [
        {
            "title": item.get("title", ""),
            "url": item.get("source_url", ""),
            "source_url": item.get("source_url", ""),
            "triples": item.get("triples", [])[:4],
            "narratives": item.get("narratives", [])[:1],
            "candidate_reason": item.get("candidate_reason", ""),
            "warnings": item.get("warnings", []),
        }
        for item in list(items)[:count]
    ]


def build_package_files(out_dir: Path, items: Sequence[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    triples: List[Dict[str, Any]] = []
    narratives: List[Dict[str, Any]] = []
    for index, item in enumerate(items, start=1):
        name = f"{index:02d}_{safe_name(str(item.get('title') or 'item'))}"
        item_triples = [
            {**triple, "source_id": SOURCE_ID, "source_url": item.get("source_url", ""), "source_title": item.get("title", ""), "package_trial": True}
            for triple in item.get("triples", [])
        ]
        item_narratives = [
            {**narrative, "source_id": SOURCE_ID, "source_url": item.get("source_url", ""), "source_title": item.get("title", ""), "package_trial": True}
            for narrative in item.get("narratives", [])
        ]
        triples.extend(item_triples)
        narratives.extend(item_narratives)
        write_json(out_dir / "triples_preview_by_item" / f"{name}.json", item_triples)
        write_json(out_dir / "narratives_preview_by_item" / f"{name}.json", item_narratives)
    write_json(out_dir / "triples_preview.json", triples)
    write_json(out_dir / "narratives_preview.json", narratives)
    return triples, narratives


def quality_ok(payload: Dict[str, Any]) -> bool:
    triage = str(payload.get("quality_triage") or "")
    return triage in {"accepted", ""}


def process_candidate(
    *,
    candidate: Dict[str, Any],
    raw_lookup: Dict[str, Path],
    raw_cache_dir: Path,
    packaged_titles: set[str],
    packaged_subjects: set[str],
    fetcher: Fetcher,
) -> Tuple[Dict[str, Any] | None, Dict[str, Any]]:
    url = str(candidate.get("url") or "")
    try:
        raw, raw_origin, network = load_or_fetch_raw(candidate, raw_lookup, fetcher)
        if not isinstance(raw, dict) or not raw:
            return None, {"url": url, "status": "failed", "reason": "raw_json_missing_or_invalid", "network_attempted": network}
        raw.update(quality_fields_for_payload(raw))
        title = str(raw.get("title") or candidate.get("title") or url)
        if not quality_ok(raw):
            return None, {"url": url, "title": title, "status": "rejected", "reason": f"quality_{raw.get('quality_triage')}", "network_attempted": network}
        raw_cache_path = raw_cache_dir / f"{safe_name(title)}.json"
        trial = narrative_preview(raw, candidate)
        relation_input = {**trial, "raw_path": str(raw_cache_path)}
        triples_raw, narrative_count = extract_text_relations(relation_input)
        accepted, warnings = validate_triples(triples_raw, str(trial.get("source_url") or ""))
        overlap_probe = {"title": normalize_title(title), "triples": accepted}
        if overlaps_phase45_item(overlap_probe, packaged_titles, packaged_subjects):
            return None, {
                "url": url,
                "title": normalize_title(title),
                "status": "duplicate_skipped",
                "reason": "phase45_title_or_subject_overlap",
                "network_attempted": network,
            }
        write_json(raw_cache_path, raw)
        if not accepted or not trial.get("narratives"):
            return None, {
                "url": url,
                "title": title,
                "status": "rejected",
                "reason": "missing_triples_or_narratives",
                "accepted_triples": len(accepted),
                "narratives": len(trial.get("narratives") or []),
                "network_attempted": network,
            }
        item = {
            "source_id": SOURCE_ID,
            "title": normalize_title(title),
            "source_url": trial.get("source_url") or url,
            "raw_cache_path": str(raw_cache_path),
            "raw_origin": raw_origin,
            "candidate_reason": candidate.get("selection_reason") or candidate.get("source_reason") or "",
            "quality_triage": raw.get("quality_triage"),
            "quality_score": raw.get("quality_score"),
            "triples": accepted,
            "narratives": trial.get("narratives", []),
            "warnings": warnings,
            "narratives_used": narrative_count,
            "network_attempted": network,
        }
        return item, {"url": url, "title": title, "status": "packaged", "network_attempted": network}
    except Exception as exc:
        return None, {"url": url, "title": candidate.get("title", ""), "status": "failed", "reason": type(exc).__name__, "network_attempted": True}


def build_second_package(
    *,
    phase40_json: Path,
    phase45_package_dir: Path,
    out_dir: Path,
    approval_template: Path,
    target_count: int,
    fetcher: Fetcher = fetch_url,
    raw_root: Path = ROOT / "data" / "raw_json" / SOURCE_ID,
    include_raw_candidates: bool = False,
    exclude_report_paths: Sequence[Path] = (),
) -> Dict[str, Any]:
    return build_nasa_package(
        phase40_json=phase40_json,
        exclude_package_dirs=[phase45_package_dir],
        out_dir=out_dir,
        approval_template=approval_template,
        target_count=target_count,
        phase_label="Phase 52",
        package_name="nasa_second_shadow_package_phase52",
        mode="nasa_second_shadow_package_preparation",
        fetcher=fetcher,
        raw_root=raw_root,
        include_raw_candidates=include_raw_candidates,
        exclude_report_paths=exclude_report_paths,
    )


def build_nasa_package(
    *,
    phase40_json: Path,
    exclude_package_dirs: Sequence[Path],
    out_dir: Path,
    approval_template: Path,
    target_count: int,
    phase_label: str,
    package_name: str,
    mode: str,
    fetcher: Fetcher = fetch_url,
    raw_root: Path = ROOT / "data" / "raw_json" / SOURCE_ID,
    include_raw_candidates: bool = False,
    exclude_report_paths: Sequence[Path] = (),
) -> Dict[str, Any]:
    reset_output_dir(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    phase40 = read_json(phase40_json)
    candidate_pool = source_candidates(phase40 if isinstance(phase40, dict) else {})
    if include_raw_candidates:
        candidate_pool += raw_candidates(raw_root)
    candidates, selection_stats = select_batch(
        candidate_pool,
        exclude_package_dirs,
        exclude_report_paths,
        target_count,
        f"{phase_label.lower().replace(' ', '_')}_remaining_after_prior_package_exclusion",
    )
    _packaged_urls, packaged_titles, packaged_subjects = combined_package_fingerprints(exclude_package_dirs)
    raw_lookup = raw_by_url(raw_root)
    raw_cache_dir = out_dir / "raw_preview_by_item"
    packaged: List[Dict[str, Any]] = []
    statuses: List[Dict[str, Any]] = []
    for candidate in candidates:
        item, status = process_candidate(
            candidate=candidate,
            raw_lookup=raw_lookup,
            raw_cache_dir=raw_cache_dir,
            packaged_titles=packaged_titles,
            packaged_subjects=packaged_subjects,
            fetcher=fetcher,
        )
        statuses.append(status)
        if item:
            packaged.append(item)
    triples, narratives = build_package_files(out_dir, packaged)
    samples = sample_items(packaged)
    write_json(out_dir / "review_sample.json", samples)
    write_text(out_dir / "review_sample.md", render_review_sample(samples))
    approval = approval_payload(len(packaged))
    write_json(approval_template, approval)
    manifest = {
        "package": package_name,
        "source_id": SOURCE_ID,
        "generated_at": utc_now(),
        "target_count": target_count,
        "selected_count": len(candidates),
        "items": len(packaged),
        "triples": len(triples),
        "narratives": len(narratives),
        "formal_write": False,
        "approval_status": "pending",
        "files": {
            "triples_preview": str(out_dir / "triples_preview.json"),
            "narratives_preview": str(out_dir / "narratives_preview.json"),
            "review_sample": str(out_dir / "review_sample.md"),
        },
    }
    write_json(out_dir / "package_manifest.json", manifest)
    relation_counts = Counter(triple.get("predicate", "") for triple in triples)
    type_distribution = Counter(
        triple.get("object", "") for triple in triples if triple.get("predicate") in {"INSTANCE_OF", "HAS_TOPIC"}
    )
    failed = sum(1 for status in statuses if status.get("status") == "failed")
    rejected = sum(1 for status in statuses if status.get("status") == "rejected")
    post_fetch_phase45_excluded = sum(1 for status in statuses if status.get("reason") == "phase45_title_or_subject_overlap")
    network_attempted = any(bool(status.get("network_attempted")) for status in statuses)
    shortage = max(0, target_count - len(packaged))
    return {
        "phase": phase_label,
        "mode": mode,
        "generated_at": manifest["generated_at"],
        "source_id": SOURCE_ID,
        "target_count": target_count,
        "selected_count": len(candidates),
        "packaged_items": len(packaged),
        "triples": len(triples),
        "narratives": len(narratives),
        "failed": failed,
        "rejected": rejected,
        "duplicates_excluded": selection_stats["duplicate_candidates"],
        "prior_items_excluded": selection_stats["excluded_phase45"] + post_fetch_phase45_excluded,
        "prior_items_excluded_before_fetch": selection_stats["excluded_phase45"],
        "prior_items_excluded_after_fetch": post_fetch_phase45_excluded,
        "phase45_items_excluded": selection_stats["excluded_phase45"] + post_fetch_phase45_excluded,
        "phase45_items_excluded_before_fetch": selection_stats["excluded_phase45"],
        "phase45_items_excluded_after_fetch": post_fetch_phase45_excluded,
        "exclude_package_dirs": [str(path) for path in exclude_package_dirs],
        "shortage": shortage,
        "shortage_reason": "" if shortage == 0 else "remaining Phase 40 candidates were fewer than target or failed quality/fetch gates",
        "candidate_statuses": statuses,
        "relations_count": dict(sorted(relation_counts.items())),
        "type_distribution": dict(sorted(type_distribution.items())),
        "sample_items": samples,
        "approval_status": "pending",
        "approval_template": str(approval_template),
        "out_dir": str(out_dir),
        "formal_shadow_write_plan": formal_shadow_plan(len(packaged), len(triples), len(narratives)),
        "network_attempted": network_attempted,
        "formal_triples_write": False,
        "formal_narratives_write": False,
        "chroma_write": False,
        "neo4j_write": False,
        "active_source": ACTIVE_SOURCE,
        "registry": {source: SOURCE_REGISTRY.get(source, "unknown") for source in ("zh_wikipedia", "nasa", "esa", "wikidata")},
        "active_source_unchanged": ACTIVE_SOURCE == "zh_wikipedia",
        "recommended_next_action": "review_package_before_any_shadow_apply" if packaged else "refresh_nasa_frontier_before_next_package",
    }


def reset_output_dir(out_dir: Path) -> None:
    if not under_four_source_expansion(out_dir):
        raise ValueError("out_dir must stay under evaluation/four_source_expansion")
    if out_dir.exists():
        shutil.rmtree(out_dir)


def render_markdown(report: Dict[str, Any]) -> str:
    lines = [
        f"# NASA shadow package preparation ({report['phase']})",
        "",
        "This prepares a NASA shadow package from remaining candidates. It does not approve or apply the package.",
        "",
        f"- target_count: `{report['target_count']}`",
        f"- selected_count: `{report['selected_count']}`",
        f"- packaged_items: `{report['packaged_items']}`",
        f"- triples: `{report['triples']}`",
        f"- narratives: `{report['narratives']}`",
        f"- prior_items_excluded: `{report.get('prior_items_excluded', report.get('phase45_items_excluded'))}`",
        f"- rejected: `{report['rejected']}`",
        f"- failed: `{report['failed']}`",
        f"- shortage: `{report['shortage']}`",
        f"- approval_status: `{report['approval_status']}`",
        f"- network_attempted: `{report['network_attempted']}`",
        "",
        "## Relation Counts",
        "",
    ]
    for relation, count in report["relations_count"].items():
        lines.append(f"- `{relation}`: {count}")
    lines.extend(["", "## Candidate Statuses", "", "| status | title | url | reason |", "| --- | --- | --- | --- |"])
    for status in report["candidate_statuses"]:
        lines.append(f"| `{status.get('status')}` | {status.get('title', '')} | `{status.get('url', '')}` | `{status.get('reason', '')}` |")
    lines.extend(["", "## Safety", ""])
    for key in ("formal_triples_write", "formal_narratives_write", "chroma_write", "neo4j_write", "active_source_unchanged"):
        lines.append(f"- {key}: `{report[key]}`")
    lines.append("")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Prepare NASA second shadow package under evaluation only.")
    parser.add_argument("--phase40-json", default=str(ROOT / "evaluation" / "four_source_expansion" / "deduped_frontier_candidates_phase40.json"))
    parser.add_argument("--phase45-package-dir", default=str(ROOT / "evaluation" / "four_source_expansion" / "nasa_limited_shadow_package_phase45"))
    parser.add_argument("--exclude-package-dir", action="append", default=[])
    parser.add_argument("--exclude-report-json", action="append", default=[])
    parser.add_argument("--include-raw-candidates", action="store_true")
    parser.add_argument("--phase-label", default="Phase 52")
    parser.add_argument("--package-name", default="nasa_second_shadow_package_phase52")
    parser.add_argument("--mode", default="nasa_second_shadow_package_preparation")
    parser.add_argument("--target-count", type=int, default=30)
    parser.add_argument("--out-dir", default=str(ROOT / "evaluation" / "four_source_expansion" / "nasa_second_shadow_package_phase52"))
    parser.add_argument("--report-json", default=str(ROOT / "evaluation" / "four_source_expansion" / "nasa_second_shadow_package_phase52.json"))
    parser.add_argument("--report-md", default=str(ROOT / "docs" / "nasa_second_shadow_package_phase52.md"))
    parser.add_argument("--approval-template", default=str(ROOT / "evaluation" / "four_source_expansion" / "nasa_second_shadow_package_approval_phase52.json"))
    args = parser.parse_args(argv)

    out_dir = Path(args.out_dir)
    report_json = Path(args.report_json)
    report_md = Path(args.report_md)
    approval = Path(args.approval_template)
    if not output_allowed(out_dir) or not output_allowed(report_json) or not output_allowed(report_md, allow_docs=True) or not output_allowed(approval):
        print("outputs must stay under evaluation/four_source_expansion/ or docs/", file=sys.stderr)
        return 2
    if args.target_count <= 0:
        print("target-count must be positive", file=sys.stderr)
        return 2

    exclude_dirs = [Path(args.phase45_package_dir)] + [Path(path) for path in args.exclude_package_dir]
    exclude_reports = [Path(path) for path in args.exclude_report_json]
    report = build_nasa_package(
        phase40_json=Path(args.phase40_json),
        exclude_package_dirs=exclude_dirs,
        out_dir=out_dir,
        approval_template=approval,
        target_count=args.target_count,
        phase_label=args.phase_label,
        package_name=args.package_name,
        mode=args.mode,
        include_raw_candidates=args.include_raw_candidates,
        exclude_report_paths=exclude_reports,
    )
    write_json(report_json, report)
    write_text(report_md, render_markdown(report))
    print(
        f"selected={report['selected_count']} packaged={report['packaged_items']} triples={report['triples']} "
        f"narratives={report['narratives']} rejected={report['rejected']} failed={report['failed']} "
        f"approval={report['approval_status']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
