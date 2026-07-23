import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PHASE_DIR = ROOT / "evaluation" / "four_source_expansion" / "phase120"
DOC_PATH = ROOT / "docs" / "zh_auditable_offline_seed_intake_phase120.md"
REQUIRED = ("source_url", "title", "retrieved_at", "license_or_terms", "body")


def output_allowed(path: Path, allow_docs: bool = False) -> bool:
    resolved = path.resolve()
    if resolved.is_relative_to(PHASE_DIR.resolve()):
        return True
    return allow_docs and resolved.is_relative_to((ROOT / "docs").resolve())


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


def checksum(body: str) -> str:
    return hashlib.sha256((body or "").encode("utf-8")).hexdigest()


def validate_seed(seed: dict) -> dict:
    missing = [field for field in REQUIRED if not seed.get(field)]
    body = seed.get("body", "")
    actual = checksum(body)
    expected = seed.get("expected_sha256") or seed.get("computed_sha256") or actual
    quality = classify_zh_text(body)
    reasons = []
    if missing:
        reasons.append("missing_provenance:" + ",".join(missing))
    if expected != actual:
        reasons.append("checksum_mismatch")
    if quality != "accepted":
        reasons.append("quality_gate_" + quality)
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


def sample_seed() -> dict:
    body = "太阳是太阳系中心的恒星，主要由氢和氦组成，通过核聚变释放光和热，并维持行星运行环境。"
    return {
        "source_url": "https://zh.wikipedia.org/wiki/太阳",
        "title": "太阳",
        "retrieved_at": "2026-07-23T00:00:00Z",
        "license_or_terms": "CC BY-SA",
        "body": body,
        "expected_sha256": checksum(body),
    }


def _load_seeds(path: Path | None) -> list[dict]:
    if not path:
        return [sample_seed()]
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    return data if isinstance(data, list) else [data]


def build_preview(seeds: list[dict]) -> dict:
    records = [validate_seed(seed) for seed in seeds]
    counts = {
        "total": len(records),
        "accepted": sum(1 for row in records if row["quality_verdict"] == "accepted"),
        "rejected": sum(1 for row in records if row["quality_verdict"] == "rejected"),
    }
    return {
        "phase": "Phase120",
        "mode": "zh_auditable_offline_seed_intake_preview",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input_mode": "auditable_offline_seed_only",
        "live_fetch_used": False,
        "records": records,
        "review_only_candidates": [row for row in records if row["quality_verdict"] == "accepted"],
        "counts": counts,
        "verdict": "offline_seed_intake_preview_ready_for_review" if counts["accepted"] else "offline_seed_intake_no_accepted_candidates",
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
        "next_recommendation": "review offline seed provenance and checksum before any zh queue decision",
    }


def _markdown(report: dict) -> str:
    return "\n".join(
        [
            "# Phase120 ZH Auditable Offline Seed Intake Preview",
            "",
            f"- verdict: {report['verdict']}",
            f"- counts: {report['counts']}",
            f"- live_fetch_used: {str(report['live_fetch_used']).lower()}",
            f"- queue/production/preflight/apply/ingest: {report['queue_allowed']}/{report['production_ready']}/{report['preflight_allowed']}/{report['apply_approved']}/{report['ingest_approved']}",
            "",
            "Next: review offline seed provenance/checksum; no queue/apply/preflight/ingest approval.",
            "",
        ]
    )


def write_outputs(report: dict) -> None:
    PHASE_DIR.mkdir(parents=True, exist_ok=True)
    targets = [
        PHASE_DIR / "zh_auditable_offline_seed_intake_phase120.json",
        PHASE_DIR / "zh_auditable_offline_seed_intake_phase120.md",
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
    parser.add_argument("--seed-json")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    report = build_preview(_load_seeds(Path(args.seed_json) if args.seed_json else None))
    if args.write:
        write_outputs(report)
    print(json.dumps({"phase": report["phase"], "counts": report["counts"], "verdict": report["verdict"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
