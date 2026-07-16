"""
固定 Ontology - 知识图谱关系类型约束
只允许预定义关系，禁止 LLM 或规则引擎自由生成 relation
"""
import re

from .text_normalizer import normalize_to_simplified

# 允许的关系类型（Neo4j 关系名）
ALLOWED_RELATIONS = frozenset({
    'IS_A',
    'PART_OF',
    'ORBITS',
    'HAS_MASS',
    'HAS_RADIUS',
    'HAS_ATMOSPHERE',
    'DISCOVERED_BY',
    'LOCATED_IN',
})

MAX_OBJECT_TOKENS = 10
MAX_SUBJECT_TOKENS = 8

_CAUSAL_MARKERS = (
    '因为', '由於', '由于', '因為', '例如', '導致', '导致', '所以', '因此',
    '从而', '從而', '進而', '以致', '使得', '造成', 'resulting in', 'leading to',
    'because', 'because of', 'due to', 'for example', 'e.g.', 'such as', 'thus',
    'therefore', 'which', 'where',
)

_DESCRIPTIVE_PHRASE_PATTERNS = (
    re.compile(r'主要由'),
    re.compile(r'由.+(?:组成|組成|构成|構成)'),
    re.compile(r'(?:含有|包含|具有|拥有|擁有)'),
    re.compile(r'(?:位于|位於|处于|處於|围绕|圍繞|环绕|環繞|运行|運行)'),
    re.compile(r'(?:中的|里的|內的|上的|下的|时的|時的)'),
    re.compile(r'唯一一个'),
    re.compile(r'尚未'),
    re.compile(r'没有(?:大气|大氣|人造卫星|人造衛星|被探测|被探測)?'),
    re.compile(r'未被(?:探测|探測)'),
)

_PUNCTUATION = '。！？!?；;，,：:\n\r\t'

_NUMERIC_UNIT_RE = re.compile(
    r'^[~≈]?\s*[\d,.×xX\-\+\s/^()]+(?:'
    r'kg|千克|公斤|吨|噸|地球质量|地球質量|木星质量|木星質量|M⊕|M♃|'
    r'km|KM|公里|千米|m|米|AU|天文单位|天文單位|bar|%'
    r')?$'
)

_MASS_VALUE_RE = re.compile(
    r'^[~≈]?\s*[\d,.×xX\-\+\s/^()]+(?:'
    r'kg|千克|公斤|吨|噸|地球质量|地球質量|木星质量|木星質量|M⊕|M♃'
    r')$'
)

_RADIUS_VALUE_RE = re.compile(
    r'^[~≈]?\s*[\d,.×xX\-\+\s/^()]+(?:'
    r'km|KM|公里|千米|m|米'
    r')$'
)

_PURE_NUMBER_RE = re.compile(r'^[~≈]?\s*[\d,.×xX\-\+\s/^()]+$')
_DATE_RE = re.compile(
    r'^\d{3,4}(?:[-/年]\d{1,2}(?:[-/月]\d{1,2}(?:日)?)?)?$'
)
_NON_NUMERIC_RELATIONS = frozenset({
    'IS_A', 'PART_OF', 'ORBITS', 'LOCATED_IN', 'HAS_ATMOSPHERE', 'DISCOVERED_BY',
})
_ATMOSPHERE_COMPONENT_RE = re.compile(
    r'^(?:'
    r'(?:[A-Z][a-z]?\d*)+|'
    r'二氧化碳|一氧化碳|氧气|氧|氮气|氮|氩气|氩|氦气|氦|氢气|氢|甲烷|氨|水汽|水蒸气|臭氧|二氧化硫'
    r')$'
)

_IS_A_CANONICAL_MAP = {
    '天然卫星': '卫星',
    '主序恒星': '主序星',
    '红矮恒星': '红矮星',
    '气态巨行星': '类木行星',
    '岩石行星': '类地行星',
}

_ATMOSPHERE_CANONICAL_MAP = {
    '二氧化碳': 'CO2',
    '一氧化碳': 'CO',
    '氮气': 'N2',
    '氧气': 'O2',
    '氩气': 'Ar',
    '氦气': 'He',
    '氦': 'He',
    '氢气': 'H2',
    '氢': 'H2',
    '甲烷': 'CH4',
    '氨': 'NH3',
    '水汽': 'H2O',
    '水蒸气': 'H2O',
    '臭氧': 'O3',
    '二氧化硫': 'SO2',
}

