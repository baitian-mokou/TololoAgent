"""
托洛洛Agent - 主入口
双击启动Python图形界面
"""
import sys
import os
import builtins

_base_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _base_dir)

# ─── 自动修复依赖 ─────────────────────────────────
# 如果 ttkbootstrap 未安装，自动 pip install
_MISSING_DEPS = []

try:
    import ttkbootstrap
except ImportError:
    _MISSING_DEPS.append("ttkbootstrap")

try:
    import opencc
except ImportError:
    _MISSING_DEPS.append("opencc-python-reimplemented")

try:
    import pystray
except ImportError:
    _MISSING_DEPS.append("pystray")

if _MISSING_DEPS:
    import subprocess
    print(f"[TololoAgent] 检测到缺少依赖: {_MISSING_DEPS}，正在自动安装...")
    for dep in _MISSING_DEPS:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", dep, "-q"],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            print(f"[ERROR] 安装 {dep} 失败: {result.stderr}")
            print(f"[INFO] 请手动运行: {sys.executable} -m pip install {dep}")
            sys.exit(1)
        else:
            print(f"[OK] {dep} 安装成功")
    # 重新导入
    import ttkbootstrap

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


try:
    from src.gui.main_window import run_gui as _run_gui
except Exception as e:
    _log_error(e)
    raise


if __name__ == "__main__":
    try:
        _run_gui()
    except Exception as e:
        _log_error(e)
        raise
