"""
LEGACY / DEPRECATED.

Historical segmenter retained only for reference.
Do not use in the current frozen single-source baseline hot path.
"""
import os
import jieba
import jieba.posseg as pseg


class Segmenter:
    """分词器，支持词性标注和中英混合词保护"""

    def __init__(self, dict_path=None):
        self.dict_path = dict_path
        # 加载天文自定义词典
        if dict_path and os.path.exists(dict_path):
            jieba.load_userdict(dict_path)
        # 中英混合词保护列表
        self.mixed_terms = {
            'TRAPPIST-1', 'HD 209458 b', 'Gliese 581g', '51 Pegasi b',
            'C/2020 F3', '2010 TK7', '2020 XL5', '2006 RH120',
            'HD 209458', 'PSR B1257+12',
        }

    def segment(self, text):
        """返回分词列表"""
        protected_text = self._protect_mixed_terms(text)
        return list(jieba.cut(protected_text, cut_all=False))

    def segment_with_pos(self, text):
        """返回带词性标注的 (词语, 词性) 列表"""
        protected_text = self._protect_mixed_terms(text)
        return list(pseg.cut(protected_text))

    def _protect_mixed_terms(self, text):
        """对中英混合词进行预处理保护，防止被jieba切碎"""
        for term in self.mixed_terms:
            if term in text:
                protected = term.replace(' ', '_')
                text = text.replace(term, protected)
        return text
