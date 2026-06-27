import json
import os
import sys
import argparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from config import BASE_DIR, RAW_JSON_DIR, TRIPLES_DIR
from src.agent.llm_agent import LLMAgent
from src.knowledge_graph.neo4j_loader import Neo4jLoader
from src.source_adapters.wikidata import WikidataFixtureAdapter
from src.vector_store.chroma_store import ChromaStore


WIKIDATA_SOURCE = "wikidata"
DEFAULT_OUTPUT = os.path.join(
    BASE_DIR,
    "evaluation",
    "source_expansion",
    "wikidata",
    "wikidata_materialization_report.json",
)
DEFAULT_PREVIEW_OUTPUT = os.path.join(
    BASE_DIR,
    "evaluation",
    "source_expansion",
    "wikidata",
    "wikidata_live_preview_report.json",
)


def configure_stdout() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")


def main() -> None:
    configure_stdout()
    parser = argparse.ArgumentParser(description="Materialize the Wikidata shadow namespace.")
    parser.add_argument(
        "--output",
        default=None,
        help="Path to write the auditable materialization report.",
    )
    parser.add_argument(
        "--mode",
        choices=["offline", "dry-run", "live"],
        default="offline",
        help="Source adapter mode. Defaults to offline; live must be requested explicitly.",
    )
    parser.add_argument(
        "--entity",
        default="火星",
        help="Wikidata QID or Chinese entity name for live/dry-run preview.",
    )
    parser.add_argument(
        "--fixture",
        default=None,
        help="Offline Wikidata fixture path. Live fetch is intentionally not enabled.",
    )
    args = parser.parse_args()
    output_path = args.output or (DEFAULT_OUTPUT if args.mode == "offline" else DEFAULT_PREVIEW_OUTPUT)

    adapter = WikidataFixtureAdapter(
        fixture_path=args.fixture,
        entity=args.entity,
        mode=args.mode,
        base_dir=BASE_DIR,
        raw_json_dir=RAW_JSON_DIR,
        triples_dir=TRIPLES_DIR,
        graph_loader_cls=Neo4jLoader,
        chroma_store_cls=ChromaStore,
        agent_cls=LLMAgent,
    )
    payload = adapter.materialize(output_path)
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
