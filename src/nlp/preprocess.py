"""
Wikipedia 数据预处理 Pipeline

Wikipedia HTML → HTML Cleaner → DOM 结构保留
→ Infobox Parser → Section Extractor → Sentence Segmenter
→ Triple Extractor → Narrative Chunk Generator

该模块是 Tololo Agent 的知识抽取入口。它不调用 LLM，
只基于 Wikipedia HTML 结构和固定 ontology 生成 Neo4j / Chroma
兼容数据。
"""
import hashlib
import json
import re
from bs4 import BeautifulSoup, NavigableString, Tag

from src.source_control import (
    ACTIVE_SOURCE,
    RECORD_TYPE_EMBEDDING_CHUNK,
    RECORD_TYPE_TRIPLE_CANDIDATE,
    apply_record_metadata,
    get_single_source_baseline_namespace,
    normalize_origin,
)

from .ontology import normalize_infobox_key, make_triple, split_atmosphere_components, validate_triple
from .text_normalizer import normalize_to_simplified


SECTION_STOP_MARKERS = frozenset({
    '参考资料', '參考資料', '参考文献', '參考文獻',
    '外部链接', '外部連結', '参见', '參見',
    '相关条目', '相關條目', '注释', '註釋',
    '脚注', '腳註', '延伸阅读', '延伸閱讀',
})

DISCARD_KEYWORDS = (
    '参考', '參考', '来源', '來源', '外部链接', '外部連結',
    '参见', '參見', '注释', '註釋', '脚注', '腳註',
    '书目', '書目', '规范控制', '導航', '导航',
)

NOISE_SELECTORS = (
    'sup.reference',
    'table.navbox',
    'div.reflist',
    'span.mw-editsection',
    'script',
    'style',
    'noscript',
    'ol.references',
    'div.references',
    'div.navbox',
    'div.navbox-styles',
    'div.noprint',
    'div.metadata',
    'div.hatnote',
    'div.dablink',
    'div.shortdescription',
    'div.sistersitebox',
    'div#toc',
    'div#catlinks',
)

VALUE_UNITS = (
    'kg', '千克', '公斤', '吨', '噸', '地球质量', '地球質量',
    '木星质量', '木星質量', 'M⊕', 'M♃', '公里', '千米', 'km',
    'KM', '米', 'm', 'AU', '天文单位', '天文單位',
)

CANONICAL_RADIUS_RE = re.compile(
    r'\d[\d,]*(?:\.\d+)?\s*(?:公里|千米|km|KM|米|m)'
)
CANONICAL_MASS_RE = re.compile(
    r'\d[\d,]*(?:\.\d+)?(?:\s+\d+)?(?:\s*[×xX]\s*10\s*[+\-−]?\s*\d+)?\s*'
    r'(?:kg|千克|公斤|吨|噸|太阳质量|太陽質量|地球质量|地球質量|木星质量|木星質量|M⊕|M♃)'
)
VALUE_WITH_UNCERTAINTY_RE = re.compile(
    r'(\d[\d,]*(?:\.\d+)?)\s*±\s*\d[\d,]*(?:\.\d+)?\s*'
    r'(kg|吨|噸|太阳质量|地球质量|木星质量|km|KM|米|m|AU|M⊕|M♃)',
    flags=re.IGNORECASE,
)

ASTRO_ENTITY_PATTERN = r'[\u4e00-\u9fffA-Za-z0-9][\u4e00-\u9fffA-Za-z0-9\s+\-·]{1,39}'
ASTRO_CONTAINER_PATTERN = r'[\u4e00-\u9fffA-Za-z0-9][\u4e00-\u9fffA-Za-z0-9\s+\-·]{1,39}(?:系统|系統)?'
LOCATION_OBJECT_PATTERN = (
    r'(?:本星系群|'
    r'[\u4e00-\u9fffA-Za-z0-9][\u4e00-\u9fffA-Za-z0-9\s+\-·]{1,39}'
    r'(?:星系群|星系团|星系團|太阳系|太陽系|银河系|銀河系|宇宙|带|帶|区域|區域|轨道|軌道|星座|星系))'
)
DISCOVERER_PATTERN = r'[\u4e00-\u9fffA-Za-z][\u4e00-\u9fffA-Za-z0-9\s.\-·+]{1,59}'


