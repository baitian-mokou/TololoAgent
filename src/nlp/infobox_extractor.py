"""
LEGACY / DEPRECATED.

Historical infobox extractor retained for reference only.
Do not use it for the current single-source baseline or P5 convergence flow.
The active path normalizes infobox data inside `preprocess.py`.
"""
import re


class InfoboxExtractor:
    """从 Infobox 数据中提取结构化属性-数值对"""

    def __init__(self):
        # 已知的天文学属性参数名（用于过滤和标准化）
        self.known_params = [
            '半长轴', '离心率', '轨道倾角', '公转周期', '自转周期',
            '质量', '半径', '直径', '密度', '表面重力', '磁场强度',
            '表面温度', '大气压强', '逃逸速度', '轨道速度',
            '星等', '绝对星等', '视星等', '反照率', '光度', '光谱型',
            '体积', '扁率', '赤道半径', '极半径',
            '大气成分', '卫星数量', '环系统',
            '近日点', '远日点', '轨道周长', '轨道速度',
            '赤经', '赤纬', '距离',
            '发现者', '发现日期', '发现地点',
            '自转速度', '赤道自转速度', '转轴倾角', '黄赤交角',
            '表面气压', '平均密度',
        ]

    def extract_from_infobox(self, infobox_dict, page_title):
        """
        从信息框字典中提取结构化三元组

        Args:
            infobox_dict: {参数名: 值} 字典
            page_title: 页面标题

        Returns:
            list of triple dicts
        """
        triples = []
        if not infobox_dict:
            return triples

        for key, value in infobox_dict.items():
            # 标准化参数名
            param = self._normalize_param(key)
            if not param:
                continue

            # 清洗值
            clean_value = self._clean_value(value)
            if not clean_value:
                continue

            triples.append({
                'subject': page_title,
                'relation': '拥有' + param,
                'object': clean_value,
                'pattern': 'infobox',
                'raw': f'{key}: {value}',
                'source': page_title,
            })

        return triples

    def extract_kv_pairs(self, sentence):
        """
        从句子中直接提取属性-数值对（用于正文中的 inline 数据）

        Args:
            sentence: 句子文本

        Returns:
            list of {parameter, value, raw}
        """
        results = []

        for pn in self.known_params:
            # 匹配: "半长轴为1.524 AU" "半长轴：1.524AU" "半长轴 0.387 AU"
            pattern = re.compile(
                rf'{re.escape(pn)}\s*[为:：]?\s*'
                r'([+-]?\d+[,.]?\d*(?:[×x××]10[⁻]?\d+)?)'
                r'\s*'
                r'(°C|K|℃|公里|千米|米|AU|天文单位|天|小时|秒|年|'
                r'g/cm³|g/cm3|m/s²|m/s|km/s|%|帕|巴|kg|t|'
                r'地球质量|木星质量|M⊕|M♃|ly|光年|pc|秒差距)?'
            )
            m = pattern.search(sentence)
            if m:
                value = m.group(1)
                unit = m.group(2) or ''
                full_val = f'{value}{unit}'
                results.append({
                    'parameter': pn,
                    'value': full_val,
                    'raw': m.group(0),
                })

        # 多值属性: "CO2占95.3%、N2占2.7%"
        multi_val = re.findall(
            r'(\w+)\s*[占占比]?\s*([\d.]+)\s*%',
            sentence
        )
        if len(multi_val) >= 2:
            results.append({
                'parameter': '大气成分',
                'value': {k: f'{v}%' for k, v in multi_val},
                'raw': ', '.join(f'{k}/{v}%' for k, v in multi_val),
            })

        return results

    def _normalize_param(self, raw_key):
        """标准化参数名"""
        # 去除维基标记残留
        key = re.sub(r'<[^>]+>', '', raw_key)
        key = re.sub(r'\[\[([^\]|]+).*?\]\]', r'\1', key)
        key = key.strip()

        # 过滤掉太长的或明显不是参数名的
        if len(key) > 20 or len(key) < 2:
            return None

        # 过滤非参数行
        skip_keys = ['主条目', '参见', '分类', '注', '注释', '图片来源',
                      '上图', '下图', '图片', '图注']
        if key in skip_keys:
            return None

        return key

    def _clean_value(self, raw_value):
        """清洗参数值"""
        value = str(raw_value)

        # 移除 HTML 标签
        value = re.sub(r'<[^>]+>', '', value)

        # 处理 [[链接]]
        value = re.sub(r'\[\[([^\]|]+)(?:\|[^\]]+)?\]\]', r'\1', value)

        # 移除模板残留
        value = re.sub(r'\{\{[^}]+}}', '', value)

        # 移除多余空白
        value = re.sub(r'\s+', ' ', value).strip()

        # 限制长度
        if len(value) > 500:
            value = value[:500]

        return value if value else None
