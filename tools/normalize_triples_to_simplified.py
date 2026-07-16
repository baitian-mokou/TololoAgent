"""
将现有 data/triples 下的三元组与叙事文件统一归一化为简体并去重。
"""
from __future__ import annotations

import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from config import TRIPLES_DIR
from src.nlp.text_normalizer import normalize_narrative_record, normalize_to_simplified, normalize_triple_record


def normalize_triples_file(path: str) -> tuple[int, int]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        return 0, 0

    before = len(data)
    seen = set()
    normalized = []
    for item in data:
        record = normalize_triple_record(item)
        key = (
            record.get("subject", ""),
            record.get("relation", ""),
            record.get("object", ""),
        )
        if not all(key) or key in seen:
            continue
        seen.add(key)
        normalized.append(record)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(normalized, f, ensure_ascii=False, indent=2)
    return before, len(normalized)


def normalize_narratives_file(path: str) -> tuple[int, int]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        return 0, 0

    before = len(data)
    seen = set()
    normalized = []
    for item in data:
        record = normalize_narrative_record(item)
        content = record.get("content", "")
        if not content:
            continue
        key = content[:100]
        if key in seen:
            continue
        seen.add(key)
        normalized.append(record)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(normalized, f, ensure_ascii=False, indent=2)
    return before, len(normalized)


def main():
    triple_files = glob.glob(os.path.join(TRIPLES_DIR, "*_triples.json"))
    narrative_files = glob.glob(os.path.join(TRIPLES_DIR, "*_narratives.json"))

    triple_before = triple_after = 0
    for path in triple_files:
        before, after = normalize_triples_file(path)
        triple_before += before
        triple_after += after

    narrative_before = narrative_after = 0
    for path in narrative_files:
        before, after = normalize_narratives_file(path)
        narrative_before += before
        narrative_after += after

    print(
        normalize_to_simplified(
            f"已完成归一化：三元组 {triple_before} -> {triple_after}，叙事 {narrative_before} -> {narrative_after}"
        )
    )


if __name__ == "__main__":
    main()