_ATMOSPHERE_FORMULA_CANONICAL_MAP = {
    'CO2': 'CO2',
    'CO': 'CO',
    'N2': 'N2',
    'O2': 'O2',
    'AR': 'Ar',
    'HE': 'He',
    'H2': 'H2',
    'CH4': 'CH4',
    'NH3': 'NH3',
    'H2O': 'H2O',
    'O3': 'O3',
    'SO2': 'SO2',
}

_ENTITY_RE = re.compile(r'^[A-Za-z0-9\u4e00-\u9fff·\-\+\s]+$')
_DISCOVERER_RE = re.compile(r'^[A-Za-z0-9\u4e00-\u9fff][A-Za-z0-9\u4e00-\u9fff\s.\-·+]{1,59}$')
_FORMULA_RE = re.compile(r'(?:[A-Z][a-z]?\d*)+')
_ATMOSPHERE_TERM_RE = re.compile(r'[\u4e00-\u9fff]{1,12}')
_DISCOVERER_CN_NAME_RE = re.compile(r'^[\u4e00-\u9fff]{2,4}$')
_DISCOVERER_TRANSLITERATION_RE = re.compile(r'^[\u4e00-\u9fff·]{3,30}$')
_DISCOVERER_LATIN_NAME_RE = re.compile(r'^[A-Za-z][A-Za-z.\- ]{1,59}$')

_ATMOSPHERE_SPLIT_RE = re.compile(r'[、,，/／;；|+]+|\s+(?:和|及|与|與)\s*')
_ATMOSPHERE_STOPWORDS = {
    '组成', '組成', '构成', '構成', '主要', '成分', '并含有', '並含有',
    '含有', '包含', '微量', '少量', '痕量', '以及', '其中',
    '混合微量', '混合微量的', '其他', '其他的', '气态分子', '氣態分子',
    '所构成', '所構成', '构成', '構成', '分子',
}
_DISCOVERER_STOPWORDS = {
    '他', '她', '它', '其', '他们', '她们', '它们', '人们', '了再',
    '发现者', '發現者', '天文学家', '天文學家', '科学家', '科學家',
}
_DISCOVERER_BAD_MARKERS = (
    '首先', '为了', '為了', '后来', '後來', '在 ', ' 於', ' 于', '於 ',
    '发现了', '發現了', '找到', '觀測', '观测', '团队', '隊伍',
)

# Infobox / 正文参数名 → Ontology 映射
INFOBOX_KEY_MAP = {
    # 质量
    '质量': 'HAS_MASS',
    '質量': 'HAS_MASS',
    # 半径
    '半径': 'HAS_RADIUS',
    '平均半径': 'HAS_RADIUS',
    '平均半徑': 'HAS_RADIUS',
    '赤道半径': 'HAS_RADIUS',
    '赤道半徑': 'HAS_RADIUS',
    '极半径': 'HAS_RADIUS',
    '極半徑': 'HAS_RADIUS',
    # 大气
    '大气': 'HAS_ATMOSPHERE',
    '大氣': 'HAS_ATMOSPHERE',
    '大气层': 'HAS_ATMOSPHERE',
    '大氣層': 'HAS_ATMOSPHERE',
    '大气成分': 'HAS_ATMOSPHERE',
    '大氣成分': 'HAS_ATMOSPHERE',
    # 轨道 / 所属
    '所属': 'PART_OF',
    '所屬': 'PART_OF',
    '母天体': 'ORBITS',
    '母天體': 'ORBITS',
    '卫星所属行星': 'ORBITS',
    '衛星所屬行星': 'ORBITS',
    '所属恒星': 'ORBITS',
    '所屬恆星': 'ORBITS',
    '轨道所属': 'ORBITS',
    '軌道所屬': 'ORBITS',
    '绕行': 'ORBITS',
    '繞行': 'ORBITS',
    '公转对象': 'ORBITS',
    '公轉對象': 'ORBITS',
    # 发现
    '发现者': 'DISCOVERED_BY',
    '發現者': 'DISCOVERED_BY',
    # 位置
    '位置': 'LOCATED_IN',
    '所在': 'LOCATED_IN',
    '所属星系': 'LOCATED_IN',
    '所屬星系': 'LOCATED_IN',
    # 类型
    '类型': 'IS_A',
    '類型': 'IS_A',
    '分类': 'IS_A',
    '分類': 'IS_A',
}