class WikiPreprocessor:
    """Wikipedia HTML 结构化预处理器。"""

    def __init__(self, source_name=None, source_role=None, schema_version=None):
        self.source_name = source_name or get_single_source_baseline_namespace()
        self.source_name = self.source_name or ACTIVE_SOURCE
        self.source_role = source_role
        self.schema_version = schema_version

    # 正文规则模板: (pattern, relation, subject_group, object_group)
    TEXT_RULES = [
        # HAS_RADIUS
        (r'([\u4e00-\u9fffA-Za-z0-9\-·]{2,20})(?:的)?(?:平均)?(?:赤道)?半径(?:约为|約為|为|為|是|：|:)?\s*([0-9][0-9,.\s]*\s*(?:公里|千米|km|KM))', 'HAS_RADIUS', 1, 2),
        (r'([\u4e00-\u9fffA-Za-z0-9\-·]{2,20})(?:的)?(?:平均)?(?:赤道)?半徑(?:约为|約為|为|為|是|：|:)?\s*([0-9][0-9,.\s]*\s*(?:公里|千米|km|KM))', 'HAS_RADIUS', 1, 2),
        # HAS_MASS
        (r'([\u4e00-\u9fffA-Za-z0-9\-·]{2,20})(?:的)?质量(?:约为|約為|为|為|是|：|:)?\s*([0-9][0-9,.×xX\^\-\+\s]*\s*(?:kg|千克|公斤|吨|噸|地球质量|地球質量|木星质量|木星質量|M⊕|M♃))', 'HAS_MASS', 1, 2),
        (r'([\u4e00-\u9fffA-Za-z0-9\-·]{2,20})(?:的)?質量(?:约为|約為|为|為|是|：|:)?\s*([0-9][0-9,.×xX\^\-\+\s]*\s*(?:kg|千克|公斤|吨|噸|地球质量|地球質量|木星质量|木星質量|M⊕|M♃))', 'HAS_MASS', 1, 2),
        # HAS_ATMOSPHERE
        (r'([\u4e00-\u9fffA-Za-z0-9\-·]{2,20})(?:的)?大[气氣][层層]?(?:主要)?(?:由|以)([^。；]{2,80}?)(?:组成|組成|为主|為主)', 'HAS_ATMOSPHERE', 1, 2),
        (r'([\u4e00-\u9fffA-Za-z0-9\-·]{2,20})(?:的)?大[气氣][层層]?(?:成分)?(?:为|為|是|：|:)\s*([^。；]{2,80})', 'HAS_ATMOSPHERE', 1, 2),
        # ORBITS
        (rf'({ASTRO_ENTITY_PATTERN})(?:绕|繞|围绕|圍繞|环绕|環繞)({ASTRO_ENTITY_PATTERN})(?:公转|公轉|运行|運行)', 'ORBITS', 1, 2),
        (rf'({ASTRO_ENTITY_PATTERN})是({ASTRO_ENTITY_PATTERN}?)(?:的)?(?:天然)?(?:卫星|衛星)', 'ORBITS', 1, 2),
        # IS_A
        (r'([\u4e00-\u9fffA-Za-z0-9\-·]{2,20})是(?:一颗|一顆|一个|一個)?([^。；，,]{2,30}?(?:行星|恒星|恆星|卫星|衛星|彗星|小行星|矮行星|天体|天體))', 'IS_A', 1, 2),
        (r'([\u4e00-\u9fffA-Za-z0-9\-·]{2,20})(?:属于|屬於|被分类为|被分類為)([^。；，,]{2,30}?(?:行星|恒星|恆星|卫星|衛星|彗星|小行星|矮行星|天体|天體|类型|類型))', 'IS_A', 1, 2),
        # PART_OF
        (rf'({ASTRO_ENTITY_PATTERN})是({ASTRO_ENTITY_PATTERN})(?:的)?(?:组成部分|組成部分|成员|成員)', 'PART_OF', 1, 2),
        (rf'({ASTRO_ENTITY_PATTERN})(?:属于|屬於)({ASTRO_CONTAINER_PATTERN})(?=的一部分)(?:的一部分)', 'PART_OF', 1, 2),
        (rf'({ASTRO_ENTITY_PATTERN})(?:属于|屬於)({ASTRO_CONTAINER_PATTERN})', 'PART_OF', 1, 2),
        # LOCATED_IN
        (rf'({ASTRO_ENTITY_PATTERN})位(?:于|於|在)({LOCATION_OBJECT_PATTERN})', 'LOCATED_IN', 1, 2),
        (rf'({ASTRO_ENTITY_PATTERN})处(?:于|於|在)({LOCATION_OBJECT_PATTERN}|[\u4e00-\u9fffA-Za-z0-9][\u4e00-\u9fffA-Za-z0-9\s+\-·]{{1,39}}(?:宜居带|宜居帶))', 'LOCATED_IN', 1, 2),
        # DISCOVERED_BY
        (rf'({ASTRO_ENTITY_PATTERN})(?:于|於)\s*\d{{3,4}}\s*年.*?被({DISCOVERER_PATTERN})(?:发现|發現)', 'DISCOVERED_BY', 1, 2),
        (rf'({ASTRO_ENTITY_PATTERN})由({DISCOVERER_PATTERN})(?:于|於)?.*?(?:发现|發現)', 'DISCOVERED_BY', 1, 2),
        (rf'(?:^|[，,；;。]\s*)((?!(?:年|月|日)\s){DISCOVERER_PATTERN})(?:发现|發現)了?({ASTRO_ENTITY_PATTERN})', 'DISCOVERED_BY', 2, 1),
    ]

    def process_json_data(self, data):
        """
        处理 spider.py 保存的 JSON 对象。

        Returns:
            (result, error)
        """
        title = normalize_to_simplified(data.get('title', 'unknown')).strip()
        category = data.get('category', 'unknown')
        html = data.get('html', '')

        if not html:
            return None, f"'{title}' 缺少 html 字段，请重新爬取"

        soup = self.clean_html(html)
        infobox_fields = self.extract_infobox_fields(soup)
        infobox_triples = self.extract_infobox(soup, title)
        sections = self.extract_sections(soup)
        sentences = self.segment_sentences(sections)
        section_triples = self.extract_triples(title, sections, sentences)
        origin = self._resolve_record_origin(data)
        infobox_triples = [
            apply_record_metadata(
                triple,
                origin,
                RECORD_TYPE_TRIPLE_CANDIDATE,
                source_name=(data or {}).get("source") or self.source_name,
                source_role=(data or {}).get("source_role") or self.source_role,
                source_title=title,
                extra={"schema_version": (data or {}).get("schema_version") or self.schema_version} if ((data or {}).get("schema_version") or self.schema_version) else None,
            )
            for triple in infobox_triples
        ]
        section_triples = [
            apply_record_metadata(
                triple,
                origin,
                RECORD_TYPE_TRIPLE_CANDIDATE,
                source_name=(data or {}).get("source") or self.source_name,
                source_role=(data or {}).get("source_role") or self.source_role,
                source_title=title,
                extra={"schema_version": (data or {}).get("schema_version") or self.schema_version} if ((data or {}).get("schema_version") or self.schema_version) else None,
            )
            for triple in section_triples
        ]
        all_triples = self._dedupe_triples(infobox_triples + section_triples)
        embedding_chunks = self.chunk_for_embedding(
            title,
            sections,
            origin=origin,
            source_name=(data or {}).get("source") or self.source_name,
            source_role=(data or {}).get("source_role") or self.source_role,
            schema_version=(data or {}).get("schema_version") or self.schema_version,
        )

        return {
            'title': title,
            'category': category,
            'infobox': infobox_fields,
            'sections': sections,
            'sentences': sentences,
            'infobox_triples': infobox_triples,
            'section_triples': section_triples,
            'all_triples': all_triples,
            'embedding_chunks': embedding_chunks,
            'stats': {
                'infobox_fields': len(infobox_fields),
                'sections': len(sections),
                'sentences': len(sentences),
                'triples': len(all_triples),
                'chunks': len(embedding_chunks),
            },
        }, None

    def process_json_file(self, json_path):
        """加载并处理 spider 输出的 _html.json 文件。"""
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            return None, str(e)

        result, err = self.process_json_data(data)
        if result:
            result['file_path'] = json_path
        return result, err

    @staticmethod
    def _resolve_record_origin(data):
        return normalize_origin(
            (data or {}).get('origin')
            or (data or {}).get('fetch_source')
            or (data or {}).get('source')
        )

    @staticmethod
    def clean_html(html_or_soup):
        """
        清洗 HTML，删除引用/导航/脚本等噪音，但保留正文 DOM 结构。

        删除:
            sup.reference, table.navbox, div.reflist,
            span.mw-editsection, script, style, noscript
        """
        if isinstance(html_or_soup, BeautifulSoup):
            soup = html_or_soup
        else:
            soup = BeautifulSoup(html_or_soup or '', 'lxml')

        tags_to_remove = []
        for selector in NOISE_SELECTORS:
            tags_to_remove.extend(soup.select(selector))

        for tag in tags_to_remove:
            if getattr(tag, 'attrs', None) is not None:
                tag.decompose()

        # Wikipedia class 可能是列表，select 覆盖不到的异常形态再扫一遍。
        tags_to_remove = []
        for tag in soup.find_all(['sup', 'table', 'div', 'span']):
            if getattr(tag, 'attrs', None) is None:
                continue
            classes = tag.get('class') or []
            class_text = ' '.join(classes) if isinstance(classes, list) else str(classes)
            if (
                tag.name == 'sup' and 'reference' in class_text
                or tag.name == 'table' and 'navbox' in class_text
                or tag.name == 'div' and 'reflist' in class_text
                or tag.name == 'span' and 'mw-editsection' in class_text
            ):
                tags_to_remove.append(tag)

        for tag in tags_to_remove:
            if getattr(tag, 'attrs', None) is not None:
                tag.decompose()

        return soup

    @staticmethod
    def _text_from_cell(cell):
        """提取表格单元格文本，保留上下标和单位。"""
        if not cell:
            return ''

        for br in cell.find_all('br'):
            br.replace_with(' ')
        for tag in cell.find_all(['sup', 'sub']):
            tag.replace_with(tag.get_text('', strip=True))

        text = cell.get_text(' ', strip=True)
        text = re.sub(r'\[\d+(?:\.\d+)?\]', '', text)
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    @staticmethod
    def _clean_key(key):
        key = normalize_to_simplified(key or '')
        key = re.sub(r'\[编辑\]|\[編輯\]', '', key)
        key = re.sub(r'\s+', '', key)
        key = key.strip('：: ')
        return key

    @staticmethod
    def _clean_value(value):
        value = normalize_to_simplified(value or '')
        value = re.sub(r'\[\d+(?:\.\d+)?\]', '', value)
        value = re.sub(r'\s+', ' ', value)
        value = value.strip('：: ，,。;；')
        return value

    def extract_infobox_fields(self, soup):
        """
        解析 <table class="infobox">，返回原始键值字段。

        Returns:
            list[dict]: [{key, value, relation}]
        """
        if isinstance(soup, str):
            soup = BeautifulSoup(soup, 'lxml')

        table = soup.find('table', class_=lambda c: c and 'infobox' in c)
        if not table:
            return []

        fields = []
        skip_keys = {
            '名称', '圖片', '图片', '图像', '圖像', '图注', '圖注',
            '主条目', '主條目', '参见', '參見', '注释', '註釋',
        }

        for tr in table.find_all('tr'):
            parent_table = tr.find_parent('table')
            if parent_table is not table:
                continue

            th = tr.find('th', recursive=False)
            td = tr.find('td', recursive=False)
            if not th or not td:
                continue

            key = self._clean_key(self._text_from_cell(th))
            value = self._clean_value(self._text_from_cell(td))
            if not key or not value:
                continue
            if key in skip_keys or len(key) > 30 or len(value) > 500:
                continue

            relation = normalize_infobox_key(key)
            fields.append({
                'key': key,
                'value': value,
                'relation': relation,
            })

        return fields

    def extract_infobox(self, soup, page_title):
        """
        专门解析 table.infobox 并直接生成 ontology 三元组。

        示例:
            <th>质量</th><td>6.39×10^23 kg</td>
            → ("火星", "HAS_MASS", "6.39×10^23 kg")
        """
        triples = []
        for field in self.extract_infobox_fields(soup):
            relation = field.get('relation')
            if not relation:
                continue
            if relation == 'HAS_ATMOSPHERE':
                for component in split_atmosphere_components(field['value']):
                    triple = make_triple(
                        page_title,
                        relation,
                        component,
                        pattern='infobox',
                        raw=f"{field['key']}: {field['value']}",
                    )
                    if triple:
                        triples.append(triple)
                continue

            field_value = self._normalize_infobox_object(relation, field['value'])

            triple = make_triple(
                page_title,
                relation,
                field_value,
                pattern='infobox',
                raw=f"{field['key']}: {field['value']}",
            )
            if triple:
                triples.append(triple)
        return triples

    @staticmethod
    def _is_discard_section(title):
        title = normalize_to_simplified(title or '').strip()
        if not title:
            return False
        if title in SECTION_STOP_MARKERS:
            return True
        return any(keyword in title for keyword in DISCARD_KEYWORDS)

    @staticmethod
    def _is_heading_wrapper(tag):
        classes = tag.get('class') or []
        class_text = ' '.join(classes) if isinstance(classes, list) else str(classes)
        return 'mw-heading' in class_text

    @staticmethod
    def _visible_text(element):
        """从 DOM 元素提取可见正文，跳过 infobox/navbox 等非叙事内容。"""
        if isinstance(element, NavigableString):
            return re.sub(r'\s+', ' ', str(element)).strip()
        if not isinstance(element, Tag):
            return ''
        if element.name in ('script', 'style', 'noscript'):
            return ''

        classes = element.get('class') or []
        class_text = ' '.join(classes) if isinstance(classes, list) else str(classes)
        if element.name == 'table':
            return ''
        if any(x in class_text for x in (
            'infobox', 'navbox', 'reflist', 'reference', 'metadata',
            'noprint', 'mw-editsection', 'hatnote', 'dablink',
            'shortdescription'
        )):
            return ''

        if element.name in ('p', 'li', 'blockquote'):
            text = element.get_text(' ', strip=True)
            text = normalize_to_simplified(text)
            text = re.sub(r'\[\d+(?:\.\d+)?\]', '', text)
            text = re.sub(r'\s+', ' ', text).strip()
            return text

        parts = []
        for child in element.children:
            text = WikiPreprocessor._visible_text(child)
            if text:
                parts.append(text)
        return ' '.join(parts).strip()

    @staticmethod
    def _heading_anchor(heading):
        parent = heading.find_parent('div')
        if parent and WikiPreprocessor._is_heading_wrapper(parent):
            return parent
        return heading

    @staticmethod
    def _next_is_heading(tag):
        if not isinstance(tag, Tag):
            return False
        if tag.name in ('h1', 'h2', 'h3'):
            return True
        if WikiPreprocessor._is_heading_wrapper(tag):
            return bool(tag.find(['h1', 'h2', 'h3']))
        return False

    def _collect_until_next_heading(self, anchor):
        parts = []
        for sibling in anchor.next_siblings:
            if self._next_is_heading(sibling):
                break
            text = self._visible_text(sibling)
            if text and len(text) > 5:
                parts.append(text)
        return '\n'.join(parts)

    def _extract_intro(self, content, first_anchor):
        parts = []
        for child in content.children:
            if child is first_anchor:
                break
            if isinstance(child, Tag) and child.find(['h1', 'h2', 'h3']):
                break
            text = self._visible_text(child)
            if text and len(text) > 20:
                parts.append(text)
        intro = '\n'.join(parts).strip()
        return intro if len(intro) >= 20 else ''

    def extract_sections(self, soup):
        """
        按 h1 / h2 / h3 切分章节，保留 section path。

        Returns:
            list[dict]: [{section, level, text, path}]
        """
        if isinstance(soup, str):
            soup = BeautifulSoup(soup, 'lxml')

        content = soup.find('div', id='mw-content-text')
        if content:
            parser_output = content.find('div', class_=lambda c: c and 'mw-parser-output' in c)
            content = parser_output or content
        else:
            content = soup.find('div', class_=lambda c: c and 'mw-parser-output' in c) or soup

        headings = content.find_all(['h1', 'h2', 'h3'])
        sections = []

        if headings:
            first_anchor = self._heading_anchor(headings[0])
            intro = self._extract_intro(content, first_anchor)
            if intro:
                sections.append({
                    'section': '概要',
                    'level': 'intro',
                    'text': intro,
                    'path': '概要',
                })
        else:
            text = self._visible_text(content)
            if text:
                sections.append({
                    'section': '概要',
                    'level': 'intro',
                    'text': text,
                    'path': '概要',
                })
            return sections

        stack = {'h1': '', 'h2': '', 'h3': ''}
        for heading in headings:
            title = heading.get_text(' ', strip=True)
            title = normalize_to_simplified(title)
            title = re.sub(r'\[编辑\]|\[編輯\]', '', title).strip()
            if not title:
                continue
            if self._is_discard_section(title):
                break

            level = heading.name
            if level == 'h1':
                stack = {'h1': title, 'h2': '', 'h3': ''}
            elif level == 'h2':
                stack['h2'] = title
                stack['h3'] = ''
            elif level == 'h3':
                stack['h3'] = title

            path = ' > '.join(v for v in (stack['h1'], stack['h2'], stack['h3']) if v)
            anchor = self._heading_anchor(heading)
            body = self._collect_until_next_heading(anchor)
            body = re.sub(r'\n{3,}', '\n\n', body).strip()
            if len(body) < 10:
                continue

            sections.append({
                'section': title,
                'level': level,
                'text': body,
                'path': path or title,
            })

        return sections

    @staticmethod
    def segment_sentences(sections):
        """对 section 文本进行句子级切分。"""
        sentences = []
        for section in sections:
            text = section.get('text', '')
            for sentence in re.split(r'(?<=[。！？；;])\s*', text):
                sentence = re.sub(r'\s+', ' ', sentence).strip()
                sentence = normalize_to_simplified(sentence)
                if len(sentence) < 8:
                    continue
                if (
                    len(re.findall(r'[\u4e00-\u9fff]', sentence)) < 4
                    and not re.search(
                        r'(?:绕|繞|围绕|圍繞|环绕|環繞|公转|公轉|运行|運行|发现|發現|位于|位於|处于|處於|属于|屬於)',
                        sentence,
                    )
                ):
                    continue
                sentences.append({
                    'section': section.get('section', ''),
                    'section_path': section.get('path', ''),
                    'sentence': sentence,
                })
        return sentences

    @staticmethod
    def _clean_entity(name):
        name = normalize_to_simplified(name or '')
        name = re.sub(r'\s+', ' ', name or '')
        name = name.strip('，。、；：:（）()[]【】 ')
        name = re.sub(r'^(?:著|的)', '', name)
        name = re.sub(r'的$', '', name)
        name = re.sub(r'^(由于|由於|因为|因為|此外|另外|然而|而|但)', '', name)
        name = re.sub(r'(基本上|通常|一般|目前)$', '', name)
        stop_words = {
            '它', '其', '该', '該', '这个', '這個', '这种', '這種',
            '其中', '一个', '一個', '一种', '一種', '主要',
            '平均', '赤道', '由于', '由於', '可能', '或许', '或許',
        }
        if not name or name in stop_words:
            return ''
        if len(name) < 2 or len(name) > 40:
            return ''
        if re.search(r'[\\/<>={}]', name):
            return ''
        return name

    @staticmethod
    def _clean_object(value):
        value = normalize_to_simplified(value or '')
        value = re.sub(r'\s+', ' ', value or '')
        value = value.strip('，。、；;：: ')
        value = re.sub(r'^(是|为|為|约为|約為)', '', value)
        value = re.sub(r'^(由于|由於|因为|因為|例如|比如|导致|導致|所以|因此)\s*', '', value)
        value = re.sub(r'^(?:著|的|于|於|在)\s*', '', value)
        return value.strip()

    @staticmethod
    def _normalize_infobox_object(relation, value):
        value = normalize_to_simplified(value or '')
        value = value.replace('\xa0', ' ')
        value = re.sub(r'\d{6,}♠\s*', ' ', value)
        value = value.replace('千克', 'kg').replace('公斤', 'kg')
        value = value.replace('公里', 'km').replace('千米', 'km')
        value = value.replace('太陽質量', '太阳质量').replace('地球質量', '地球质量')
        value = value.replace('木星質量', '木星质量')
        value = value.replace('−', '-').replace('—', '-')
        value = VALUE_WITH_UNCERTAINTY_RE.sub(r'\1 \2', value)
        value = re.sub(r'[（(]\s*(\d[\d,.]*)\s*[±+-]\s*[\d,.]+\s*[)）]', r' \1 ', value)
        value = re.sub(r'[()（）]', ' ', value)
        value = re.sub(r'(?<=\d)\s+(?=\d\s*[×xX])', '', value)
        value = re.sub(r'\s+', ' ', value).strip('，。、；;：: ')
        if relation == 'HAS_RADIUS':
            match = CANONICAL_RADIUS_RE.search(value)
            if not match:
                return value
            return match.group(0).replace('KM', 'km').replace(',', '')
        if relation == 'HAS_MASS':
            match = CANONICAL_MASS_RE.search(value)
            if not match:
                return value
            normalized = re.sub(r'\s*[×xX]\s*', ' × ', match.group(0))
            normalized = normalized.replace(',', '')
            return re.sub(r'\s+', ' ', normalized).strip()
        return value

    @staticmethod
    def _subject_matches_page(subject, page_title):
        subject = normalize_to_simplified(subject or '').strip()
        page_title = normalize_to_simplified(page_title or '').strip()
        if not subject or not page_title:
            return False
        return subject == page_title

    def extract_triples(self, page_title, sections, sentences=None):
        """
        规则抽取正文三元组。

        固定 ontology，不调用 LLM，不自由生成 relation。
        """
        if sentences is None:
            sentences = self.segment_sentences(sections)

        triples = []
        seen = set()
        for item in sentences:
            sentence = item.get('sentence', '')
            for pattern, relation, subj_group, obj_group in self.TEXT_RULES:
                for match in re.finditer(pattern, sentence):
                    try:
                        subject = self._clean_entity(match.group(subj_group))
                        obj = self._clean_object(match.group(obj_group))
                    except IndexError:
                        continue

                    if relation == 'DISCOVERED_BY' and subj_group == 2:
                        subject = self._clean_entity(match.group(subj_group))

                    if not subject:
                        continue
                    if not obj or len(obj) > 120:
                        continue
                    if relation == 'DISCOVERED_BY' and subject != page_title:
                        continue

                    if not self._subject_matches_page(subject, page_title):
                        continue
                    subject = page_title

                    candidate_objects = [obj]
                    if relation == 'HAS_ATMOSPHERE':
                        candidate_objects = split_atmosphere_components(obj)

                    for candidate in candidate_objects:
                        triple = make_triple(
                            subject,
                            relation,
                            candidate,
                            pattern='rule',
                            raw=match.group(0),
                        )
                        if not triple:
                            continue
                        if not validate_triple(triple['subject'], triple['relation'], triple['object']):
                            continue

                        key = (triple['subject'], triple['relation'], triple['object'])
                        if key in seen:
                            continue
                        seen.add(key)
                        triples.append(triple)

        return triples

    @staticmethod
    def _dedupe_triples(triples):
        seen = set()
        result = []
        for triple in triples:
            key = (triple.get('subject'), triple.get('relation'), triple.get('object'))
            if key in seen:
                continue
            seen.add(key)
            result.append(triple)
        return result

    @staticmethod
    def _clean_chunk_text(text):
        text = normalize_to_simplified(text or '')
        text = re.sub(r'\[编辑\]|\[編輯\]', '', text or '')
        text = re.sub(r'\[\d+(?:\.\d+)?\]', '', text)
        text = re.sub(r'\s+', ' ', text)
        text = re.sub(r'(?<=[。！？])\s*', '\n', text)
        return text.strip()

    @staticmethod
    def _split_section_text(text, min_chars, max_chars):
        pieces = []
        current = ''
        for sentence in re.split(r'(?<=[。！？；;])\s*', text):
            sentence = sentence.strip()
            if not sentence:
                continue
            if len(current) + len(sentence) <= max_chars:
                current += sentence
            else:
                if current and len(current) >= min_chars:
                    pieces.append(current.strip())
                current = sentence

        if current and len(current) >= min_chars:
            pieces.append(current.strip())
        elif current and pieces:
            pieces[-1] = (pieces[-1] + current).strip()
        elif current:
            pieces.append(current.strip())
        return pieces

    def chunk_for_embedding(self, page_title, sections, min_chars=120, max_chars=800, origin='api', source_name=None, source_role=None, schema_version=None):
        """
        按 section 生成 embedding 文本块，不整篇 embedding。

        Returns:
            list[dict]: [{title, section, chunk, path}]
        """
        chunks = []
        for section in sections:
            section_title = section.get('section', '')
            section_title = normalize_to_simplified(section_title)
            if self._is_discard_section(section_title):
                continue

            text = self._clean_chunk_text(section.get('text', ''))
            if len(text) < min_chars:
                continue

            if len(text) <= max_chars:
                chunks.append(apply_record_metadata({
                    'title': page_title,
                    'section': section_title,
                    'chunk': text,
                    'path': normalize_to_simplified(section.get('path', section_title)),
                }, origin, RECORD_TYPE_EMBEDDING_CHUNK, source_name=source_name or self.source_name, source_role=source_role or self.source_role, source_title=page_title, extra={"schema_version": schema_version or self.schema_version} if (schema_version or self.schema_version) else None))
                continue

            for index, piece in enumerate(self._split_section_text(text, min_chars, max_chars)):
                chunks.append(apply_record_metadata({
                    'title': page_title,
                    'section': section_title if index == 0 else f'{section_title} ({index + 1})',
                    'chunk': piece,
                    'path': normalize_to_simplified(section.get('path', section_title)),
                }, origin, RECORD_TYPE_EMBEDDING_CHUNK, source_name=source_name or self.source_name, source_role=source_role or self.source_role, source_title=page_title, extra={"schema_version": schema_version or self.schema_version} if (schema_version or self.schema_version) else None))

        return chunks

    @staticmethod
    def chunks_to_narratives(embedding_chunks, page_title, source_name=None, source_role=None, schema_version=None):
        """将 embedding chunks 转为 ChromaStore 兼容叙事格式。"""
        narratives = []
        for index, chunk in enumerate(embedding_chunks):
            content = chunk.get('chunk', '')
            section = chunk.get('section', '')
            if not content or len(content) < 50:
                continue

            chunk_id = hashlib.md5(
                f'{page_title}|{section}|{index}|{content[:80]}'.encode('utf-8')
            ).hexdigest()[:12]
            narratives.append(apply_record_metadata({
                'page_title': page_title,
                'section': section,
                'chunk_index': index,
                'content': content,
                'path': chunk.get('path', ''),
                'keywords': WikiPreprocessor._simple_keywords(content),
                'chunk_id': chunk_id,
            }, chunk.get('origin'), RECORD_TYPE_EMBEDDING_CHUNK, source_name=source_name or chunk.get('source_name'), source_role=source_role or chunk.get('source_role'), source_title=page_title, extra={"schema_version": schema_version or chunk.get("schema_version")} if (schema_version or chunk.get("schema_version")) else None))
        return narratives

    @staticmethod
    def _simple_keywords(text, top_k=8):
        words = re.findall(r'[\u4e00-\u9fff]{2,}', text or '')
        freq = {}
        for word in words:
            if word in {'一个', '一种', '可以', '以及', '由于', '因此', '其中'}:
                continue
            freq[word] = freq.get(word, 0) + 1
        return [word for word, _ in sorted(freq.items(), key=lambda item: -item[1])[:top_k]]


_default = WikiPreprocessor()

clean_html = _default.clean_html
extract_infobox = _default.extract_infobox
extract_sections = _default.extract_sections
segment_sentences = _default.segment_sentences
extract_triples = _default.extract_triples
chunk_for_embedding = _default.chunk_for_embedding
