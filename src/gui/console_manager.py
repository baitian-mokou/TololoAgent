"""
Windows 控制台显示/隐藏与托盘联动辅助
"""
from __future__ import annotations

import os
import threading
from pathlib import Path

try:
    import ctypes
except ImportError:
    ctypes = None

try:
    import pystray
    from pystray import MenuItem as TrayMenuItem
except ImportError:
    pystray = None
    TrayMenuItem = None

try:
    from PIL import Image
except ImportError:
    Image = None


SW_HIDE = 0
SW_SHOW = 5
SW_RESTORE = 9
GWL_EXSTYLE = -20
WS_EX_APPWINDOW = 0x00040000
WS_EX_TOOLWINDOW = 0x00000080
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_FRAMECHANGED = 0x0020

ICON_PATH = Path(__file__).resolve().parent / "assets" / "tololo_icon.png"


def _get_console_hwnd() -> int:
    if os.name != "nt" or ctypes is None:
        return 0
    try:
        return int(ctypes.windll.kernel32.GetConsoleWindow())
    except Exception:
        return 0


class _ConsoleTrayController:
    def __init__(self):
        self._icon = None
        self._icon_thread = None
        self._lock = threading.Lock()

    def has_console(self) -> bool:
        return _get_console_hwnd() != 0

    def is_visible(self) -> bool:
        hwnd = _get_console_hwnd()
        if not hwnd or ctypes is None:
            return False
        try:
            return bool(ctypes.windll.user32.IsWindowVisible(hwnd))
        except Exception:
            return False

    def is_minimized(self) -> bool:
        hwnd = _get_console_hwnd()
        if not hwnd or ctypes is None:
            return False
        try:
            return bool(ctypes.windll.user32.IsIconic(hwnd))
        except Exception:
            return False

    def show_console(self) -> bool:
        hwnd = _get_console_hwnd()
        if not hwnd or ctypes is None:
            return False
        try:
            self._set_taskbar_mode(hwnd, show_in_taskbar=True)
            if self.is_minimized():
                ctypes.windll.user32.ShowWindow(hwnd, SW_RESTORE)
            else:
                ctypes.windll.user32.ShowWindow(hwnd, SW_SHOW)
            ctypes.windll.user32.SetForegroundWindow(hwnd)
            self._hide_tray_icon()
            return True
        except Exception:
            return False

    def hide_console(self) -> bool:
        hwnd = _get_console_hwnd()
        if not hwnd or ctypes is None:
            return False
        try:
            self._set_taskbar_mode(hwnd, show_in_taskbar=False)
            ctypes.windll.user32.ShowWindow(hwnd, SW_HIDE)
            self._show_tray_icon()
            return True
        except Exception:
            return False

    def shutdown(self):
        self._hide_tray_icon()

    def _show_tray_icon(self):
        if pystray is None or Image is None or not ICON_PATH.exists():
            return

        with self._lock:
            if self._icon is not None:
                return

            image = Image.open(ICON_PATH)
            menu = pystray.Menu(
                TrayMenuItem("显示终端", lambda icon, item: self.show_console()),
                TrayMenuItem("隐藏终端", lambda icon, item: self.hide_console()),
            )
            self._icon = pystray.Icon("tololo_console", image, "TololoAgent 终端", menu)
            self._icon_thread = threading.Thread(target=self._icon.run, daemon=True)
            self._icon_thread.start()

    def _hide_tray_icon(self):
        with self._lock:
            if self._icon is None:
                return
            try:
                self._icon.stop()
            except Exception:
                pass
            self._icon = None
            self._icon_thread = None

    def _set_taskbar_mode(self, hwnd: int, *, show_in_taskbar: bool):
        if ctypes is None or not hwnd:
            return

        style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        if show_in_taskbar:
            style = (style | WS_EX_APPWINDOW) & ~WS_EX_TOOLWINDOW
        else:
            style = (style | WS_EX_TOOLWINDOW) & ~WS_EX_APPWINDOW

        ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
        ctypes.windll.user32.SetWindowPos(
            hwnd,
            0,
            0,
            0,
            0,
            0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED,
        )


_controller = _ConsoleTrayController()


def has_console() -> bool:
    return _controller.has_console()


def is_console_visible() -> bool:
    return _controller.is_visible()


def is_console_minimized() -> bool:
    return _controller.is_minimized()


def show_console() -> bool:
    return _controller.show_console()


def hide_console() -> bool:
    return _controller.hide_console()


def shutdown_console_manager():
    _controller.shutdown()
