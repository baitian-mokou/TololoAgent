import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import zh_multi_seed_review_package_phase121 as phase121

PHASE_DIR = ROOT / "evaluation" / "four_source_expansion" / "phase123"
DOC_PATH = ROOT / "docs" / "zh_seed_availability_proxy_readiness_phase123.md"
DEFAULT_DIRS = (
    ROOT / "external_seeds" / "zh_wikipedia",
    ROOT / "evaluation" / "four_source_expansion" / "phase123" / "input_seeds",
)


def output_allowed(path: Path, allow_docs: bool = False) -> bool:
    resolved = path.resolve()
    if resolved.is_relative_to(PHASE_DIR.resolve()):
        return True
    return allow_docs and resolved.is_relative_to((ROOT / "docs").resolve())


def _read_seed_dir(path: Path) -> list[dict]:
    seeds = []
    if not path.exists():
        return seeds
    for file in sorted(path.glob("*.json")):
        with file.open(encoding="utf-8") as handle:
            data = json.load(handle)
        seeds.extend(data if isinstance(data, list) else [data])
    return seeds


def find_external_seeds(paths: list[Path]) -> tuple[list[dict], list[str]]:
    seeds = []
    found_dirs = []
    for path in paths:
        loaded = _read_seed_dir(path)
        if loaded:
            found_dirs.append(str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path))
            seeds.extend(loaded)
    return seeds, found_dirs


def proxy_readiness(env: dict[str, str] | None = None) -> tuple[dict, dict]:
    env = env if env is not None else os.environ
    detected = {name: bool(env.get(name)) for name in ("HTTP_PROXY", "HTTPS_PROXY")}
    redacted = {name: "<redacted>" if detected[name] else "" for name in detected}
    return detected, redacted


def build_readiness(paths: list[Path] | None = None, env: dict[str, str] | None = None) -> dict:
    paths = paths if paths is not None else list(DEFAULT_DIRS)
    seeds, found_dirs = find_external_seeds(paths)
    detected, redacted = proxy_readiness(env)
    validation = phase121.build_package(seeds, len(seeds)) if seeds else None
    return {
        "phase": "Phase123",
        "mode": "zh_external_seed_availability_proxy_readiness",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "candidate_dirs": [str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path) for path in paths],
        "found_seed_dirs": found_dirs,
        "external_seed_count": len(seeds),
        "seed_availability": "external_seeds_found" if seeds else "no_external_seeds_found",
        "validation_run": bool(seeds),
        "validation_summary": {
            "counts": validation["counts"],
            "verdict": validation["verdict"],
            "review_only_candidates": validation["review_only_candidates"],
        }
        if validation
        else None,
        "proxy_env_detected": detected,
        "proxy_env_values": redacted,
        "recommended_next": (
            "review validated external seeds with Phase121 output"
            if seeds
            else "provide audited seed JSON under external_seeds/zh_wikipedia or configure proxy then request controlled retest"
        ),
        "live_fetch_used": False,
        "queue_allowed": False,
        "production_ready": False,
        "preflight_allowed": False,
        "apply_preflight_allowed": False,
        "apply_approved": False,
        "ingest_approved": False,
        "preflight_approved": False,
        "formal_raw_write": False,
        "formal_default_triples_write": False,
        "chroma_write": False,
        "neo4j_write": False,
        "active_source": "zh_wikipedia",
        "active_source_unchanged": True,
        "clear_source_ingestion_outputs_called": False,
    }


def _markdown(report: dict) -> str:
    return "\n".join(
        [
            "# Phase123 ZH Seed Availability + Proxy Readiness",
            "",
            f"- seed_availability: {report['seed_availability']}",
            f"- external_seed_count: {report['external_seed_count']}",
            f"- validation_run: {str(report['validation_run']).lower()}",
            f"- proxy_env_detected: {report['proxy_env_detected']}",
            f"- live_fetch_used: {str(report['live_fetch_used']).lower()}",
            f"- queue/production/preflight/apply/ingest: {report['queue_allowed']}/{report['production_ready']}/{report['preflight_allowed']}/{report['apply_approved']}/{report['ingest_approved']}",
            f"- recommended_next: {report['recommended_next']}",
            "",
        ]
    )


def write_outputs(report: dict) -> None:
    PHASE_DIR.mkdir(parents=True, exist_ok=True)
    targets = [
        PHASE_DIR / "zh_seed_availability_proxy_readiness_phase123.json",
        PHASE_DIR / "zh_seed_availability_proxy_readiness_phase123.md",
        DOC_PATH,
    ]
    for target in targets:
        if not output_allowed(target, allow_docs=target == DOC_PATH):
            raise ValueError(f"output path not allowed: {target}")
    targets[0].write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown = _markdown(report)
    targets[1].write_text(markdown, encoding="utf-8")
    targets[2].write_text(markdown, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", action="append")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    paths = [Path(item) for item in args.input_dir] if args.input_dir else None
    report = build_readiness(paths)
    if args.write:
        write_outputs(report)
    print(json.dumps({"phase": report["phase"], "external_seed_count": report["external_seed_count"], "validation_run": report["validation_run"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
