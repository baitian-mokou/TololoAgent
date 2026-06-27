import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from config import BASE_DIR


def structured(source, schema, qid, category, query, expected, hit=True, normalized=None):
    item = {
        "id": qid,
        "category": category,
        "query_kind": "structured",
        "query": query,
        "expected_path": "fallback",
        "allowed_final_sources": ["fallback"],
        "expected_top_k_hit": hit,
        "expected_result": expected if hit else {"empty": True},
        "source_filter": [source],
        "source_schema_version": schema,
    }
    if normalized:
        item["normalized_expected_value"] = normalized
    return item


def narrative(source, schema, qid, category, query, title, sections, hit=True):
    item = {
        "id": qid,
        "category": category,
        "query_kind": "narrative",
        "query": query,
        "expected_path": "fallback",
        "allowed_final_sources": ["fallback"],
        "expected_top_k_hit": hit,
        "expected_result": {"page_title": title, "section_any_of": sections} if hit else {"empty": True},
        "source_filter": [source],
        "source_schema_version": schema,
    }
    if hit:
        item["expected_page_title"] = title
        item["expected_section_any_of"] = sections
    return item


def write_json(path, payload):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def main():
    wikidata_schema = "wikidata_shadow_ready_v1"
    nasa_schema = "nasa_shadow_ready_v1"

    wikidata_queries = [
        structured("wikidata", wikidata_schema, "wikidata_structured_phobos_orbits", "structured", "火卫一绕谁公转", {"subject": "火卫一", "relation": "ORBITS", "object": "火星"}),
        structured("wikidata", wikidata_schema, "wikidata_structured_deimos_discoverer", "structured", "火卫二是谁发现的", {"subject": "火卫二", "relation": "DISCOVERED_BY", "object": "阿萨夫·霍尔"}),
        structured("wikidata", wikidata_schema, "wikidata_structured_moon_orbits", "structured", "月球绕谁运行", {"subject": "月球", "relation": "ORBITS", "object": "地球"}),
        structured("wikidata", wikidata_schema, "wikidata_structured_pluto_part_of", "structured", "冥王星属于哪里", {"subject": "冥王星", "relation": "PART_OF", "object": "柯伊伯带"}),
        structured("wikidata", wikidata_schema, "wikidata_structured_ceres_discoverer", "structured", "谷神星是谁发现的", {"subject": "谷神星", "relation": "DISCOVERED_BY", "object": "朱塞普·皮亚齐"}),
        narrative("wikidata", wikidata_schema, "wikidata_narrative_mars_atmosphere", "narrative", "火星大气成分", "火星", ["大气"]),
        narrative("wikidata", wikidata_schema, "wikidata_narrative_jupiter_atmosphere", "narrative", "木星大气有什么成分", "木星", ["大气"]),
        narrative("wikidata", wikidata_schema, "wikidata_narrative_galilean_moon", "narrative", "木卫三是伽利略卫星吗", "木卫三", ["伽利略卫星"]),
        structured("wikidata", wikidata_schema, "wikidata_negative_unknown_satellite", "negative", "Wikidata 不存在的火星第三颗卫星绕谁运行", {}, hit=False),
        narrative("wikidata", wikidata_schema, "wikidata_negative_wrong_source_term", "negative", "完全不存在的 ESA 测试条目叙事", "", [], hit=False),
        structured("wikidata", wikidata_schema, "wikidata_fallback_local_graph", "fallback", "木卫一绕谁运行", {"subject": "木卫一", "relation": "ORBITS", "object": "木星"}),
        narrative("wikidata", wikidata_schema, "wikidata_fallback_local_narrative", "fallback", "冥王星的分类信息", "冥王星", ["分类"]),
        structured("wikidata", wikidata_schema, "wikidata_source_isolation_no_zhwiki", "source_isolation", "海王星是谁发现的", {"subject": "海王星", "relation": "DISCOVERED_BY", "object": "约翰·伽勒"}),
        narrative("wikidata", wikidata_schema, "wikidata_source_isolation_no_nasa", "source_isolation", "金星大气二氧化碳", "金星", ["大气"]),
        structured("wikidata", wikidata_schema, "wikidata_metadata_structured_schema", "metadata_completeness", "天王星是谁发现的", {"subject": "天王星", "relation": "DISCOVERED_BY", "object": "威廉·赫歇尔"}),
        narrative("wikidata", wikidata_schema, "wikidata_metadata_narrative_schema", "metadata_completeness", "谷神星发现者叙事", "谷神星", ["发现"]),
        structured("wikidata", wikidata_schema, "wikidata_path_routing_structured", "path_routing", "火星质量是多少", {"subject": "火星", "relation": "HAS_MASS", "object": "6.4171e23 kg"}, normalized="6.4171e23kg"),
        narrative("wikidata", wikidata_schema, "wikidata_path_routing_narrative", "path_routing", "土星大气成分说明", "土星", ["大气"]),
        structured("wikidata", wikidata_schema, "wikidata_unit_mars_mass", "unit_normalization", "火星的质量", {"subject": "火星", "relation": "HAS_MASS", "object": "6.4171e23 kg"}, normalized="6.4171e23kg"),
        structured("wikidata", wikidata_schema, "wikidata_unit_jupiter_radius", "unit_normalization", "木星半径是多少", {"subject": "木星", "relation": "HAS_RADIUS", "object": "69911 km"}, normalized="69911km"),
        structured("wikidata", wikidata_schema, "wikidata_unit_moon_radius", "unit_normalization", "月球半径是多少", {"subject": "月球", "relation": "HAS_RADIUS", "object": "1737.4 km"}, normalized="1737.4km"),
        structured("wikidata", wikidata_schema, "wikidata_conflict_pluto_region", "conflict_case", "冥王星属于柯伊伯带还是八大行星", {"subject": "冥王星", "relation": "PART_OF", "object": "柯伊伯带"}),
        structured("wikidata", wikidata_schema, "wikidata_conflict_mars_atmosphere", "conflict_case", "火星大气是氧气还是二氧化碳为主", {"subject": "火星", "relation": "HAS_ATMOSPHERE", "object": "二氧化碳;氮气;氩气"}),
        structured("wikidata", wikidata_schema, "wikidata_conflict_ceres_region", "conflict_case", "谷神星属于小行星带还是柯伊伯带", {"subject": "谷神星", "relation": "PART_OF", "object": "小行星带"}),
    ]

    nasa_queries = [
        structured("nasa", nasa_schema, "nasa_structured_phobos_orbits", "structured", "火卫一绕谁公转", {"subject": "火卫一", "relation": "ORBITS", "object": "火星"}),
        structured("nasa", nasa_schema, "nasa_structured_mars_mass_expected_absent", "structured", "火星质量是多少", {}, hit=False),
        structured("nasa", nasa_schema, "nasa_structured_mars_radius_expected_absent", "structured", "火星半径是多少", {}, hit=False),
        narrative("nasa", nasa_schema, "nasa_narrative_mars_atmosphere", "narrative", "火星大气成分", "火星", ["大气"]),
        narrative("nasa", nasa_schema, "nasa_narrative_mars_weather", "narrative", "火星为什么寒冷干燥", "火星", ["大气"]),
        narrative("nasa", nasa_schema, "nasa_narrative_phobos_context_absent", "narrative", "火卫一任务页面摘要", "", [], hit=False),
        structured("nasa", nasa_schema, "nasa_negative_deimos_absent", "negative", "火卫二绕谁公转", {}, hit=False),
        structured("nasa", nasa_schema, "nasa_negative_jupiter_absent", "negative", "木星大气成分", {}, hit=False),
        structured("nasa", nasa_schema, "nasa_negative_wikidata_only_absent", "negative", "谷神星是谁发现的", {}, hit=False),
        structured("nasa", nasa_schema, "nasa_fallback_local_graph", "fallback", "火卫一是火星的卫星吗", {"subject": "火卫一", "relation": "ORBITS", "object": "火星"}),
        narrative("nasa", nasa_schema, "nasa_fallback_local_narrative", "fallback", "NASA Mars Fact Sheet 火星大气", "火星", ["大气"]),
        structured("nasa", nasa_schema, "nasa_source_isolation_no_wikidata", "source_isolation", "冥王星是谁发现的", {}, hit=False),
        narrative("nasa", nasa_schema, "nasa_source_isolation_no_zhwiki", "source_isolation", "地球大气成分", "", [], hit=False),
        structured("nasa", nasa_schema, "nasa_metadata_structured_schema", "metadata_completeness", "火卫一绕谁运行 metadata", {"subject": "火卫一", "relation": "ORBITS", "object": "火星"}),
        narrative("nasa", nasa_schema, "nasa_metadata_narrative_schema", "metadata_completeness", "火星大气 schema version", "火星", ["大气"]),
        structured("nasa", nasa_schema, "nasa_path_routing_structured", "path_routing", "火卫一轨道主星", {"subject": "火卫一", "relation": "ORBITS", "object": "火星"}),
        narrative("nasa", nasa_schema, "nasa_path_routing_narrative", "path_routing", "火星表面气压为什么低", "火星", ["大气"]),
        narrative("nasa", nasa_schema, "nasa_unit_atmosphere_percent_co2", "unit_normalization", "火星二氧化碳约占多少百分比", "火星", ["大气"]),
        narrative("nasa", nasa_schema, "nasa_unit_atmosphere_percent_nitrogen", "unit_normalization", "火星氮气约 2.7%", "火星", ["大气"]),
        narrative("nasa", nasa_schema, "nasa_conflict_mars_co2", "conflict_case", "火星大气主要是氧气还是二氧化碳", "火星", ["大气"]),
        structured("nasa", nasa_schema, "nasa_conflict_no_multisource_pluto", "conflict_case", "NASA shadow 里冥王星属于柯伊伯带吗", {}, hit=False),
        structured("nasa", nasa_schema, "nasa_conflict_no_wikidata_mass", "conflict_case", "NASA shadow 用 Wikidata 火星质量回答吗", {}, hit=False),
    ]

    common_gates = {
        "source_filter_failure_max": 0,
        "metadata_contract_break_max": 0,
        "inferred_boundary_break_max": 0,
        "query_explainability_degraded_max": 0,
    }
    write_json(os.path.join(BASE_DIR, "evaluation", "source_expansion", "wikidata", "wikidata_queries.json"), {
        "version": "source_expansion_gold_set_v2",
        "source_name": "wikidata",
        "source_schema_version": wikidata_schema,
        "approval_mode": "owner-approved exception",
        "owner_override": True,
        "top_k_default": 5,
        "force_local_graph_fallback": True,
        "force_local_narrative_fallback": True,
        "gates": {"exact_accuracy_min": 0.65, **common_gates},
        "queries": wikidata_queries,
    })
    write_json(os.path.join(BASE_DIR, "evaluation", "source_expansion", "nasa", "nasa_queries.json"), {
        "version": "source_expansion_gold_set_v2",
        "source_name": "nasa",
        "source_schema_version": nasa_schema,
        "source_purpose": "authoritative_fact_verification_and_numeric_supplement",
        "top_k_default": 5,
        "force_local_graph_fallback": True,
        "force_local_narrative_fallback": True,
        "gates": {"exact_accuracy_min": 0.35, **common_gates},
        "queries": nasa_queries,
    })


if __name__ == "__main__":
    main()
