import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PHASE_DIR = ROOT / "evaluation" / "four_source_expansion" / "phase121"
DOC_PATH = ROOT / "docs" / "zh_multi_seed_review_package_phase121.md"
REQUIRED = ("source_url", "title", "retrieved_at", "license_or_terms", "body")


def output_allowed(path: Path, allow_docs: bool = False) -> bool:
    resolved = path.resolve()
    if resolved.is_relative_to(PHASE_DIR.resolve()):
        return True
    return allow_docs and resolved.is_relative_to((ROOT / "docs").resolve())


def checksum(body: str) -> str:
    return hashlib.sha256((body or "").encode("utf-8")).hexdigest()


def classify_zh_text(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", text or "").strip()
    lower = cleaned.lower()
    if not cleaned:
        return "failed"
    if "�" in cleaned or sum(token in lower for token in ("å", "æ", "ç", "é", "è", "ã")) >= 2:
        return "rejected"
    if any(token in lower for token in ("infobox", "table", "template", "caption", "模板", "信息框", "图注")):
        return "rejected"
    chinese = len(re.findall(r"[\u4e00-\u9fff]", cleaned))
    digits = sum(ch.isdigit() for ch in cleaned)
    if chinese < 18 or digits / max(len(cleaned), 1) > 0.25:
        return "rejected"
    return "accepted"


def fixture_seeds() -> list[dict]:
    bodies = {
        "太阳": "太阳是太阳系中心的恒星，主要由氢和氦组成，通过核聚变释放光和热，并维持行星运行环境。",
        "水星": "水星是太阳系最靠近太阳的行星，表面温差很大，绕太阳公转周期较短，适合作为审查示例正文。",
    }
    seeds = []
    for title, body in bodies.items():
        seeds.append(
            {
                "source_url": f"https://zh.wikipedia.org/wiki/{title}",
                "title": title,
                "retrieved_at": "2026-07-23T00:00:00Z",
                "license_or_terms": "CC BY-SA",
                "body": body,
                "expected_sha256": checksum(body),
            }
        )
    return seeds


def validate_seed(seed: dict, duplicate: bool = False) -> dict:
    body = seed.get("body", "")
    actual = checksum(body)
    expected = seed.get("expected_sha256") or seed.get("computed_sha256") or actual
    reasons = []
    missing = [field for field in REQUIRED if not seed.get(field)]
    if missing:
        reasons.append("missing_provenance:" + ",".join(missing))
    if expected != actual:
        reasons.append("checksum_mismatch")
    quality = classify_zh_text(body)
    if quality != "accepted":
        reasons.append("quality_gate_" + quality)
    if duplicate:
        reasons.append("duplicate_seed")
    accepted = not reasons
    return {
        "source": "zh_wikipedia",
        "source_url": seed.get("source_url", ""),
        "title": seed.get("title", ""),
        "retrieved_at": seed.get("retrieved_at", ""),
        "license_or_terms": seed.get("license_or_terms", ""),
        "checksum": actual,
        "expected_sha256": expected,
        "quality_verdict": "accepted" if accepted else "rejected",
        "reject_reasons": reasons,
        "body_length": len(body),
        "body_preview": body[:220] if accepted else "",
        "review_status": "pending_manual_review" if accepted else "rejected_for_review",
        "queue_allowed": False,
        "production_ready": False,
    }


def load_input_dir(path: Path | None) -> tuple[list[dict], int]:
    if not path or not path.exists():
        return fixture_seeds(), 0
    files = sorted(path.glob("*.json"))
    if not files:
        return fixture_seeds(), 0
    seeds = []
    for file in files:
        with file.open(encoding="utf-8") as handle:
            data = json.load(handle)
        seeds.extend(data if isinstance(data, list) else [data])
    return seeds, len(seeds)


def build_package(seeds: list[dict], external_seed_count: int) -> dict:
    seen = set()
    records = []
    for seed in seeds:
        key = (seed.get("title", ""), seed.get("source_url", ""), checksum(seed.get("body", "")))
        duplicate = key in seen
        seen.add(key)
        records.append(validate_seed(seed, duplicate))
    counts = {
        "total": len(records),
        "accepted": sum(1 for row in records if row["quality_verdict"] == "accepted"),
        "rejected": sum(1 for row in records if row["quality_verdict"] == "rejected"),
    }
    fixture_only = external_seed_count == 0
    return {
        "phase": "Phase121",
        "mode": "zh_multi_seed_review_only_offline_package",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "external_seed_count": external_seed_count,
        "fixture_only": fixture_only,
        "live_fetch_used": False,
        "records": records,
        "review_only_candidates": [row for row in records if row["quality_verdict"] == "accepted"],
        "counts": counts,
        "verdict": "fixture_only_flow_ready_for_review" if fixture_only else "external_seed_review_package_ready_for_review",
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
        "next_recommendation": "provide audited external seeds for real review package; no queue/apply/preflight/ingest approval",
    }


def _markdown(report: dict) -> str:
    return "\n".join(
        [
            "# Phase121 ZH Multi-seed Review-only Offline Package",
            "",
            f"- verdict: {report['verdict']}",
            f"- counts: {report['counts']}",
            f"- external_seed_count: {report['external_seed_count']}",
            f"- fixture_only: {str(report['fixture_only']).lower()}",
            f"- live_fetch_used: {str(report['live_fetch_used']).lower()}",
            f"- queue/production/preflight/apply/ingest: {report['queue_allowed']}/{report['production_ready']}/{report['preflight_allowed']}/{report['apply_approved']}/{report['ingest_approved']}",
            "",
            "Next: review package; use real audited external seeds before treating this as source data.",
            "",
        ]
    )


def write_outputs(report: dict) -> None:
    PHASE_DIR.mkdir(parents=True, exist_ok=True)
    targets = [
        PHASE_DIR / "zh_multi_seed_review_package_phase121.json",
        PHASE_DIR / "zh_multi_seed_review_package_phase121.md",
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
    parser.add_argument("--input-dir")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    seeds, external_count = load_input_dir(Path(args.input_dir) if args.input_dir else None)
    report = build_package(seeds, external_count)
    if args.write:
        write_outputs(report)
    print(json.dumps({"phase": report["phase"], "counts": report["counts"], "fixture_only": report["fixture_only"], "verdict": report["verdict"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
