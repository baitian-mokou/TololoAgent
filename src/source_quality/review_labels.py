from __future__ import annotations

from typing import Any, Dict


RELATION_LABELS: Dict[str, str] = {
    "HAS_RADIUS": "半径",
    "HAS_MASS": "质量",
    "ORBITS": "绕行/轨道关系",
    "HAS_ATMOSPHERE": "大气成分",
    "DISCOVERED_BY": "发现者",
    "LOCATED_IN": "位于",
    "PART_OF": "属于",
    "HAS_DIAMETER": "直径",
    "HAS_TEMPERATURE": "温度",
    "HAS_DENSITY": "密度",
    "HAS_GRAVITY": "表面重力",
}


STATUS_LABELS: Dict[str, Dict[str, str]] = {
    "defer_unresolved": {
        "label": "建议暂缓",
        "description": "外部证据不足，暂时不要合并。",
        "recommended_action": "暂缓",
    },
    "unresolved": {
        "label": "仍未解决",
        "description": "多个来源无法确认谁对谁错。",
        "recommended_action": "暂缓",
    },
    "mark_extraction_error": {
        "label": "建议标记为抽取错误",
        "description": "当前值很可能是抽取过程产生的问题。",
        "recommended_action": "填写修正建议",
    },
    "ontology_rule_needed": {
        "label": "需要知识关系规则",
        "description": "这不是普通数值修正，需要先明确关系规则。",
        "recommended_action": "暂缓",
    },
    "measurement_kind_mismatch": {
        "label": "口径不同",
        "description": "例如平均半径、赤道半径、极半径混在一起。",
        "recommended_action": "通过",
    },
    "true_value_conflict": {
        "label": "数值冲突",
        "description": "不同来源给出了不同值。",
        "recommended_action": "暂缓",
    },
    "source_granularity_mismatch": {
        "label": "来源粒度不同",
        "description": "可能是四舍五入或精度差异。",
        "recommended_action": "拒绝",
    },
    "defer_needs_external_source": {
        "label": "建议暂缓",
        "description": "需要更多权威来源。",
        "recommended_action": "暂缓",
    },
    "approve_measurement_kind_only": {
        "label": "可通过低风险标注",
        "description": "只补充说明，不改事实值。",
        "recommended_action": "通过",
    },
    "no_action": {
        "label": "建议不处理",
        "description": "当前差异不需要改正式数据。",
        "recommended_action": "拒绝",
    },
    "no_action_manual_review": {
        "label": "建议人工复核后不自动处理",
        "description": "当前候选不应自动写入正式数据。",
        "recommended_action": "暂缓",
    },
    "likely_zhwiki_extraction_error": {
        "label": "疑似中文维基抽取错误",
        "description": "外部证据显示当前中文维基值可能来自抽取过程问题。",
        "recommended_action": "填写修正建议",
    },
}


def format_relation_label(relation: str) -> str:
    relation = str(relation or "")
    label = RELATION_LABELS.get(relation)
    return f"{relation}（{label}）" if label else relation


def status_label(status: str) -> str:
    entry = STATUS_LABELS.get(str(status or ""))
    return entry["label"] if entry else str(status or "")


def status_description(status: str) -> str:
    entry = STATUS_LABELS.get(str(status or ""))
    return entry["description"] if entry else "需要人工复核。"


def recommended_action_for_status(status: str, default: str = "暂缓") -> str:
    entry = STATUS_LABELS.get(str(status or ""))
    return entry["recommended_action"] if entry else default


def format_status_explanation(status: str) -> str:
    status = str(status or "")
    if not status:
        return "未给出状态：需要人工复核。"
    entry = STATUS_LABELS.get(status)
    if not entry:
        return f"{status}：需要人工复核。"
    return f"{entry['label']}：{entry['description']}"


def primary_review_status(item: Dict[str, Any]) -> str:
    external = item.get("source_evidence", {}).get("external_review") or {}
    return (
        external.get("recommendation")
        or external.get("comparison_result")
        or item.get("issue_type")
        or item.get("action")
        or ""
    )


def recommended_action_for_review(item: Dict[str, Any], default: str = "暂缓") -> str:
    status = primary_review_status(item)
    if item.get("change_type") == "metadata_only" and item.get("risk_level") == "low":
        return recommended_action_for_status("approve_measurement_kind_only", default)
    return recommended_action_for_status(status, default)
