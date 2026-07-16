import argparse
import glob
import json
import os
import re
import shutil
import sys
from typing import Dict, List

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from config import BASE_DIR, TRIPLES_DIR
from src.knowledge_graph.neo4j_loader import Neo4jLoader
from src.nlp.text_normalizer import normalize_to_simplified
from src.source_control import ACTIVE_SOURCE, ORIGIN_INTERNAL_LINK, SOURCE_ROLE, get_source_schema_version

EXPORT_ROOT = os.path.join(BASE_DIR, 'data', 'presentation_exports', 'solar_system_pack')
MERGED_PATH = os.path.join(BASE_DIR, 'data', 'presentation_exports', 'solar_system_triples_merged.json')
REPORT_PATH = os.path.join(BASE_DIR, 'data', 'presentation_exports', 'solar_system_import_report.json')

PLANETS = [
    '水星', '金星', '地球', '火星', '木星', '土星', '天王星', '海王星', '冥王星',
]
SATELLITES = [
    '月球', '火卫一', '木卫一', '木卫二', '木卫四', '土卫一', '土卫四', '土卫五',
    '土卫六', '土卫七', '土卫八', '天卫一', '天卫二', '天卫四', '天卫五', '冥卫一',
]
OVERVIEW_PAGES = [
    '地球#卫星', '火星的卫星', '木星的卫星', '天王星的卫星', '海王星的卫星', '冥王星的卫星', '伽利略卫星',
]
HOST_MAP = {
    '月球': '地球',
    '火卫一': '火星',
    '木卫一': '木星',
    '木卫二': '木星',
    '木卫四': '木星',
    '土卫一': '土星',
    '土卫四': '土星',
    '土卫五': '土星',
    '土卫六': '土星',
    '土卫七': '土星',
    '土卫八': '土星',
    '天卫一': '天王星',
    '天卫二': '天王星',
    '天卫四': '天王星',
    '天卫五': '天王星',
    '冥卫一': '冥王星',
}
ATMOSPHERE_MAP = {
    '水星': '稀薄外逸层',
    '金星': '二氧化碳,氮',
    '地球': '氮,氧,氩,二氧化碳',
    '火星': '二氧化碳,氮,氩',
    '木星': '氢,氦,甲烷,氨',
    '土星': '氢,氦,甲烷,氨',
    '天王星': '氢,氦,甲烷',
    '海王星': '氢,氦,甲烷',
    '冥王星': '氮,甲烷,一氧化碳',
    '土卫六': '氮,甲烷',
}
TYPE_MAP = {
    **{name: '行星' for name in PLANETS[:-1]},
    '冥王星': '矮行星',
    **{name: '天然卫星' for name in SATELLITES},
    '地球#卫星': '天然卫星系统',
    '火星的卫星': '天然卫星系统',
    '木星的卫星': '天然卫星系统',
    '天王星的卫星': '天然卫星系统',
    '海王星的卫星': '天然卫星系统',
    '冥王星的卫星': '天然卫星系统',
    '伽利略卫星': '天然卫星群',
}
PAGE_PART_OF = {
    '地球#卫星': '地球系统',
    '火星的卫星': '火星系统',
    '木星的卫星': '木星系统',
    '天王星的卫星': '天王星系统',
    '海王星的卫星': '海王星系统',
    '冥王星的卫星': '冥王星系统',
    '伽利略卫星': '木星系统',
}



def split_atmosphere_value(value: str) -> List[str]:
    text = normalize_to_simplified(value or '').strip()
    if not text:
        return []
    parts = [item.strip() for item in re.split(r'[,，、/]+', text) if item.strip()]
    if not parts:
        return [text]
    deduped = []
    seen = set()
    for item in parts:
        if item in seen:
            continue
        seen.add(item)
        deduped.append(item)
    return deduped
def configure_stdout():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')


def ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)


def load_json(path: str):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def dump_json(path: str, payload):
    ensure_dir(os.path.dirname(path))
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def make_triple(subject: str, relation: str, obj: str, raw: str, *, source_title: str = '') -> dict:
    return {
        'subject': subject,
        'relation': relation,
        'object': obj,
        'pattern': 'rule',
        'raw': raw,
        'source': ACTIVE_SOURCE,
        'source_name': ACTIVE_SOURCE,
        'source_role': SOURCE_ROLE,
        'origin': ORIGIN_INTERNAL_LINK,
        'type': 'triple_candidate',
        'source_title': source_title or subject,
        'schema_version': get_source_schema_version(ACTIVE_SOURCE),
    }


def existing_triple_files() -> Dict[str, str]:
    mapping = {}
    for path in glob.glob(os.path.join(TRIPLES_DIR, '*_triples.json')):
        name = os.path.basename(path)[:-len('_triples.json')]
        mapping[name] = path
    return mapping


def existing_narrative_files() -> Dict[str, str]:
    mapping = {}
    for path in glob.glob(os.path.join(TRIPLES_DIR, '*_narratives.json')):
        name = os.path.basename(path)[:-len('_narratives.json')]
        mapping[name] = path
    return mapping


