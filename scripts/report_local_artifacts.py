from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
TARGETS = [
    "venv",
    ".venv",
    "models",
    "data/chroma_db",
    "settings.local.json",
    "error.log",
]
GLOBS = [
    "data/chroma_db.broken*",
    "data/**/chroma_db",
    "data/**/chroma_db.broken*",
    "**/chroma.sqlite3",
]


def size_of(path):
    if path.is_file():
        return path.stat().st_size
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file())


def format_size(size):
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{size} B"
        size /= 1024


def iter_artifacts():
    seen = set()
    for item in TARGETS:
        path = ROOT / item
        if path.exists():
            seen.add(path.resolve())
            yield path
    for pattern in GLOBS:
        for path in ROOT.glob(pattern):
            resolved = path.resolve()
            if resolved not in seen:
                seen.add(resolved)
                yield path


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    artifacts = sorted(iter_artifacts(), key=lambda p: str(p).lower())
    if not artifacts:
        print("未发现需要交付前关注的本地产物。")
        return

    print("本地产物统计（只报告，不删除）：")
    total = 0
    for path in artifacts:
        size = size_of(path)
        total += size
        print(f"- {path.relative_to(ROOT)}: {format_size(size)}")
    print(f"合计: {format_size(total)}")
    print("建议：正式提交/打包前不要包含以上本机产物；模型请通过下载脚本或 Ollama 重新获取。")


if __name__ == "__main__":
    main()