def normalize_infobox_key(raw_key):
    """标准化 infobox 键名并返回对应的 ontology 关系"""
    if not raw_key:
        return None
    key = normalize_to_simplified(str(raw_key)).strip()
    key = key.replace('\n', '').replace('[编辑]', '')
    if len(key) > 20:
        return None
    return INFOBOX_KEY_MAP.get(key)


def validate_relation(relation):
    """验证关系是否在 ontology 允许范围内"""
    if relation in ALLOWED_RELATIONS:
        return relation
    return None


def _token_count(text):
    tokens = re.findall(r'[A-Za-z]+(?:\d+)?|[\u4e00-\u9fff]+|\d+(?:\.\d+)?', text or '')
    return len(tokens)


def _contains_causal_marker(text):
    lowered = (text or '').lower()
    return any(marker in lowered for marker in _CAUSAL_MARKERS)


def _contains_descriptive_marker(text):
    text = normalize_to_simplified(text or '').strip()
    if not text:
        return False
    for pattern in _DESCRIPTIVE_PHRASE_PATTERNS:
        if pattern.search(text):
            return True
    if '的' in text and len(re.findall(r'[\u4e00-\u9fff]', text)) >= 5:
        return True
    return False


def _is_numeric_or_dated_value(text):
    text = normalize_to_simplified(text or '').strip()
    if not text:
        return False
    compact = re.sub(r'\s+', '', text)
    if _DATE_RE.fullmatch(compact):
        return True
    if _PURE_NUMBER_RE.fullmatch(compact):
        return True
    if _NUMERIC_UNIT_RE.fullmatch(compact):
        return True
    return False


def _normalize_whitespace(text):
    return re.sub(r'\s+', ' ', normalize_to_simplified(text or '')).strip()


def _normalize_is_a_object(obj):
    text = _normalize_whitespace(obj)
    if not text:
        return None
    text = text.strip('，。、；;：: ')
    text = re.sub(r'^(?:一个|一個|一种|一種|一颗|一顆)\s*', '', text)
    text = _IS_A_CANONICAL_MAP.get(text, text)

    star_match = re.fullmatch(r'([OBAFGKM])型主序恒星', text, flags=re.IGNORECASE)
    if star_match:
        return f"{star_match.group(1).upper()}型主序星"

    if text.endswith('恒星'):
        if text in {'主序恒星', '红矮恒星'}:
            return _IS_A_CANONICAL_MAP.get(text)
    return _IS_A_CANONICAL_MAP.get(text, text)


def _normalize_located_in_object(obj):
    text = _normalize_whitespace(obj)
    if not text:
        return None
    text = text.strip('，。、；;：: ')
    text = re.sub(r'^(?:位于|位於|处于|處於|在)\s*', '', text)
    text = re.sub(r'(?:之)?(?:内|內|中)$', '', text)
    text = re.sub(r'(?:范围|範圍|区域|區域)$', '', text)
    text = text.strip()
    return text or None


def _normalize_entity_target_object(obj):
    text = _normalize_whitespace(obj)
    if not text:
        return None
    text = text.strip('，。、；;：: ')
    text = re.sub(r'^(?:著|的|于|於|在)\s*', '', text)
    return text or None


def _normalize_atmosphere_object(obj):
    text = _normalize_whitespace(obj)
    if not text:
        return None
    text = text.strip('，。、；;：: ')
    if text in _ATMOSPHERE_CANONICAL_MAP:
        return _ATMOSPHERE_CANONICAL_MAP[text]
    compact = re.sub(r'\s+', '', text).upper()
    if compact in _ATMOSPHERE_FORMULA_CANONICAL_MAP:
        return _ATMOSPHERE_FORMULA_CANONICAL_MAP[compact]
    return None


def _normalize_discovered_by_object(obj):
    text = _normalize_whitespace(obj)
    if not text:
        return None
    text = re.sub(r'^(?:由|被)\s*', '', text)
    text = re.sub(r'\s*·\s*', '·', text)
    return text


