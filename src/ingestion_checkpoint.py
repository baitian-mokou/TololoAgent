import hashlib
import json
import os
import re
import time
from typing import Dict

from config import BASE_DIR


CHECKPOINT_DIR = os.path.join(BASE_DIR, "data", "ingestion_checkpoints")


def _safe_slug(value: str) -> str:
    value = str(value or "default").strip() or "default"
    return re.sub(r"[^0-9A-Za-z_.-]+", "_", value).strip("_") or "default"


def checkpoint_path(kind: str, source_name: str, data_dir: str) -> str:
    abs_dir = os.path.abspath(data_dir)
    digest = hashlib.md5(abs_dir.encode("utf-8")).hexdigest()[:12]
    filename = f"{_safe_slug(source_name)}_{_safe_slug(kind)}_{digest}.json"
    return os.path.join(CHECKPOINT_DIR, filename)


def file_signature(filepath: str) -> Dict[str, int]:
    stat = os.stat(filepath)
    mtime_ns = getattr(stat, "st_mtime_ns", int(stat.st_mtime * 1_000_000_000))
    return {"size": int(stat.st_size), "mtime_ns": int(mtime_ns)}


def load_checkpoint(path: str, kind: str) -> Dict[str, dict]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return {"processed": {}}
    if data.get("kind") != kind or not isinstance(data.get("processed"), dict):
        return {"processed": {}}
    return data


def save_checkpoint(path: str, kind: str, source_name: str, data_dir: str, processed: Dict[str, dict]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    payload = {
        "kind": kind,
        "source_name": source_name,
        "data_dir": os.path.abspath(data_dir),
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "processed": processed,
    }
    tmp_path = path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, path)


def remove_checkpoint(path: str) -> None:
    try:
        os.remove(path)
    except FileNotFoundError:
        return


def checkpoint_has_current_file(checkpoint: Dict[str, dict], filepath: str) -> bool:
    processed = checkpoint.get("processed", {})
    return processed.get(os.path.abspath(filepath)) == file_signature(filepath)


def mark_file_processed(processed: Dict[str, dict], filepath: str) -> None:
    processed[os.path.abspath(filepath)] = file_signature(filepath)
