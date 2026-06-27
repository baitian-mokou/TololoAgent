"""
NLP流水线协调器 - 供GUI调用的统一入口
Wikipedia HTML → preprocess pipeline → 三元组 + embedding chunks
"""
import os
import json
import sys
import re
import time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))

from config import ACTIVE_SOURCE, BASE_DIR, RAW_JSON_DIR, SOURCE_REGISTRY, TRIPLES_DIR
from src.source_control import (
    SOURCE_SCHEMA_VERSION,
    get_single_source_baseline_namespace,
    get_source_namespace_dir,
    get_source_schema_version,
)

from .preprocess import WikiPreprocessor
from .text_normalizer import normalize_to_simplified
from .triple_builder import TripleBuilder


class NlpPipeline:
    """协调预处理 pipeline，输出 Neo4j / Chroma 兼容数据"""

    def __init__(self, progress_callback=None, source_name=None, source_role=None, schema_version=None):
        self.progress_callback = progress_callback
        self._base_dir = BASE_DIR
        self.source_name = source_name or get_single_source_baseline_namespace() or ACTIVE_SOURCE
        self.source_role = source_role
        self.schema_version = schema_version or get_source_schema_version(self.source_name)
        self.raw_json_dir = get_source_namespace_dir(RAW_JSON_DIR, self.source_name)
        self.triples_dir = get_source_namespace_dir(TRIPLES_DIR, self.source_name)
        os.makedirs(self.triples_dir, exist_ok=True)
        os.makedirs(self.raw_json_dir, exist_ok=True)

        self.preprocessor = WikiPreprocessor(
            source_name=self.source_name,
            source_role=self.source_role,
            schema_version=self.schema_version,
        )
        self.triple_builder = TripleBuilder(self.triples_dir)

    def _report(self, msg):
        if self.progress_callback:
            self.progress_callback(0, 0, msg)

    @staticmethod
    def _should_skip_json(fname):
        """跳过非条目JSON文件"""
        skip_prefixes = ['Template_talk', 'WikiProject', 'Talk', 'User', 'User_talk',
                         'Wikipedia', 'Help', 'File', 'Category', 'Portal', 'MediaWiki',
                         'Book', 'Draft', 'Module', 'TimedText', 'Gadget']
        for p in skip_prefixes:
            if fname.startswith(p):
                return True
        return False

    def process_json_file(self, json_path):
        """
        处理单个 _html.json 文件

        流程:
            HTML → clean → infobox → sections → sentences
            → rule triples → section chunks → 保存
        """
        parsed, error = self.preprocessor.process_json_file(json_path)
        if error or not parsed:
            self._report(f"[跳过] {error}")
            return 0, 0

        page_title = normalize_to_simplified(parsed['title']).strip()
        triples = []
        narratives = []

        # ---- 三元组（Infobox + 正文规则，固定 ontology） ----
        for t in parsed.get('all_triples', []):
            if self.triple_builder.add_triple(t, page_title):
                triples.append(t)

        # ---- Embedding chunks（按 section 分块） ----
        embedding_chunks = parsed.get('embedding_chunks', [])
        chunk_narratives = WikiPreprocessor.chunks_to_narratives(
            embedding_chunks,
            page_title,
            source_name=(parsed or {}).get("source") or self.source_name,
            source_role=(parsed or {}).get("source_role") or self.source_role,
            schema_version=(parsed or {}).get("schema_version") or self.schema_version,
        )
        for chunk in chunk_narratives:
            if self.triple_builder.add_narrative(chunk):
                narratives.append(chunk)

        # ---- 保存 ----
        safe_title = self._sanitize(page_title)
        if triples:
            self.triple_builder.save_triples(safe_title, triples)
        if narratives:
            self.triple_builder.save_narratives(safe_title, narratives)

        stats = parsed.get('stats', {})
        self._report(
            f"  [{page_title}] "
            f"sections={stats.get('sections', 0)}, "
            f"triples={len(triples)}, "
            f"chunks={len(narratives)}"
        )

        return len(triples), len(narratives)

    def _save_narratives(self, safe_title, narratives):
        """保存叙事 chunks 到 JSON（ChromaStore 兼容格式）"""
        path = os.path.join(self.triples_dir, f'{safe_title}_narratives.json')
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(narratives, f, ensure_ascii=False, indent=2)
        return path

    def _sanitize(self, name):
        name = normalize_to_simplified(name).strip()
        return re.sub(
            r'[\\/:*?"<>|？！：；，。、【】「」『』《》（）→←↑↓"\x27\u2019\u0305]',
            '_', name
        )

    def process_all(self):
        """处理 data/raw_json 下所有 _html.json 文件"""
        raw_dir = self.raw_json_dir

        if not os.path.exists(raw_dir):
            self._report(f"[错误] 目录不存在: {raw_dir}")
            return 0, 0

        json_files = [f for f in os.listdir(raw_dir) if f.endswith('_html.json')]
        if not json_files:
            self._report("[错误] 没有找到 _html.json 文件，请先运行爬虫")
            return 0, 0

        filtered = [f for f in json_files if not self._should_skip_json(f)]
        skipped_count = len(json_files) - len(filtered)
        json_files = filtered

        total_triples = 0
        total_narratives = 0
        total = len(json_files)
        no_html_count = 0

        self._report(
            f"[NLP启动] 发现 {total} 个 _html.json 文件"
            f"（跳过 {skipped_count} 个非条目文件）"
        )

        for i, fname in enumerate(json_files):
            fpath = os.path.join(raw_dir, fname)
            self._report(f"[{i+1}/{total}] 处理: {fname}")

            # 预检：旧版纯 text 数据需重新爬取
            try:
                with open(fpath, 'r', encoding='utf-8') as f:
                    peek = json.load(f)
                if not peek.get('html'):
                    no_html_count += 1
                    self._report(
                        f"  [跳过] '{peek.get('title', fname)}' "
                        f"缺少 html 字段，请重新运行爬虫"
                    )
                    continue
            except Exception:
                pass

            t, n = self.process_json_file(fpath)
            total_triples += t
            total_narratives += n

            if (i + 1) % 50 == 0:
                self._report(
                    f"[进度] 已处理 {i+1}/{total} 个文件，"
                    f"累计 {total_triples} 个三元组"
                )
                self._save_summary(total_triples, total_narratives, total)

        if no_html_count:
            self._report(
                f"[警告] {no_html_count} 个文件缺少 html 字段，"
                f"需重新爬取后才能使用新 pipeline"
            )

        self._report(
            f"[NLP完成] 共计 {total_triples} 个三元组, "
            f"{total_narratives} 个 embedding chunks"
        )
        self._save_summary(total_triples, total_narratives, total)

        return total_triples, total_narratives

    def _save_summary(self, total_triples, total_narratives, total_files):
        """保存处理摘要"""
        summary_path = os.path.join(self.triples_dir, 'summary.json')
        with open(summary_path, 'w', encoding='utf-8') as f:
            json.dump({
                'total_triples': total_triples,
                'total_narratives': total_narratives,
                'total_files': total_files,
                'pipeline': 'preprocess_v2',
                'active_source': ACTIVE_SOURCE,
                'source_registry': SOURCE_REGISTRY,
                'source_schema_version': self.schema_version,
                'time': time.strftime('%Y-%m-%d %H:%M:%S'),
            }, f, ensure_ascii=False, indent=2)

    def process_txt_file(self, filepath):
        """[已废弃] 处理TXT文件 - 请改用 process_json_file"""
        self._report("[废弃] TXT文件处理已废弃，请使用 _html.json 文件")
        return 0, 0

    def process_all_txt(self):
        """[已废弃] 处理所有TXT文件 - 请改用 process_all"""
        self._report("[废弃] TXT文件批量处理已废弃，请使用 process_all()")
        return 0, 0
