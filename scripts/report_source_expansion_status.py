from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.source_expansion_status import collect_source_expansion_status


DEFAULT_OUTPUT = ROOT / "evaluation" / "source_expansion" / "source_expansion_status_report.json"


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Report local source expansion status.")
    parser.add_argument("--json-out", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    report = collect_source_expansion_status()
    write_json(Path(args.json_out), report)
    print("source | raw | triples | narratives | gate | exploratory | chroma_shadow | neo4j_rels | probe")
    print("--- | ---: | ---: | ---: | --- | ---: | ---: | ---: | ---")
    for source, item in report.items():
        print(
            f"{source} | {item['raw_count']} | {item['triple_count']} | {item['narrative_count']} | "
            f"{str(item['strict_gate_passed']).lower()} | {item['exploratory_count']} | "
            f"{item['chroma_shadow_count']} | {item['neo4j_last_import_relationships']} | {item['last_probe_status']}"
        )


if __name__ == "__main__":
    main()
