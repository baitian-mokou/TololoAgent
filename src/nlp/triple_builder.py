"""
三元组构建器 - 后处理+去重+JSON输出
"""
import json
import os

from .ontology import validate_triple
from .text_normalizer import (
    normalize_narrative_record,
    normalize_to_simplified,
    normalize_triple_record,
)
from src.source_control import (
    RECORD_TYPE_EMBEDDING_CHUNK,
    RECORD_TYPE_TRIPLE_CANDIDATE,
    apply_record_metadata,
)


class TripleBuilder:
    """构建并输出三元组和叙事知识片段"""

    def __init__(self, output_dir):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
        self._seen_triples = set()
        self._seen_narratives = set()

    def add_triple(self, triple, source_title):
        """添加一个三元组（带来源）"""
        normalized = normalize_triple_record(triple)
        validated = validate_triple(
            normalized.get('subject', ''),
            normalized.get('relation', ''),
            normalized.get('object', ''),
        )
        if not validated:
            return False
        normalized.update(validated)
        source_title = normalize_to_simplified(source_title).strip()
        key = f"{normalized['subject']}|{normalized['relation']}|{normalized['object']}"
        if key in self._seen_triples:
            return False
        self._seen_triples.add(key)
        normalized = apply_record_metadata(
            normalized,
            normalized.get('origin'),
            RECORD_TYPE_TRIPLE_CANDIDATE,
            source_name=normalized.get('source_name') or normalized.get('source'),
            source_title=source_title or normalized.get('source_title', ''),
            extra={"schema_version": normalized.get("schema_version", "")} if normalized.get("schema_version") else None,
        )
        normalized['raw'] = normalize_to_simplified(normalized.get('raw', '')).strip()
        triple.clear()
        triple.update(normalized)
        return True

    def add_narrative(self, narrative):
        """添加一个叙事片段（去重）"""
        normalized = normalize_narrative_record(narrative)
        content_key = normalized['content'][:100]
        if content_key in self._seen_narratives:
            return False
        self._seen_narratives.add(content_key)
        normalized = apply_record_metadata(
            normalized,
            normalized.get('origin'),
            RECORD_TYPE_EMBEDDING_CHUNK,
            source_name=normalized.get('source_name') or normalized.get('source'),
            source_title=normalized.get('source_title') or normalized.get('page_title', ''),
            extra={"schema_version": normalized.get("schema_version", "")} if normalized.get("schema_version") else None,
        )
        narrative.clear()
        narrative.update(normalized)
        return True

    def save_triples(self, name, triples):
        """保存三元组到JSON文件"""
        path = os.path.join(self.output_dir, f'{name}_triples.json')
        merged = self._merge_triples(path, triples)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(merged, f, ensure_ascii=False, indent=2)
        return path

    def save_narratives(self, name, narratives):
        """保存叙事片段到JSON文件"""
        path = os.path.join(self.output_dir, f'{name}_narratives.json')
        merged = self._merge_narratives(path, narratives)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(merged, f, ensure_ascii=False, indent=2)
        return path

    def get_stats(self):
        """返回统计信息"""
        return {
            'triples': len(self._seen_triples),
            'narratives': len(self._seen_narratives),
        }

    def _merge_triples(self, path, triples):
        records = self._load_json_list(path)
        seen = set()
        merged = []
        for triple in records + list(triples):
            normalized = normalize_triple_record(triple)
            validated = validate_triple(
                normalized.get('subject', ''),
                normalized.get('relation', ''),
                normalized.get('object', ''),
            )
            if not validated:
                continue
            normalized.update(validated)
            key = (
                normalized.get('subject', ''),
                normalized.get('relation', ''),
                normalized.get('object', ''),
            )
            if not all(key) or key in seen:
                continue
            seen.add(key)
            normalized = apply_record_metadata(
                normalized,
                normalized.get('origin'),
                RECORD_TYPE_TRIPLE_CANDIDATE,
                source_name=normalized.get('source_name') or normalized.get('source'),
                source_title=normalized.get('source_title') or normalized.get('subject', ''),
                extra={"schema_version": normalized.get("schema_version", "")} if normalized.get("schema_version") else None,
            )
            normalized['raw'] = normalize_to_simplified(normalized.get('raw', '')).strip()
            merged.append(normalized)
        return merged

    def _merge_narratives(self, path, narratives):
        records = self._load_json_list(path)
        seen = set()
        merged = []
        for narrative in records + list(narratives):
            normalized = normalize_narrative_record(narrative)
            content = normalized.get('content', '')
            if not content:
                continue
            key = content[:100]
            if key in seen:
                continue
            seen.add(key)
            normalized = apply_record_metadata(
                normalized,
                normalized.get('origin'),
                RECORD_TYPE_EMBEDDING_CHUNK,
                source_name=normalized.get('source_name') or normalized.get('source'),
                source_title=normalized.get('source_title') or normalized.get('page_title', ''),
                extra={"schema_version": normalized.get("schema_version", "")} if normalized.get("schema_version") else None,
            )
            merged.append(normalized)
        return merged

    @staticmethod
    def _load_json_list(path):
        if not os.path.exists(path):
            return []
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return data if isinstance(data, list) else []
        except Exception:
            return []