def normalize_object_by_relation(relation, obj):
    """按关系类型对 object 做最小、可解释的标准化。"""
    rel = validate_relation(relation)
    if not rel:
        return None

    text = _normalize_whitespace(obj)
    if not text:
        return None

    if rel == 'IS_A':
        return _normalize_is_a_object(text)
    if rel == 'LOCATED_IN':
        return _normalize_located_in_object(text)
    if rel in {'ORBITS', 'PART_OF'}:
        return _normalize_entity_target_object(text)
    if rel == 'HAS_ATMOSPHERE':
        return _normalize_atmosphere_object(text)
    if rel == 'DISCOVERED_BY':
        return _normalize_discovered_by_object(text)
    return text


def _is_entity_like(text, max_tokens=MAX_OBJECT_TOKENS, allow_spaces=True):
    text = normalize_to_simplified(text or '').strip()
    if not text:
        return False
    if any(ch in text for ch in _PUNCTUATION):
        return False
    if any(ch in text for ch in '()（）[]【】{}<>'):
        return False
    if _contains_causal_marker(text):
        return False
    if _contains_descriptive_marker(text):
        return False
    if _token_count(text) > max_tokens:
        return False
    if not allow_spaces and ' ' in text:
        return False
    return bool(_ENTITY_RE.fullmatch(text))


def _is_astronomy_entity_like(text, max_tokens=MAX_OBJECT_TOKENS):
    """允许目录编号型天体名，如 Kepler-22 / HD 189733 / M31 / NGC 205。"""
    text = normalize_to_simplified(text or '').strip()
    if not text:
        return False
    if any(ch in text for ch in _PUNCTUATION):
        return False
    if any(ch in text for ch in '()（）[]【】{}<>'):
        return False
    if _contains_causal_marker(text):
        return False
    if _contains_descriptive_marker(text):
        return False
    if _token_count(text) > max_tokens:
        return False
    return bool(_ENTITY_RE.fullmatch(text))


def _is_valid_discoverer_name(text):
    text = normalize_to_simplified(text or '').strip()
    if not text:
        return False
    if _is_numeric_or_dated_value(text):
        return False
    if _contains_causal_marker(text) or _contains_descriptive_marker(text):
        return False
    if re.match(r'^(?:年|月|日)(?:\s|$)', text):
        return False
    if '的' in text:
        return False
    if text in _DISCOVERER_STOPWORDS:
        return False
    if any(marker in text for marker in _DISCOVERER_BAD_MARKERS):
        return False
    if not re.search(r'[A-Za-z\u4e00-\u9fff]', text):
        return False
    if _token_count(text) > 8:
        return False
    if not _DISCOVERER_RE.fullmatch(text):
        return False
    if _DISCOVERER_CN_NAME_RE.fullmatch(text):
        return True
    if '·' in text and _DISCOVERER_TRANSLITERATION_RE.fullmatch(text):
        return True
    if _DISCOVERER_LATIN_NAME_RE.fullmatch(text):
        return _token_count(text) <= 4
    return False


def _is_valid_object(obj, relation, max_tokens=MAX_OBJECT_TOKENS):
    obj = normalize_to_simplified(obj or '').strip()
    if not obj:
        return False
    if _contains_causal_marker(obj):
        return False
    if _contains_descriptive_marker(obj):
        return False
    if any(ch in obj for ch in _PUNCTUATION):
        return False
    if any(ch in obj for ch in '()（）[]【】{}<>'):
        return False
    if relation in _NON_NUMERIC_RELATIONS and _is_numeric_or_dated_value(obj):
        return False
    if relation == 'HAS_MASS':
        compact = re.sub(r'\s+', '', obj)
        return bool(_MASS_VALUE_RE.fullmatch(compact)) and not bool(_DATE_RE.fullmatch(compact))
    if relation == 'HAS_RADIUS':
        compact = re.sub(r'\s+', '', obj)
        return bool(_RADIUS_VALUE_RE.fullmatch(compact)) and not bool(_DATE_RE.fullmatch(compact))
    if relation == 'DISCOVERED_BY':
        return _is_valid_discoverer_name(obj)
    if relation == 'HAS_ATMOSPHERE':
        compact = re.sub(r'\s+', '', obj)
        if _is_numeric_or_dated_value(compact):
            return False
        return bool(_ATMOSPHERE_COMPONENT_RE.fullmatch(compact))
    if relation == 'IS_A':
        if _is_numeric_or_dated_value(obj):
            return False
        if re.search(r'\d', obj):
            return False
        return _is_entity_like(obj, max_tokens=max_tokens, allow_spaces=True)
    if relation in {'PART_OF', 'ORBITS', 'LOCATED_IN'}:
        if _is_numeric_or_dated_value(obj):
            return False
        return _is_astronomy_entity_like(obj, max_tokens=max_tokens)
    if any(ch in obj for ch in _PUNCTUATION):
        return False
    return _is_entity_like(obj, max_tokens=max_tokens)


