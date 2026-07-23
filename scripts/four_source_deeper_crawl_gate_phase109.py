import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PHASE_DIR = ROOT / "evaluation" / "four_source_expansion" / "phase109"
DOC_PATH = ROOT / "docs" / "four_source_deeper_crawl_gate_phase109.md"


def output_allowed(path: Path, allow_docs: bool = False) -> bool:
    resolved = path.resolve()
    if resolved.is_relative_to(PHASE_DIR.resolve()):
        return True
    return allow_docs and resolved.is_relative_to((ROOT / "docs").resolve())


def _load(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def default_gate_config() -> dict:
    return {
        "mode": "controlled_deeper_crawl_gate_design_only",
        "live_fetch_allowed": False,
        "actual_crawl_allowed": False,
        "output_root": "evaluation/four_source_expansion/phase109",
        "total_max_batch": 80,
        "sources": {
            "zh_wikipedia": {
                "max_batch": 20,
                "entry_rules": ["article body pages only", "existing review context or approved seeds only"],
                "allowlist": ["zh.wikipedia.org/wiki/"],
                "denylist": ["infobox", "table-heavy", "template-heavy", "category", "special"],
                "required_fields": ["title", "source_url", "body_text", "source", "quality_flags"],
                "quality_gates": ["body_extraction", "template_table_ratio", "minimum_readable_text"],
                "stop_conditions": ["template/table noise dominates", "duplicate title/source_url", "batch limit reached"],
            },
            "nasa": {
                "max_batch": 10,
                "entry_rules": ["validated endpoint/API strategy only", "no generic web crawl"],
                "allowlist": ["images-api.nasa.gov", "science.nasa.gov/wp-json", "nasa.gov"],
                "denylist": ["search", "gallery", "index", "tag", "category", "navigation"],
                "required_fields": ["title", "source_url", "source_id", "body_or_metadata", "endpoint_method", "quality_flags"],
                "quality_gates": ["endpoint_method_recorded", "non_navigation_text", "metadata_not_thin_only"],
                "stop_conditions": ["navigation residue dominates", "endpoint quality below reviewable", "batch limit reached"],
            },
            "esa": {
                "max_batch": 20,
                "entry_rules": ["mission/science content only", "preserve known conditional quality labels"],
                "allowlist": ["esa.int", "sci.esa.int", "www.esa.int"],
                "denylist": ["index", "news listing", "latest", "tag", "category", "press list"],
                "required_fields": ["title", "source_url", "body_text", "source", "quality_flags"],
                "quality_gates": ["mission_or_science_signal", "index_listing_filter", "minimum_readable_text"],
                "stop_conditions": ["index/news listing dominates", "duplicate mission page", "batch limit reached"],
            },
            "wikidata": {
                "max_batch": 30,
                "entry_rules": ["structured QID/claim expansion only", "no thin/no-claim entities"],
                "allowlist": ["wikidata.org/wiki/", "wikidata.org/entity/", "wikidata.org/w/api.php"],
                "denylist": ["no-claim", "disambiguation", "unreferenced", "thin-label-only"],
                "required_fields": ["qid", "label", "claims", "source_url", "quality_flags"],
                "quality_gates": ["claim_filter", "reference_or_source_field", "non_empty_structured_fact"],
                "stop_conditions": ["no meaningful claims", "duplicate QID", "batch limit reached"],
            },
        },
        "safety_flags": {
            "production_ready": False,
            "preflight_allowed": False,
            "apply_approved": False,
            "ingest_approved": False,
            "formal_raw_write": False,
            "formal_default_triples_write": False,
            "chroma_write": False,
            "neo4j_write": False,
        },
    }


def evaluate_gate_config(config: dict) -> dict:
    sources = config.get("sources", {})
    required_sources = {"zh_wikipedia", "nasa", "esa", "wikidata"}
    total = sum(source.get("max_batch", 0) for source in sources.values())
    required_keys = {"entry_rules", "allowlist", "denylist", "required_fields", "quality_gates", "stop_conditions"}
    schema_pass = set(sources) == required_sources and all(required_keys <= set(source) for source in sources.values())
    limit_pass = total <= 80 and sources.get("zh_wikipedia", {}).get("max_batch") <= 20 and sources.get("nasa", {}).get("max_batch") <= 10 and sources.get("esa", {}).get("max_batch") <= 20 and sources.get("wikidata", {}).get("max_batch") <= 30
    flags = config.get("safety_flags", {})
    safety_pass = (
        config.get("live_fetch_allowed") is False
        and config.get("actual_crawl_allowed") is False
        and all(flags.get(name) is False for name in [
            "production_ready",
            "preflight_allowed",
            "apply_approved",
            "ingest_approved",
            "formal_raw_write",
            "formal_default_triples_write",
            "chroma_write",
            "neo4j_write",
        ])
    )
    return {
        "schema_pass": schema_pass,
        "limit_pass": limit_pass,
        "safety_pass": safety_pass,
        "total_max_batch": total,
        "ready_to_run_controlled_deeper_crawl": schema_pass and limit_pass and safety_pass,
        "production_ready": False,
        "preflight_allowed": False,
    }


def build_gate_design(phase108_report: Path, phase107_closeout: Path, phase106_report: Path, phase105_handoff: Path) -> dict:
    phase108 = _load(phase108_report)
    phase107 = _load(phase107_closeout)
    phase106 = _load(phase106_report)
    phase105 = _load(phase105_handoff)
    config = default_gate_config()
    evaluation = evaluate_gate_config(config)
    return {
        "phase": "Phase109",
        "mode": "controlled_deeper_crawl_gate_design",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input_reports": {
            "phase105": str(phase105_handoff.relative_to(ROOT)),
            "phase106": str(phase106_report.relative_to(ROOT)),
            "phase107": str(phase107_closeout.relative_to(ROOT)),
            "phase108": str(phase108_report.relative_to(ROOT)),
        },
        "gate_readiness": "ready_to_run_controlled_deeper_crawl_after_review" if evaluation["ready_to_run_controlled_deeper_crawl"] else "not_ready",
        "ready_to_run_controlled_deeper_crawl": evaluation["ready_to_run_controlled_deeper_crawl"],
        "live_fetch_allowed_in_gate_design": False,
        "actual_crawl_performed": False,
        "total_max_batch": config["total_max_batch"],
        "gate_config": config,
        "dry_run_evaluation": evaluation,
        "source_context": {
            "phase108_repair_counts": phase108["repair_counts_by_source"],
            "phase107_final_verdict": phase107["final_verdict"],
            "phase106_conditional_counts": phase106["item_verdict_counts_by_source"],
            "phase105_status": phase105["overall_status"],
        },
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
        "next_recommendation": "review gate design before any controlled deeper crawl run",
    }


