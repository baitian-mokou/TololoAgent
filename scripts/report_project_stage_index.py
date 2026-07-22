from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import ACTIVE_SOURCE, SOURCE_REGISTRY


REPORTS = [
    ("final_status", "docs/project_current_stage_final_report.md"),
    ("source_expansion_delivery", "docs/source_expansion_delivery_report.md"),
    ("general_screening_overview", "docs/general_science_source_screening_overview.md"),
    ("source_expansion_status", "evaluation/source_expansion/source_expansion_status_report.json"),
    ("shadow_graph_probe", "evaluation/source_expansion/shadow_graph_probe_report.json"),
    ("manifest_validation", "evaluation/source_quality/source_manifest_validation_report.json"),
    ("candidate_sites_summary", "evaluation/source_quality/sandbox/candidate_science_sites_summary_phase28.json"),
    ("candidate_sites_filled_review", "evaluation/source_quality/sandbox/candidate_science_sites_summary_phase29_filled.json"),
    ("approved_plan_preview", "evaluation/source_quality/sandbox/candidate_science_sites_approved_plan_phase29.json"),
    ("offline_fixture_quality", "evaluation/source_quality/sandbox/offline_fixture_quality_phase30.json"),
    ("preview_probe_plan", "evaluation/source_quality/sandbox/preview_network_probe_plan_phase31.json"),
    ("network_probe_approval_package", "evaluation/source_quality/sandbox/network_probe_approval_package_phase32.json"),
    ("network_probe_approval_decisions", "evaluation/source_quality/sandbox/network_probe_approval_decisions_phase33_filled.json"),
    ("manual_preview_command_card", "evaluation/source_quality/sandbox/manual_preview_command_card_phase34.json"),
]


VERIFICATION_COMMANDS = [
    "venv\\Scripts\\python.exe -m unittest discover tests",
    "venv\\Scripts\\python.exe scripts\\validate_source_manifests.py",
    "venv\\Scripts\\python.exe scripts\\report_sandbox_candidate_reviews.py --manifest-dir configs\\source_manifests\\candidates --sandbox-dir evaluation\\source_quality\\sandbox --out-json evaluation\\source_quality\\sandbox\\candidate_science_sites_summary_phase28.json --out-md evaluation\\source_quality\\sandbox\\candidate_science_sites_summary_phase28.md",
    "venv\\Scripts\\python.exe scripts\\report_offline_fixture_quality.py --manifest-dir configs\\source_manifests\\candidates --source noaa_climate_candidate --source data_portal_candidate --fixture-dir tests\\fixtures\\source_quality --out-json evaluation\\source_quality\\sandbox\\offline_fixture_quality_phase30.json --out-md evaluation\\source_quality\\sandbox\\offline_fixture_quality_phase30.md",
    "venv\\Scripts\\python.exe scripts\\render_network_probe_approval_package.py --probe-plan-json evaluation\\source_quality\\sandbox\\preview_network_probe_plan_phase31.json --out-json evaluation\\source_quality\\sandbox\\network_probe_approval_package_phase32.json --out-md evaluation\\source_quality\\sandbox\\network_probe_approval_package_phase32.md",
]


SAFETY_BOUNDARIES = [
    "不直接全网爬取。",
    "不执行 fetch / crawl / ingest。",
    "不写正式 raw、triples、narratives、Chroma 或 Neo4j。",
    "不自动批准 preview-only 网络探测。",
    "未注册 candidate source 只能停留在 sandbox / report。",
    "ACTIVE_SOURCE 必须保持 zh_wikipedia。",
]


NEXT_ROUTES = [
    {"id": "A", "title": "继续离线增强", "description": "扩展 fixture pack、页面类型和人工审阅样本。"},
    {"id": "B", "title": "用户明确批准后做 NOAA 5 页 preview-only 网络探测", "description": "使用 Phase 34 命令卡，仍只写 sandbox 报告。"},
    {"id": "C", "title": "准备答辩材料", "description": "围绕三源 shadow 扩源和通用科学网站筛选闭环组织展示。"},
]


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def output_allowed(path: Path) -> bool:
    parts = set(path.resolve().parts)
    return "evaluation" in parts or "docs" in parts


def report_item(root: Path, category: str, rel_path: str) -> Dict[str, Any]:
    path = root / rel_path
    return {
        "category": category,
        "path": rel_path,
        "status": "present" if path.exists() else "missing",
    }


def build_index(root: Path = ROOT) -> Dict[str, Any]:
    registry = {name: SOURCE_REGISTRY.get(name) for name in ("zh_wikipedia", "wikidata", "nasa", "esa")}
    return {
        "current_stage": "Phase 36 index",
        "previous_stage": "Phase 35 complete",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_status": {
            "active_source": ACTIVE_SOURCE,
            "registry": registry,
            "candidate_registered": any(
                name in SOURCE_REGISTRY for name in ("noaa_climate_candidate", "data_portal_candidate")
            ),
        },
        "report_index": [report_item(root, category, rel_path) for category, rel_path in REPORTS],
        "github_hint": {
            "network_checked": False,
            "note": "分支和 commit 状态请在计划端或本地 git 命令中确认；本索引不联网查询。",
        },
        "verification_commands": VERIFICATION_COMMANDS,
        "safety_boundaries": SAFETY_BOUNDARIES,
        "next_routes": NEXT_ROUTES,
    }


def render_markdown(report: Dict[str, Any]) -> str:
    source = report["source_status"]
    lines: List[str] = [
        "# 项目状态索引",
        "",
        f"- 当前阶段：`{report['current_stage']}`",
        f"- 上一阶段：`{report['previous_stage']}`",
        f"- ACTIVE_SOURCE：`{source['active_source']}`",
        f"- Candidate registered：`{source['candidate_registered']}`",
        "",
        "## 默认源状态",
        "",
        "| source | status |",
        "|---|---|",
    ]
    for name, status in source["registry"].items():
        lines.append(f"| {name} | `{status}` |")

    lines.extend(["", "## 关键报告索引", "", "| category | path | status |", "|---|---|---|"])
    for item in report["report_index"]:
        lines.append(f"| {item['category']} | `{item['path']}` | `{item['status']}` |")

    lines.extend(["", "## 可复现验证命令", ""])
    for command in report["verification_commands"]:
        lines.append(f"- `{command}`")

    lines.extend(["", "## 安全红线", ""])
    for boundary in report["safety_boundaries"]:
        lines.append(f"- {boundary}")

    lines.extend(["", "## 下一步路线", ""])
    for route in report["next_routes"]:
        lines.append(f"- **{route['id']}：{route['title']}** - {route['description']}")

    lines.extend([
        "",
        "## GitHub / Commit 提示",
        "",
        report["github_hint"]["note"],
        "",
    ])
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Build current project stage report index.")
    parser.add_argument("--out-json", default=str(ROOT / "evaluation" / "project_stage_index.json"))
    parser.add_argument("--out-md", default=str(ROOT / "docs" / "project_stage_index.md"))
    args = parser.parse_args(argv)

    out_json = Path(args.out_json)
    out_md = Path(args.out_md)
    if not output_allowed(out_json) or not output_allowed(out_md):
        print("outputs must stay under evaluation/ or docs/", file=sys.stderr)
        return 2

    report = build_index(ROOT)
    write_json(out_json, report)
    write_text(out_md, render_markdown(report))
    missing = sum(1 for item in report["report_index"] if item["status"] == "missing")
    print(f"reports={len(report['report_index'])} missing={missing} active_source={ACTIVE_SOURCE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
