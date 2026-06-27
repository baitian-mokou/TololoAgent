"""
LEGACY / DEPRECATED.

Historical narrative processor retained only for reference.
Do not use in the current frozen single-source baseline.
Narrative chunk generation now lives in `preprocess.py` and `triple_builder.py`.
"""
import re
import json
import os
import hashlib


class NarrativeProcessor:
    """处理叙事性章节文本：清洗、分块、关键词提取"""

    def __init__(self, output_dir=None):
        self.output_dir = output_dir
        self.narratives = []

    def process_section(self, section_title, section_text, page_title):
        """
        处理单个叙事章节

        Args:
            section_title: 章节标题
            section_text: 章节文本
            page_title: 页面标题

        Returns:
            list of chunk dicts
        """
        chunks = []

        # 1. 清洗文本
        clean_text = self._clean_narrative_text(section_text)

        if not clean_text or len(clean_text) < 100:
            return chunks

        # 2. 分块（300-800字）
        raw_chunks = self._chunk_text(clean_text, min_chars=300, max_chars=800)

        # 3. 提取关键词
        keywords = self._extract_keywords(clean_text)

        for i, chunk_text in enumerate(raw_chunks):
            chunk = {
                'page_title': page_title,
                'section': section_title,
                'chunk_index': i,
                'content': chunk_text,
                'keywords': keywords,
                'source': page_title,
                'chunk_id': self._make_chunk_id(page_title, section_title, i),
            }
            chunks.append(chunk)
            self.narratives.append(chunk)

        return chunks

    def save_narratives(self, title, chunks, output_dir=None):
        """将叙事chunks保存为JSON"""
        save_dir = output_dir or self.output_dir
        if not save_dir:
            return False

        os.makedirs(save_dir, exist_ok=True)
        safe_name = re.sub(r'[\\/:*?"<>|？！：；，。、【】「」『』《》（）→←↑↓"\']', '_', title)
        filepath = os.path.join(save_dir, f'{safe_name}_narratives.json')

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(chunks, f, ensure_ascii=False, indent=2)

        return True

    def get_all_narratives(self):
        """获取所有已处理的叙事chunks"""
        return self.narratives

    def _clean_narrative_text(self, text):
        """清洗叙事文本：保留可读性，去除噪音"""
        # 1. 移除 <ref> 标记
        text = re.sub(r'<ref[^>]*>.*?</ref>', '', text, flags=re.DOTALL)

        # 2. 移除维基模板 {{{{...}}}}
        for _ in range(3):
            text = re.sub(r'\{\{[^{}]*?\}\}', '', text)

        # 3. 处理 [[链接]] (保留显示文本)
        text = re.sub(r'\[\[([^\]|]+)(?:\|[^\]]+)?\]\]', r'\1', text)

        # 4. 移除 HTML 标签
        text = re.sub(r'<[^>]+>', '', text)

        # 5. 移除 [数字] 引用标记
        text = re.sub(r'\[\d+(?:\.\d+)?\]', '', text)

        # 6. 移除 [编辑] 标记
        text = re.sub(r'\[编辑\]', '', text)

        # 7. 移除纯数字或符号行
        lines = text.split('\n')
        clean_lines = []
        for line in lines:
            line = line.strip()
            # 跳过空行
            if not line:
                continue
            # 跳过纯数字/符号行
            if re.fullmatch(r'[\d\s.,;:!?\-—–()\[\]{}]+\'*', line.strip()):
                continue
            # 跳过太短的行
            if len(line) < 10:
                continue
            clean_lines.append(line)

        text = '\n'.join(clean_lines)

        # 8. 合并空白
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = re.sub(r' {2,}', ' ', text)

        return text.strip()

    def _chunk_text(self, text, min_chars=300, max_chars=800):
        """将文本切分为合适的chunks"""
        if len(text) <= max_chars:
            return [text] if len(text) >= min_chars else []

        chunks = []
        # 优先在句子边界切割
        sentences = re.split(r'(?<=[。！？；\n])\s*', text)

        current_chunk = ''
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue

            if len(current_chunk) + len(sentence) <= max_chars:
                current_chunk += sentence
            else:
                if current_chunk and len(current_chunk) >= min_chars:
                    chunks.append(current_chunk.strip())
                # 新chunk从当前句子开始
                current_chunk = sentence

        # 最后一段
        if current_chunk and len(current_chunk) >= min_chars:
            chunks.append(current_chunk.strip())

        # 如果某段太短，合并到前一段
        merged = []
        for chunk in chunks:
            if merged and len(chunk) < min_chars:
                merged[-1] += chunk
            else:
                merged.append(chunk)

        return merged if merged else ([text] if len(text) >= min_chars else [])

    def _extract_keywords(self, text, top_k=10):
        """提取关键词（使用jieba TF-IDF）"""
        try:
            import jieba.analyse
            keywords = jieba.analyse.extract_tags(text, topK=top_k)
            return keywords
        except ImportError:
            # jieba 不可用时，简单的基于频率的关键词提取
            words = re.findall(r'[\u4e00-\u9fff]{2,}', text)
            freq = {}
            for w in words:
                freq[w] = freq.get(w, 0) + 1
            sorted_words = sorted(freq.items(), key=lambda x: -x[1])
            return [w for w, c in sorted_words[:top_k]]

    @staticmethod
    def _make_chunk_id(page_title, section_title, index):
        """生成唯一的chunk ID"""
        raw = f'{page_title}_{section_title}_{index}'
        return hashlib.md5(raw.encode()).hexdigest()[:12]
