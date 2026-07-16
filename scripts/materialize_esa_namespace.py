import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from config import BASE_DIR, RAW_JSON_DIR, TRIPLES_DIR
from src.agent.llm_agent import LLMAgent
from src.source_adapters.esa import EsaSmokeAdapter
from src.vector_store.chroma_store import ChromaStore


DEFAULT_OUTPUT = os.path.join(BASE_DIR, "evaluation", "source_expansion", "esa", "esa_materialization_report.json")


def configure_stdout() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")


def main() -> None:
    configure_stdout()
    parser = argparse.ArgumentParser(description="Materialize the ESA adapter smoke namespace.")
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--fixture", default=None)
    parser.add_argument(
        "--mode",
        choices=["offline", "dry-run", "live"],
        default="offline",
        help="Source adapter mode. Defaults to offline; ESA live currently falls back to offline smoke data.",
    )
    args = parser.parse_args()

    adapter = EsaSmokeAdapter(
        fixture_path=args.fixture,
        mode=args.mode,
        base_dir=BASE_DIR,
        raw_json_dir=RAW_JSON_DIR,
        triples_dir=TRIPLES_DIR,
        chroma_store_cls=ChromaStore,
        agent_cls=LLMAgent,
    )
    payload = adapter.materialize(args.output)
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
