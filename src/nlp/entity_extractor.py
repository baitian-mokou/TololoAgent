"""
LEGACY / DEPRECATED.

Historical entity extractor kept only for reference.
Do not use in the current single-source P5 hot path.
The frozen baseline uses `preprocess.py + triple_builder.py` via `NlpPipeline`.
"""
import re
import json
import os
import jieba


class EntityExtractor:
    """从句子中提取天体实体、属性名、数值"""

    def __init__(self, dict_path=None, terms_path=None):
        # 加载 jieba 天文词典
        if dict_path and os.path.exists(dict_path):
            jieba.load_userdict(dict_path)

        # 停用词（不移除合法天文词）
        self.skip_words = {
            '的', '了', '是', '在', '和', '与', '或', '有', '被', '把',
            '从', '到', '对', '为', '以', '上', '下', '中', '内', '外',
            '之', '而', '且', '但', '也', '都', '还', '又', '就', '更',
            '很', '太', '最', '较', '一', '二', '三', '四', '五', '六',
            '七', '八', '九', '十', '百', '千', '万', '亿', '两', '多',
            '约', '近', '达', '余', '左右', '超过', '超过约',
        }
        # 合法天文词（不被过滤）
        self.allowed_astro = {
            '太阳', '行星', '恒星', '卫星', '彗星', '小行星', '星系',
            '地球', '火星', '木星', '土星', '金星', '水星', '天王星', '海王星',
            '月球', '银河系', '黑洞', '超新星', '白矮星', '中子星',
        }
        # 属性名列表（用于属性-数值对识别）
        self.param_names = [
            '半长轴', '离心率', '轨道倾角', '公转周期', '自转周期',
            '质量', '半径', '直径', '密度', '表面重力', '磁场强度',
            '表面温度', '大气成分', '逃逸速度', '轨道速度',
            '星等', '绝对星等', '视星等', '反照率', '光度', '光谱型',
            '体积', '扁率', '赤道半径', '极半径',
            '大气压强', '卫星数量', '环系统',
            '近日点', '远日点', '轨道周长',
            '发现者', '发现日期', '自转速度',
            '转轴倾角', '黄赤交角', '平均密度',
        ]
        # 单位模式（扩充天文学单位）
        self.unit_pattern = re.compile(
            r'([+-]?\d+(?:[,.]\d+)?(?:[×x]10[⁻]?\d+)?)\s*'
            r'(°C|K|℃|公里|千米|米|AU|天文单位|天|小时|秒|年|'
            r'g/cm³|g/cm3|m/s²|m/s|km/s|%|帕|巴|千克|kg|吨|t|'
            r'地球质量|木星质量|M⊕|M♃|月球质量|ly|光年|pc|秒差距)'
        )
        # 数值区域检测
        self.range_pattern = re.compile(
            r'([+-]?\d+[,.]?\d*)\s*(到|至|~|～)\s*([+-]?\d+[,.]?\d*)\s*(°C|K|℃)'
        )

        # 加载天文词库（实体白名单）
        self.terms = self._load_terms(terms_path)

    def _load_terms(self, path):
        """加载天文词库"""
        if not path or not os.path.exists(path):
            return {}
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}

    def _is_valid_entity(self, name):
        """检查是否是合法实体"""
        name = name.strip()
        if not name:
            return False
        if name in self.skip_words:
            return False
        if name in self.allowed_astro:
            return True

        # 检查天文白名单（从astronomy_terms.json加载）
        if self.terms:
            for category in ['celestial_bodies', 'missions', 'scientists',
                             'observatories', 'constellations']:
                items = self.terms.get(category, {})
                if isinstance(items, dict):
                    for sublist in items.values():
                        if name in sublist:
                            return True
                elif isinstance(items, list):
                    if name in items:
                        return True

        # 长度限制放宽：2-20
        if len(name) < 2 or len(name) > 20:
            return False

        # 不再强制要求中文！允许中英混合名（如"51 Pegasi b"）
        # 但必须包含字母或中文，不能只是纯数字符号
        if not re.search(r'[a-zA-Z\u4e00-\u9fff]', name):
            return False

        # 不允许标点符号（但允许数字和字母组成的中英混合）
        if re.search(r'[。，；：、？！·～…—\n\t]', name):
            return False

        return True

    def extract_entities(self, sentence, tokens):
        """从句子和分词结果提取实体"""
        entities = []

        # 1. 从分词结果中提取中文实体
        for token in tokens:
            token = token.strip()
            if self._is_valid_entity(token):
                entities.append({
                    'name': token,
                    'type': 'entity',
                    'source': 'jieba',
                })
            # 数字+单位组合
            elif re.match(r'^[+-]?\d+[,.]?\d*[°C%AUkm]', token):
                entities.append({
                    'name': token,
                    'type': 'value',
                    'source': 'regex',
                })

        # 2. 从句子中用正则提取数值+单位
        for m in self.unit_pattern.finditer(sentence):
            val = m.group(1)
            unit = m.group(2)
            entities.append({
                'name': f'{val}{unit}',
                'type': 'value',
                'source': 'regex',
            })

        # 3. 检测范围值
        for m in self.range_pattern.finditer(sentence):
            entities.append({
                'name': m.group(0),
                'type': 'value_range',
                'source': 'regex',
            })

        # 4. 属性名匹配
        for pn in self.param_names:
            if pn in sentence:
                entities.append({
                    'name': pn,
                    'type': 'parameter',
                    'source': 'dict',
                })

        return entities
