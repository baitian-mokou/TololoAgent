from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import BASE_DIR
from src.source_quality.review_labels import (
    format_relation_label,
    format_status_explanation,
    primary_review_status,
    recommended_action_for_review,
    status_label,
)


DEFAULT_QUEUE = Path(BASE_DIR) / "data" / "quality_review" / "quality_review_queue.json"
DEFAULT_MARKDOWN = Path(BASE_DIR) / "docs" / "quality_review_cards.md"
DEFAULT_JSON = Path(BASE_DIR) / "evaluation" / "quality_review_cards.json"


def configure_stdout() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def dump_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def format_value(value: Any) -> str:
    if isinstance(value, list):
        return "、".join(str(item) for item in value)
    if value is None or value == "":
        return "未给出"
    return str(value)


def issue_label(issue_type: str) -> str:
    if not issue_type:
        return "需要人工复核"
    return status_label(issue_type) or issue_type


def risk_label(risk_level: str) -> str:
    return {"high": "高风险", "medium": "中风险", "low": "低风险"}.get(risk_level, risk_level or "风险未定")


def current_values_text(item: Dict[str, Any]) -> str:
    evidence = item.get("source_evidence", {})
    values = evidence.get("values_by_source", {})
    parts = []
    for source, source_values in values.items():
        parts.append(f"{source}: {format_value(source_values)}")
    return "；".join(parts) if parts else format_value(item.get("current_value"))


def external_evidence_text(item: Dict[str, Any]) -> str:
    external = item.get("source_evidence", {}).get("external_review") or {}
    if not external:
        return "暂无额外外部复核；请以审计证据和原始来源为准。"
    evidence = external.get("external_evidence") or {}
    recommendation = external.get("recommendation") or external.get("action") or ""
    comparison = external.get("comparison_result") or ""
    confidence = external.get("confidence")
    normalized = evidence.get("normalized_value") or evidence.get("object") or "未给出标准化值"
    url = evidence.get("source_url") or "未给出链接"
    license_text = evidence.get("source_license") or evidence.get("license_hint") or "未说明许可"
    return (
        f"外部复核建议：{format_status_explanation(recommendation)}；"
        f"比较结果：{format_status_explanation(comparison)}；置信度：{confidence}。"
        f"外部值：{normalized}；来源：{url}；许可：{license_text}。"
    )


def recommended_action(item: Dict[str, Any]) -> str:
    return recommended_action_for_review(item, "暂缓")


def risk_explanation(item: Dict[str, Any]) -> str:
    status = primary_review_status(item)
    if status:
        return format_status_explanation(status)
    if item.get("change_type") == "metadata_only":
        return "这条只涉及补充测量口径或质量状态，不改变 subject/relation/object。"
    if item.get("risk_level") == "high":
        return "这条可能涉及事实值冲突或抽取错误。建议先暂缓，不建议直接合并。"
    if item.get("issue_type") == "source_granularity_mismatch":
        return "这条更像不同来源的精度差异，通常不需要改正式数据。"
    return "这条需要人工判断，默认不写入正式数据。"


def merge_impact(item: Dict[str, Any]) -> str:
    if item.get("change_type") == "metadata_only":
        return "若审批通过并执行低风险标注，只会给匹配 triples 增加质量元数据；不会改变正式事实值。"
    if item.get("risk_level") == "high":
        return "默认不会合并为正式事实值；需要额外来源确认和显式 value-change 许可。"
    return "默认不会写入正式 triples。"


def human_system_recommendation(item: Dict[str, Any]) -> str:
    action = recommended_action(item)
    status = primary_review_status(item)
    explanation = format_status_explanation(status)
    if action == "通过":
        return f"{explanation} 推荐操作：通过低风险标注；仍需先 dry-run。"
    if action == "拒绝":
        return f"{explanation} 推荐操作：拒绝当前候选，不写正式数据。"
    if action == "填写修正建议":
        return f"{explanation} 推荐操作：填写修正建议，保存后先 dry-run 查看差异。"
    return f"{explanation} 推荐操作：暂缓，等待更多证据。"


def user_summary(item: Dict[str, Any]) -> str:
    subject = item.get("subject") or "未知对象"
    relation = format_relation_label(item.get("relation") or "未知关系")
    return (
        f"{subject} 的 {relation} 被列入质量复查。"
        f"当前记录是：{format_value(item.get('current_value'))}。"
        f"问题原因：{issue_label(item.get('issue_type'))}。"
    )


