import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PHASE_DIR = ROOT / "evaluation" / "four_source_expansion" / "phase122"
DOC_PATH = ROOT / "docs" / "zh_external_seed_package_spec_phase122.md"
REQUIRED_FIELDS = ("source_url", "title", "retrieved_at", "license_or_terms", "body", "expected_sha256")
PLACEHOLDER_BODY = "<paste UTF-8 MediaWiki plain text extract here>"


def output_allowed(path: Path, allow_docs: bool = False) -> bool:
    resolved = path.resolve()
    if resolved.is_relative_to(PHASE_DIR.resolve()):
        return True
    return allow_docs and resolved.is_relative_to((ROOT / "docs").resolve())


def output_files() -> list[Path]:
    return [
        Path("docs/zh_external_seed_package_spec_phase122.md"),
        Path("evaluation/four_source_expansion/phase122/zh_seed_package_template_phase122.json"),
        Path("evaluation/four_source_expansion/phase122/phase122_summary.json"),
        Path("evaluation/four_source_expansion/phase122/phase122_summary.md"),
    ]


def _sha256(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def seed_template() -> dict:
    return {
        "source_url": "https://zh.wikipedia.org/wiki/<title>",
        "title": "<title>",
        "retrieved_at": "YYYY-MM-DDTHH:MM:SSZ",
        "license_or_terms": "CC BY-SA; include MediaWiki export/source terms used by operator",
        "provenance_notes": "Downloaded by <operator/tool/environment>; include API URL or export method.",
        "body": PLACEHOLDER_BODY,
        "expected_sha256": _sha256(PLACEHOLDER_BODY),
    }


def validate_template(seed: dict) -> dict:
    missing = [field for field in REQUIRED_FIELDS if field not in seed]
    warnings = []
    if seed.get("body") == PLACEHOLDER_BODY:
        warnings.append("placeholder_body")
    if seed.get("title", "").startswith("<"):
        warnings.append("placeholder_title")
    if seed.get("expected_sha256") != _sha256(seed.get("body", "")):
        warnings.append("checksum_not_matching_current_body")
    return {
        "missing_fields": missing,
        "warnings": warnings,
        "accepted_as_real_seed": not missing and not warnings,
    }


def build_summary() -> dict:
    template = seed_template()
    return {
        "phase": "Phase122",
        "mode": "zh_external_seed_package_spec_and_operator_guide",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "template_validation": validate_template(template),
        "required_fields": list(REQUIRED_FIELDS),
        "checksum_algorithm": "sha256(UTF-8 body)",
        "operator_steps": [
            "download or export MediaWiki plain text in a network-enabled environment",
            "fill one JSON file per seed or a JSON list of seeds",
            "compute expected_sha256 over the exact UTF-8 body",
            "run Phase121 intake with --input-dir against the seed folder",
            "review accepted records manually before any later queue decision",
        ],
        "forbidden": ["live fetch in this phase", "default data writes", "queue/apply/preflight/ingest/production approval"],
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
        "next_recommendation": "prepare audited external seed files, then rerun Phase121 intake for review-only output",
    }


def _markdown(summary: dict) -> str:
    return "\n".join(
        [
            "# Phase122 ZH External Seed Package Spec",
            "",
            "Required seed fields: `source_url`, `title`, `retrieved_at`, `license_or_terms`, `body`, `expected_sha256`.",
            "Optional field: `provenance_notes` for operator/tool/API/export details.",
            "",
            "Checksum: compute `sha256` over the exact UTF-8 `body` string.",
            "Body requirements: readable Chinese article text only; no table/infobox/template/caption-heavy text, mojibake, or numeric-heavy dumps.",
            "Naming: one `.json` seed per article, or one JSON list file; keep files outside repo `data/` paths.",
            "",
            "Run later review-only intake: `python scripts/zh_multi_seed_review_package_phase121.py --input-dir <seed-dir> --write`.",
            "",
            f"Flags: queue={summary['queue_allowed']}, production={summary['production_ready']}, preflight={summary['preflight_allowed']}, apply={summary['apply_approved']}, ingest={summary['ingest_approved']}.",
            "This spec does not approve queue/apply/preflight/ingest/production.",
            "",
        ]
    )


def write_outputs(summary: dict) -> None:
    PHASE_DIR.mkdir(parents=True, exist_ok=True)
    template_path = PHASE_DIR / "zh_seed_package_template_phase122.json"
    summary_json = PHASE_DIR / "phase122_summary.json"
    summary_md = PHASE_DIR / "phase122_summary.md"
    for target in (template_path, summary_json, summary_md, DOC_PATH):
        if not output_allowed(target, allow_docs=target == DOC_PATH):
            raise ValueError(f"output path not allowed: {target}")
    template_path.write_text(json.dumps(seed_template(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown = _markdown(summary)
    summary_md.write_text(markdown, encoding="utf-8")
    DOC_PATH.write_text(markdown, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    summary = build_summary()
    if args.write:
        write_outputs(summary)
    print(json.dumps({"phase": summary["phase"], "spec_status": "template_and_operator_guide_ready", "flags_false": True}, ensure_ascii=False))


if __name__ == "__main__":
    main()
