"""
LEGACY / DEPRECATED.

Historical relation extractor kept only to avoid destructive removal.
Do not use for the current single-source baseline.
The active triple contract is enforced by `preprocess.py` and `ontology.py`.
"""
import re


class RelationExtractor:
    """从句子中抽取实体间的关系三元组"""

    def __init__(self):
        self.templates = self._build_templates()

    def _build_templates(self):
        """构建20个关系模板 - 使用非贪婪匹配防止跨词"""
        return [
            # ---- 第一组：绕转关系 ----
            {
                'relation': '围绕',
                'patterns': [
                    (r'([^。，；：！？\n]{2,10})绕[着绕转]?\s*([^。，；：！？\n]{2,20})公?转',),
                    (r'([^。，；：！？\n]{2,10})围绕\s*([^。，；：！？\n]{2,20})',),
                    (r'([^。，；：！？\n]{2,10})是\s*([^。，；：！？\n]{2,20})的卫星',),
                    (r'([^。，；：！？\n]{2,10})环绕\s*([^。，；：！？\n]{2,20})',),
                    (r'([^。，；：！？\n]{2,10})在\s*([^。，；：！？\n]{2,20})轨道上',),
                ],
            },
            # ---- 第二组：轨道参数 ----
            {
                'relation': '拥有轨道参数',
                'patterns': [
                    (r'([^。，；：！？\n]{2,10})(?:的)?(?:轨道)?半长轴[为:：]?\s*([\d.]+)\s*AU',),
                    (r'([^。，；：！？\n]{2,10})(?:的)?离心率[为:：]?\s*([\d.]+)',),
                    (r'([^。，；：！？\n]{2,10})(?:的)?公转周期[为:：]?\s*([\d.]+)\s*(?:天|年)',),
                    (r'([^。，；：！？\n]{2,10})距离太阳\s*约?\s*([\d.]+)\s*AU',),
                ],
            },
            # ---- 第三组：环境特征 ----
            {
                'relation': '拥有环境特征',
                'patterns': [
                    (r'([^。，；：！？\n]{2,10})(?:的)?表面温度[为:：]?\s*(.+?)(?:°C|℃|K)',),
                    (r'([^。，；：！？\n]{2,10})(?:的)?大气[中主要]?(?:成分|组成)[为:：]?\s*(.+?)',),
                    (r'([^。，；：！？\n]{2,10})(?:的)?(?:表面)?重力[加速度]?[为:：]?\s*([\d.]+)\s*m/s',),
                ],
            },
            # ---- 第四组：行星类型 ----
            {
                'relation': '属于行星类型',
                'patterns': [
                    (r'([^。，；：！？\n]{2,10})是\s*([^。，；：！？\n]{2,10}(?:行星|星|天体))',),
                    (r'([^。，；：！？\n]{2,10})属于\s*([^。，；：！？\n]{2,10}(?:行星|星|天体))',),
                    (r'([^。，；：！？\n]{2,10})被?分类[为成]\s*([^。，；：！？\n]{2,10}(?:行星|矮行星|恒星|卫星|彗星|小行星))',),
                ],
            },
            # ---- 第五组：物理参数 ----
            {
                'relation': '拥有物理参数',
                'patterns': [
                    (r'([^。，；：！？\n]{2,10})(?:的)?(?:平均)?直径[为:：]?\s*([\d.]+)\s*公里',),
                    (r'([^。，；：！？\n]{2,10})(?:的)?质量[为:：]?\s*([\d.]+)\s*(?:地球|kg|吨)',),
                    (r'([^。，；：！？\n]{2,10})(?:的)?(?:平均)?密度[为:：]?\s*([\d.]+)\s*g/cm',),
                    (r'([^。，；：！？\n]{2,10})(?:的)?(?:赤道)?半径[为:：]?\s*([\d.]+)\s*公里',),
                ],
            },
            # ---- 第六组：卫星 ----
            {
                'relation': '拥有卫星',
                'patterns': [
                    (r'([^。，；：！？\n]{2,10})(?:拥有|有|包含)(?:至少)?\s*(\d+)\s*(?:颗已知)?卫星',),
                    (r'([^。，；：！？\n]{2,10})的(?:卫星|天然卫星)(?:包括|有)\s*([^。，；：！？\n]{2,30})',),
                ],
            },
            # ---- 第七组：探测/发现 ----
            {
                'relation': '被探测',
                'patterns': [
                    (r'([^。，；：！？\n]{2,15})(?:探测器|号|计划)(?:探测|飞越|着陆|观测)?(?:了)?\s*([^。，；：！？\n]{2,10})',),
                    (r'([^。，；：！？\n]{2,10})由\s*([^。，；：！？\n]{2,15})\s*发现',),
                    (r'([^。，；：！？\n]{2,10})于\s*(\d{4})\s*年.*?发现',),
                ],
            },
            # ---- 第八组：位置 ----
            {
                'relation': '位于',
                'patterns': [
                    (r'([^。，；：！？\n]{2,10})位[于在]\s*([^。，；：！？\n]{2,30}(?:带|区|系|星团|星系))',),
                    (r'([^。，；：！？\n]{2,10})处[于在]\s*([^。，；：！？\n]{2,30})',),
                ],
            },
            # ---- 第九组：大气成分 ----
            {
                'relation': '大气成分',
                'patterns': [
                    (r'([^。，；：！？\n]{2,10})(?:的)?大气由\s*([^。，；：！？\n]{2,40})\s*组成',),
                    (r'([^。，；：！？\n]{2,10})(?:的)?大气(?:中|主要)含[有]\s*([^。，；：！？\n]{2,40})',),
                ],
            },
        ]

    @staticmethod
    def _is_valid_entity(name):
        """验证实体名是否合法"""
        name = name.strip()
        if not name:
            return False
        if len(name) < 2 or len(name) > 20:
            return False
        # 必须包含字母或中文
        if not re.search(r'[a-zA-Z\u4e00-\u9fff]', name):
            return False
        # 不允许包含的字符（标点、换行等）
        # 但允许中文全角字符、数字、字母、空格、短横线
        if re.search(r'[\\/()（）\[\]{}<>。,，;；:：\n\t]', name):
            return False
        # 不是常见停用词
        skip = {'的', '了', '是', '在', '和', '与', '或', '有', '被', '把', '从', '到',
                '对', '为', '以', '上', '下', '中', '内', '外', '之', '而', '且', '但',
                '也', '都', '还', '又', '就', '更', '很', '太', '最', '较', '约', '近',
                '维基百科', '参考文献', '外部链接', '参见', '导航', '这是一', '所有', '这些', '那些'}
        if name in skip:
            return False
        return True

    @staticmethod
    def _is_numeric(obj):
        """检查是否是数值类型（允许单位后缀）"""
        return bool(re.match(r'^[\d.°C%AUkm\s\-/×x]+$', obj))

    def extract(self, sentence, entities=None):
        """从单个句子中抽取关系三元组

        Args:
            sentence: 句子文本（已在流水线中被分句）
            entities: (可选) 已提取的实体列表，用于候选过滤

        Returns:
            list of triple dicts
        """
        triples = []
        seen = set()

        # 可选：构建实体名字典用于过滤
        entity_names = set()
        if entities:
            for e in entities:
                if e.get('type') in ('entity',):
                    entity_names.add(e.get('name', ''))

        for template in self.templates:
            rel = template['relation']
            for pattern_group in template['patterns']:
                pattern = pattern_group[0]
                m = re.search(pattern, sentence)
                if m:
                    groups = m.groups()
                    if len(groups) >= 2:
                        subj = groups[0].strip()
                        obj = groups[1].strip()
                        if not subj or not obj:
                            continue
                        if len(subj) < 2 or len(obj) < 1:
                            continue

                        # 实体合法性验证
                        if not self._is_valid_entity(subj):
                            # 如果有实体候选，放宽验证
                            if entity_names:
                                # 检查 subject 是否在实体候选的 context 中
                                matched = False
                                for en in entity_names:
                                    if en in subj or subj in en:
                                        matched = True
                                        break
                                if not matched:
                                    continue
                            else:
                                continue

                        # 对 object 做验证（允许数值型）
                        if not self._is_valid_entity(obj):
                            # 允许数值型object: 数字+单位 或 纯数字
                            if not re.match(r'^[\d.°C%AUkm\s\-/×x]+$', obj) \
                               and not self._is_valid_entity(obj):
                                continue

                        # 去重
                        key = f'{subj}|{rel}|{obj}'
                        if key in seen:
                            continue
                        seen.add(key)

                        triples.append({
                            'subject': subj,
                            'relation': rel,
                            'object': obj,
                            'pattern': str(pattern),
                            'raw': m.group(0),
                        })

        return triples