def build_card(item: Dict[str, Any], index: int) -> Dict[str, Any]:
    evidence_summary = external_evidence_text(item)
    card = {
        "card_id": f"quality_card_{index:03d}",
        "review_id": item.get("review_id"),
        "patch_id": item.get("patch_id"),
        "subject": item.get("subject"),
        "relation": item.get("relation"),
        "relation_label": format_relation_label(item.get("relation")),
        "human_decision": item.get("human_decision", "pending"),
        "risk_level": item.get("risk_level"),
        "risk_label": risk_label(item.get("risk_level")),
        "status_label": status_label(primary_review_status(item)),
        "status_explanation": format_status_explanation(primary_review_status(item)),
        "current_value_summary": current_values_text(item),
        "user_facing_summary": user_summary(item),
        "recommended_user_action": recommended_action(item),
        "risk_explanation": risk_explanation(item),
        "evidence_summary": evidence_summary,
        "merge_impact_summary": merge_impact(item),
        "system_recommendation": human_system_recommendation(item),
    }
    return card


def card_has_chinese_text(card: Dict[str, Any]) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", card.get("user_facing_summary", "")))


def render_markdown(cards: List[Dict[str, Any]], generated_at: str) -> str:
    lines = [
        "# 质量复查卡片",
        "",
        f"生成时间：`{generated_at}`",
        "",
        f"卡片数量：`{len(cards)}`",
        "",
    ]
    for index, card in enumerate(cards, start=1):
        lines.extend(
            [
                f"## {index}. {card.get('subject')} / {card.get('relation_label')}",
                "",
                f"- 复查项：`{card.get('patch_id')}`",
                f"- 关系：{card.get('relation_label')}",
                f"- 中文状态：{card.get('status_label') or '需要人工复核'}",
                f"- 简短解释：{card.get('status_explanation')}",
                f"- 风险等级：{card.get('risk_label')}",
                f"- 推荐操作：{card.get('recommended_user_action')}",
                f"- 当前值：{card.get('current_value_summary')}",
                f"- 这条数据是什么：{card.get('user_facing_summary')}",
                f"- 为什么：{card.get('risk_explanation')}",
                f"- 外部证据：{card.get('evidence_summary')}",
                f"- 合并影响：{card.get('merge_impact_summary')}",
                f"- 系统建议：{card.get('system_recommendation') or '暂无'}",
                "",
            ]
        )
    return "\n".join(lines)


def generate_quality_review_cards(
    queue_path: str = str(DEFAULT_QUEUE),
    markdown_path: str = str(DEFAULT_MARKDOWN),
    json_path: str = str(DEFAULT_JSON),
) -> Dict[str, Any]:
    generated_at = datetime.now(timezone.utc).isoformat()
    queue_file = Path(queue_path)
    queue = load_json(queue_file)
    items = [item for item in queue.get("items", []) if isinstance(item, dict)]
    cards = []
    for index, item in enumerate(items, start=1):
        card = build_card(item, index)
        item["user_facing_summary"] = card["user_facing_summary"]
        item["recommended_user_action"] = card["recommended_user_action"]
        item["risk_explanation"] = card["risk_explanation"]
        item["evidence_summary"] = card["evidence_summary"]
        item["merge_impact_summary"] = card["merge_impact_summary"]
        item["relation_label"] = card["relation_label"]
        item["status_label"] = card["status_label"]
        item["status_explanation"] = card["status_explanation"]
        cards.append(card)
    queue.setdefault("summary", {})["card_count"] = len(cards)
    queue["cards_generated_at"] = generated_at
    dump_json(queue_file, queue)

    payload = {
        "generated_at": generated_at,
        "queue_path": str(queue_file),
        "card_count": len(cards),
        "all_cards_have_chinese_summary": all(card_has_chinese_text(card) for card in cards),
        "formal_triples_written": False,
        "chroma_written": False,
        "neo4j_written": False,
        "cards": cards,
    }
    dump_json(Path(json_path), payload)
    Path(markdown_path).parent.mkdir(parents=True, exist_ok=True)
    Path(markdown_path).write_text(render_markdown(cards, generated_at), encoding="utf-8")
    return {
        "markdown_path": str(markdown_path),
        "json_path": str(json_path),
        "queue_path": str(queue_file),
        "card_count": len(cards),
        "formal_triples_written": False,
        "chroma_written": False,
        "neo4j_written": False,
    }


def main() -> None:
    configure_stdout()
    parser = argparse.ArgumentParser(description="Generate human-readable quality review cards.")
    parser.add_argument("--queue", default=str(DEFAULT_QUEUE))
    parser.add_argument("--markdown", default=str(DEFAULT_MARKDOWN))
    parser.add_argument("--json", default=str(DEFAULT_JSON))
    args = parser.parse_args()
    result = generate_quality_review_cards(args.queue, args.markdown, args.json)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