def augment_entity_triples(name: str, triples: List[dict]) -> List[dict]:
    by_key = {}
    loader = Neo4jLoader()
    try:
        for triple in triples:
            cleaned = loader._clean_graph_triple(triple)
            if not cleaned:
                continue
            key = (cleaned['subject'], cleaned['relation'], cleaned['object'])
            by_key[key] = cleaned

        subject = name
        if subject in PLANETS:
            synthetic = [
                make_triple(subject, 'ORBITS', '太阳', f'{subject}绕太阳公转'),
                make_triple(subject, 'LOCATED_IN', '太阳系', f'{subject}位于太阳系'),
                make_triple(subject, 'IS_A', TYPE_MAP.get(subject, '行星'), f'{subject}是{TYPE_MAP.get(subject, "行星")}'),
            ]
            atm = ATMOSPHERE_MAP.get(subject)
            if atm:
                for component in split_atmosphere_value(atm):
                    synthetic.append(
                        make_triple(
                            subject,
                            'HAS_ATMOSPHERE',
                            component,
                            f'{subject}大气主要由{component}组成',
                        )
                    )
        elif subject in SATELLITES:
            host = HOST_MAP.get(subject)
            synthetic = [
                make_triple(subject, 'LOCATED_IN', '太阳系', f'{subject}位于太阳系'),
                make_triple(subject, 'IS_A', TYPE_MAP.get(subject, '天然卫星'), f'{subject}是{TYPE_MAP.get(subject, "天然卫星")}'),
            ]
            if host:
                synthetic.append(make_triple(subject, 'ORBITS', host, f'{subject}绕{host}公转'))
                synthetic.append(make_triple(subject, 'PART_OF', f'{host}系统', f'{subject}属于{host}系统'))
            atm = ATMOSPHERE_MAP.get(subject)
            if atm:
                for component in split_atmosphere_value(atm):
                    synthetic.append(
                        make_triple(
                            subject,
                            'HAS_ATMOSPHERE',
                            component,
                            f'{subject}大气主要由{component}组成',
                        )
                    )
        else:
            synthetic = []

        for triple in synthetic:
            cleaned = loader._clean_graph_triple(triple)
            if not cleaned:
                continue
            key = (cleaned['subject'], cleaned['relation'], cleaned['object'])
            by_key[key] = cleaned
        return list(by_key.values())
    finally:
        loader.close()


def build_overview_triples(name: str) -> List[dict]:
    triples = [
        make_triple(name, 'IS_A', TYPE_MAP.get(name, '天然卫星系统'), f'{name}是{TYPE_MAP.get(name, "天然卫星系统")}'),
        make_triple(name, 'LOCATED_IN', '太阳系', f'{name}位于太阳系'),
    ]
    part_of = PAGE_PART_OF.get(name)
    if part_of:
        triples.append(make_triple(name, 'PART_OF', part_of, f'{name}属于{part_of}'))
    if name == '伽利略卫星':
        triples.extend([
            make_triple('木卫一', 'PART_OF', '伽利略卫星', '木卫一属于伽利略卫星', source_title='伽利略卫星'),
            make_triple('木卫二', 'PART_OF', '伽利略卫星', '木卫二属于伽利略卫星', source_title='伽利略卫星'),
            make_triple('木卫四', 'PART_OF', '伽利略卫星', '木卫四属于伽利略卫星', source_title='伽利略卫星'),
        ])
    loader = Neo4jLoader()
    try:
        cleaned = []
        for triple in triples:
            item = loader._clean_graph_triple(triple)
            if item:
                cleaned.append(item)
        return cleaned
    finally:
        loader.close()


def copy_if_exists(src: str, dst: str):
    if src and os.path.exists(src):
        shutil.copy2(src, dst)


def main():
    configure_stdout()
    parser = argparse.ArgumentParser(description='Build and optionally import a presentation solar-system dataset.')
    parser.add_argument('--import-neo4j', action='store_true', help='Import the curated dataset into Neo4j after building it.')
    args = parser.parse_args()

    ensure_dir(EXPORT_ROOT)
    if os.path.isdir(EXPORT_ROOT):
        for item in os.listdir(EXPORT_ROOT):
            path = os.path.join(EXPORT_ROOT, item)
            if os.path.isfile(path):
                os.remove(path)

    triple_map = existing_triple_files()
    narrative_map = existing_narrative_files()

    merged = []
    exported_files = []
    selected_entities = PLANETS + SATELLITES

    for name in selected_entities:
        triples = load_json(triple_map[name]) if name in triple_map else []
        augmented = augment_entity_triples(name, triples)
        triple_out = os.path.join(EXPORT_ROOT, f'{name}_triples.json')
        dump_json(triple_out, augmented)
        exported_files.append(triple_out)
        merged.extend(augmented)

        if name in narrative_map:
            narrative_out = os.path.join(EXPORT_ROOT, f'{name}_narratives.json')
            copy_if_exists(narrative_map[name], narrative_out)
            exported_files.append(narrative_out)

    for name in OVERVIEW_PAGES:
        overview_triples = build_overview_triples(name)
        triple_out = os.path.join(EXPORT_ROOT, f'{name}_triples.json')
        dump_json(triple_out, overview_triples)
        exported_files.append(triple_out)
        merged.extend(overview_triples)
        if name in narrative_map:
            narrative_out = os.path.join(EXPORT_ROOT, f'{name}_narratives.json')
            copy_if_exists(narrative_map[name], narrative_out)
            exported_files.append(narrative_out)

    dedup = {}
    for item in merged:
        key = (item['subject'], item['relation'], item['object'])
        dedup[key] = item
    merged = list(dedup.values())
    dump_json(MERGED_PATH, merged)

    report = {
        'export_root': EXPORT_ROOT,
        'merged_path': MERGED_PATH,
        'entity_count': len(selected_entities) + len(OVERVIEW_PAGES),
        'triple_count': len(merged),
        'exported_files': [os.path.basename(path) for path in exported_files],
        'imported': False,
    }

    if args.import_neo4j:
        loader = Neo4jLoader()
        try:
            nodes, rels = loader.load_all_triples(triples_dir=EXPORT_ROOT)
            stats = loader.get_stats()
        finally:
            loader.close()
        report['imported'] = True
        report['neo4j'] = {
            'loaded_nodes': nodes,
            'loaded_relationships': rels,
            'stats': stats,
        }

    dump_json(REPORT_PATH, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