def _split_atmosphere_components(obj):
    """把大气描述拆成单一成分，避免把解释句整体写入图谱。"""
    text = normalize_to_simplified(obj or '').strip()
    if not text:
        return []

    candidates = []
    for match in re.finditer(r'\d+(?:\.\d+)?\s*%\s*的?\s*([A-Za-z][A-Za-z0-9]*|[\u4e00-\u9fff]{2,8})', text):
        candidates.append(match.group(1).strip())

    text = re.sub(
        r'^(?:主要由|主要成分(?:为|是)?|成分(?:为|是)?|由|以|包含|含有)\s*',
        '',
        text,
    )
    text = re.sub(r'(?:组成|構成|构成|为主|為主|主成分.*)$', '', text).strip()
    text = re.sub(r'\d+(?:\.\d+)?\s*%.*?(?:,|，|、|;|；|$)', ' ', text)
    text = text.replace('以及', '、').replace('及', '、')
    text = text.replace('和', '、').replace('与', '、').replace('與', '、')

    for part in _ATMOSPHERE_SPLIT_RE.split(text):
        part = re.sub(r'[\(\)（）\[\]【】<>]', ' ', part)
        part = re.sub(r'\s+', ' ', part).strip(' ：:，,。;；')
        part = re.sub(r'^(?:并|並)?(?:含有|包含)?(?:微量|少量|痕量)?', '', part).strip()
        part = re.sub(r'(?:以及)?其他.*$', '', part).strip()
        part = re.sub(r'(?:所构成|所構成|构成|構成)$', '', part).strip()
        if not part or _contains_causal_marker(part):
            continue
        formulas = _FORMULA_RE.findall(part)
        if formulas:
            candidates.extend(formulas)
            continue
        for token in _ATMOSPHERE_TERM_RE.findall(part):
            token = token.strip()
            if not token or token.isdigit():
                continue
            if token in _ATMOSPHERE_STOPWORDS:
                continue
            if len(token) <= 1:
                continue
            if _contains_causal_marker(token):
                continue
            candidates.append(token)

    cleaned = []
    seen = set()
    for token in candidates:
        if token in seen:
            continue
        if token in _ATMOSPHERE_STOPWORDS:
            continue
        if '其他' in token or '分子' in token or '构成' in token or '構成' in token:
            continue
        if _is_entity_like(token, max_tokens=3):
            seen.add(token)
            cleaned.append(token)
    return cleaned


def split_atmosphere_components(obj):
    """公开的大气成分拆分接口。"""
    return _split_atmosphere_components(obj)


def validate_triple(subject, relation, obj, max_object_tokens=MAX_OBJECT_TOKENS):
    """严格校验三元组，失败直接丢弃。"""
    rel = validate_relation(relation)
    if not rel:
        return None

    subject = normalize_to_simplified(subject).strip()
    obj = normalize_object_by_relation(rel, obj)
    if not subject or not obj:
        return None
    if not _is_entity_like(subject, max_tokens=MAX_SUBJECT_TOKENS, allow_spaces=True):
        return None
    if not _is_valid_object(obj, rel, max_tokens=max_object_tokens):
        return None
    return {
        'subject': subject,
        'relation': rel,
        'object': obj,
    }


def make_triple(subject, relation, obj, pattern='rule', raw=''):
    """构造标准三元组 dict，自动校验 relation"""
    validated = validate_triple(subject, relation, obj)
    if not validated:
        return None
    rel = validated['relation']
    subject = validated['subject']
    obj = validated['object']
    raw = normalize_to_simplified(raw).strip() if raw else ''
    return {
        'subject': subject,
        'relation': rel,
        'object': obj,
        'pattern': pattern,
        'raw': raw or f'{subject} {rel} {obj}',
    }
