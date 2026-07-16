import json
import os
import sys
import argparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from config import BASE_DIR, RAW_JSON_DIR, TRIPLES_DIR
from src.agent.llm_agent import LLMAgent
from src.source_adapters.nasa import NasaPipelineAdapter
from src.vector_store.chroma_store import ChromaStore


NASA_SOURCE = "nasa"
DEFAULT_OUTPUT = os.path.join(BASE_DIR, "evaluation", "source_expansion", "nasa", "nasa_materialization_report.json")
DEFAULT_PREVIEW_OUTPUT = os.path.join(BASE_DIR, "evaluation", "source_expansion", "nasa", "nasa_live_preview_report.json")


def configure_stdout() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")


def main() -> None:
    configure_stdout()
    parser = argparse.ArgumentParser(description="Materialize the NASA source-expansion namespace.")
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
        help="NASA fact source entity for live/dry-run preview.",
    )
    args = parser.parse_args()
    output_path = args.output or (DEFAULT_OUTPUT if args.mode == "offline" else DEFAULT_PREVIEW_OUTPUT)

    adapter = NasaPipelineAdapter(
        entity=args.entity,
        mode=args.mode,
        base_dir=BASE_DIR,
        raw_json_dir=RAW_JSON_DIR,
        triples_dir=TRIPLES_DIR,
        chroma_store_cls=ChromaStore,
        agent_cls=LLMAgent,
    )
    payload = adapter.materialize(output_path)
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
