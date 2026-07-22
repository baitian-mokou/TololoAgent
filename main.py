"""
托洛洛Agent - 主入口
双击启动Python图形界面
"""
import sys
import os
import builtins
from importlib.util import find_spec

_base_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _base_dir)

# ─── 依赖检查 ─────────────────────────────────
_REQUIRED_IMPORTS = {
    "beautifulsoup4": "bs4",
    "chromadb": "chromadb",
    "huggingface-hub": "huggingface_hub",
    "jieba": "jieba",
    "neo4j": "neo4j",
    "numpy": "numpy",
    "opencc-python-reimplemented": "opencc",
    "pillow": "PIL",
    "pystray": "pystray",
    "requests": "requests",
    "sentence-transformers": "sentence_transformers",
    "torch": "torch",
    "ttkbootstrap": "ttkbootstrap",
}


def _missing_required_dependencies():
    return [
        package
        for package, import_name in _REQUIRED_IMPORTS.items()
        if find_spec(import_name) is None
    ]


def _exit_if_required_dependencies_missing():
    missing = _missing_required_dependencies()
    if not missing:
        return

    print("[TololoAgent] 缺少 Python 依赖，已停止启动。")
    print("缺失包：")
    for package in missing:
        print(f"  - {package}")
    print()
    print("请先在项目目录运行：")
    print("  python -m pip install -r requirements.txt")
    print()
    print("如果使用虚拟环境，请先激活 venv 后再执行安装命令。")
    sys.exit(1)

# ─── 全局修复 Windows 下打印中文的编码问题 ─────────────────
_original_print = builtins.print


def _safe_print(*args, **kwargs):
    try:
        _original_print(*args, **kwargs)
    except (UnicodeEncodeError, ValueError, OSError):
        try:
            text = " ".join(str(a) for a in args)
            safe_text = text.encode(
                sys.stdout.encoding or 'utf-8', errors='replace'
            ).decode(
                sys.stdout.encoding or 'utf-8', errors='replace'
            )
            _original_print(safe_text, **kwargs)
        except Exception:
            pass


if not sys.stdout or not hasattr(sys.stdout, 'encoding') or sys.stdout.encoding is None:
    builtins.print = _safe_print
elif 'utf-8' not in sys.stdout.encoding.lower():
    builtins.print = _safe_print

# ─── 捕获静默错误 ─────────────────
_error_log_path = os.path.join(_base_dir, "error.log")


def _log_error(e):
    import traceback
    try:
        with open(_error_log_path, "w", encoding="utf-8") as f:
            f.write("TololoAgent Crash Report\n")
            f.write("=" * 50 + "\n")
            traceback.print_exc(file=f)
    except Exception:
        pass


def main():
    _exit_if_required_dependencies_missing()
    try:
        from src.gui.main_window import run_gui
    except Exception as e:
        _log_error(e)
        raise

    try:
        run_gui()
    except Exception as e:
        _log_error(e)
        raise


if __name__ == "__main__":
    main()
