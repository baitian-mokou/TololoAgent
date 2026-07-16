"""
LEGACY / DEPRECATED.

Historical HTML/Wikitext parser retained only to avoid destructive deletion.
Do not wire this module into the current frozen single-source baseline.
The active extraction path is `NlpPipeline -> WikiPreprocessor`.
"""
import re
import json
import os


class HtmlParser:
    """解析 _html.json 的 text 字段，提取结构化信息"""

    def __init__(self):
        # 叙事章节关键词（匹配章节标题）
        self.narrative_section_keywords = [
            '历史', '发现', '观测', '探测', '故事', '传说', '神话',
            '命名', '名称', '词源', '辞源', '由来',
            '任务', '计划', '探索', '研究',
            '记录', '大事记', '年表', '时间线',
            '背景', '文化', '艺术', '文学',
        ]
        # 事实章节关键词
        self.factual_section_keywords = [
            '物理', '轨道', '参数', '特征', '构造', '结构', '组成',
            '化学', '大气', '气候', '温度', '磁场', '引力',
            '地质', '地形', '表面', '内部', '分层',
            '分类', '类型', '光谱', '亮度', '质量', '半径',
            '卫星', '环', '系统',
        ]
        # 丢弃章节关键词
        self.discard_section_keywords = [
            '参考', '来源', '外部链接', '参见', '相关条目',
            '注释', '脚注', '引用', '书目',
            '规范控制', '分类', '导航', '模板',
        ]

    def parse_json_file(self, json_path):
        """加载并解析一个 _html.json 文件"""
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            return None, str(e)

        title = data.get('title', 'unknown')
        category = data.get('category', 'unknown')
        raw_text = data.get('text', '')

        if not raw_text:
            return None, f"'{title}' 的 text 字段为空"

        result = self.parse(raw_text, title)
        result['category'] = category
        result['file_path'] = json_path
        return result, None

    def parse(self, raw_text, page_title=''):
        """
        解析维基百科HTML/wikitext文本

        Args:
            raw_text: _html.json 中的 text 字段
            page_title: 页面标题

        Returns:
            dict: {
                'title': 标题,
                'infobox': {参数名: 值} 或 None,
                'sections': [(标题, 文本, 类型: factual/narrative/discard), ...],
                'full_text': 清洗后的完整文本,
                'stats': {总段数, 事实段, 叙事段, 丢弃段}
            }
        """
        result = {
            'title': page_title,
            'infobox': None,
            'sections': [],
            'full_text': '',
            'stats': {
                'total_sections': 0,
                'factual_sections': 0,
                'narrative_sections': 0,
                'discard_sections': 0,
            }
        }

        text = raw_text

        # 第一步：提取信息框 (Infobox)
        infobox = self._extract_infobox(text)
        if infobox:
            result['infobox'] = infobox

        # 第二步：清洗文本（移除维基标记、HTML标签、引用等）
        clean_text = self._clean_wikitext(text)
        result['full_text'] = clean_text

        # 第三步：按章节分割
        sections = self._split_sections(clean_text)
        result['sections'] = sections

        # 第四步：统计
        for _, _, s_type in sections:
            result['stats']['total_sections'] += 1
            if s_type == 'factual':
                result['stats']['factual_sections'] += 1
            elif s_type == 'narrative':
                result['stats']['narrative_sections'] += 1
            else:
                result['stats']['discard_sections'] += 1

        return result

    def _extract_infobox(self, text):
        """
        从维基文本中提取信息框（Infobox）
        """
        infobox = {}

        # 找到第一个章节标记前的文本（即页面开头的信息框区域）
        first_section = re.search(r'^={2,}', text, re.MULTILINE)
        if first_section:
            header_area = text[:first_section.start()]
        else:
            header_area = text[:min(10000, len(text))]

        # 匹配 {{Infobox ... }} 块
        infobox_start = header_area.find('{{Infobox')
        if infobox_start == -1:
            infobox_start = header_area.find('{{信息框')

        if infobox_start != -1:
            # 找到匹配的 }} 关闭
            depth = 2
            i = infobox_start + 2
            while i < len(header_area) and depth > 0:
                if header_area[i:i+2] == '{{':
                    depth += 1
                    i += 2
                elif header_area[i:i+2] == '}}':
                    depth -= 1
                    i += 2
                else:
                    i += 1
            ib_text = header_area[infobox_start:i]

            # 提取键值对
            lines = ib_text.split('\n')
            for line in lines:
                line = line.strip()
                kv_match = re.match(r'\|\s*([^=]+?)\s*=\s*(.+)', line)
                if kv_match:
                    key = kv_match.group(1).strip()
                    value = kv_match.group(2).strip()
                    value = re.sub(r'<[^>]+>', '', value)
                    value = re.sub(r'\[\[([^\]|]+)(?:\|[^\]]+)?\]\]', r'\1', value)
                    value = re.sub(r'\{\{[^}]+}}', '', value)
                    value = value.strip()
                    if key and value and len(value) < 200 and len(key) <= 20:
                        skip_keys = ['主条目', '参见', '分类', '注', '注释', '上图', '下图', '图片', '图注', '名称']
                        if key not in skip_keys:
                            infobox[key] = value

        return infobox if infobox else None

    def _clean_wikitext(self, text):
        """清洗维基文本，移除标记和噪音"""
        # 1. 移除 <ref>...</ref> 完整引用
        text = re.sub(r'<ref[^>]*>.*?</ref>', '', text, flags=re.DOTALL)
        text = re.sub(r'<ref[^>]*/>', '', text)

        # 2. 移除 <nowiki> ... </nowiki>
        text = re.sub(r'<nowiki>.*?</nowiki>', '', text, flags=re.DOTALL)

        # 3. 移除 <gallery> ... </gallery>
        text = re.sub(r'<gallery[^>]*>.*?</gallery>', '', text, flags=re.DOTALL)

        # 4. 移除 {{Infobox ... }} 信息框（已提取）
        text = re.sub(r'\{\{\s*[Ii]nfo[Bb]ox[^}]*?\}\}', '', text, flags=re.DOTALL)

        # 5. 移除 {{...}} 模板（嵌套处理，最多5层）
        for _ in range(5):
            text = re.sub(r'\{\{[^{}]*?\}\}', '', text)

        # 6. 移除 HTML 标签
        text = re.sub(r'<[^>]+>', '', text)

        # 7. 处理 [[链接]]
        text = re.sub(r'\[\[([^\]|]+)(?:\|[^\]]+)?\]\]', r'\1', text)

        # 8. 移除 [编号]
        text = re.sub(r'\[\d+(?:\.\d+)?\]', '', text)

        # 9. 移除 [编辑] 标记
        text = re.sub(r'\[编辑\]', '', text)

        # 10. 移除多余空白
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = re.sub(r' {2,}', ' ', text)

        return text.strip()

    def _split_sections(self, text):
        """
        按段落分割文本，检测关键词进行分类
        """
        sections = []
        paragraphs = re.split(r'\n{2,}', text)
        paragraphs = [p.strip() for p in paragraphs if p.strip()]

        if not paragraphs:
            return sections

        current_label = ''
        current_text = ''

        for para in paragraphs:
            if self._is_section_title(para):
                if current_text:
                    sections.append((current_label, current_text.strip(),
                                     self._classify_section(current_label)))
                current_label = para[:30]
                current_text = ''
            else:
                current_text += '\n' + para

        if current_text.strip():
            sections.append((current_label, current_text.strip(),
                             self._classify_section(current_label)))

        sections = [(t, txt, st) for t, txt, st in sections if len(txt) >= 50]
        return sections

    def _is_section_title(self, para):
        """检测段落是否是章节标题"""
        if len(para) > 80:
            return False
        all_keywords = (self.factual_section_keywords +
                        self.narrative_section_keywords +
                        self.discard_section_keywords +
                        ['主条目', '參見', '相关条目', '相關條目'])
        for kw in all_keywords:
            if kw in para:
                return True
        return False

    def _classify_section(self, label):
        """根据标签判断段落类型: factual / narrative / discard"""
        if not label:
            return 'factual'
        for kw in self.discard_section_keywords:
            if kw in label:
                return 'discard'
        for kw in self.narrative_section_keywords:
            if kw in label:
                return 'narrative'
        return 'factual'

    def get_infobox_triples(self, parsed_result, page_title):
        """从信息框中提取属性三元组"""
        triples = []
        infobox = parsed_result.get('infobox')
        if not infobox:
            return triples
        for key, value in infobox.items():
            if key and value:
                triples.append({
                    'subject': page_title,
                    'relation': '拥有' + key,
                    'object': value,
                    'pattern': 'infobox',
                    'raw': f'{key}: {value}',
                    'source': page_title,
                })
        return triples

    def get_factual_sections(self, parsed_result):
        """获取所有事实章节"""
        return [(t, txt) for t, txt, st in parsed_result.get('sections', [])
                if st == 'factual']

    def get_narrative_sections(self, parsed_result):
        """获取所有叙事章节"""
        return [(t, txt) for t, txt, st in parsed_result.get('sections', [])
                if st == 'narrative']