def _markdown(report: dict) -> str:
    lines = [
        "# Phase109 Controlled Deeper Crawl Gate Design",
        "",
        f"- Gate readiness: {report['gate_readiness']}",
        f"- Total max batch: {report['total_max_batch']}",
        "- Live fetch in this phase: false",
        "- Production/preflight/apply/ingest: false",
        "",
        "## Source Limits",
    ]
    for source, config in report["gate_config"]["sources"].items():
        lines.append(f"- {source}: max {config['max_batch']}; gates={config['quality_gates']}; deny={config['denylist']}")
    return "\n".join(lines) + "\n"


def write_outputs(report: dict) -> list[Path]:
    paths = [
        PHASE_DIR / "controlled_deeper_crawl_gate_phase109.json",
        PHASE_DIR / "controlled_deeper_crawl_gate_phase109.md",
        DOC_PATH,
    ]
    for path in paths:
        if not output_allowed(path, allow_docs=path == DOC_PATH):
            raise ValueError(f"blocked output path: {path}")
    PHASE_DIR.mkdir(parents=True, exist_ok=True)
    (PHASE_DIR / "controlled_deeper_crawl_gate_phase109.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (PHASE_DIR / "controlled_deeper_crawl_gate_phase109.md").write_text(_markdown(report), encoding="utf-8")
    DOC_PATH.write_text(_markdown(report), encoding="utf-8")
    return paths


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Phase109 controlled deeper crawl gate design.")
    parser.add_argument("--phase108-report", type=Path, default=ROOT / "evaluation" / "four_source_expansion" / "phase108" / "source_repair_preview_phase108.json")
    parser.add_argument("--phase107-closeout", type=Path, default=ROOT / "evaluation" / "four_source_expansion" / "phase107" / "final_closeout_phase107.json")
    parser.add_argument("--phase106-report", type=Path, default=ROOT / "evaluation" / "four_source_expansion" / "phase106" / "item_verdict_report_phase106.json")
    parser.add_argument("--phase105-handoff", type=Path, default=ROOT / "evaluation" / "four_source_expansion" / "phase105" / "review_handoff_phase105.json")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    report = build_gate_design(args.phase108_report, args.phase107_closeout, args.phase106_report, args.phase105_handoff)
    if args.write:
        write_outputs(report)
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
