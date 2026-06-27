"""
Windows 窗口外观辅助：标题栏深色模式、系统主题跟随、应用图标
"""
from __future__ import annotations

import os
import tkinter as tk
from pathlib import Path

try:
    import ctypes
    import winreg
except ImportError:  # 非 Windows 平台
    ctypes = None
    winreg = None


ASSET_DIR = Path(__file__).resolve().parent / "assets"
ICON_PNG_PATH = ASSET_DIR / "tololo_icon.png"
ICON_ICO_PATH = ASSET_DIR / "tololo_icon.ico"

_PERSONALIZE_KEY = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
_APPS_USE_LIGHT_THEME = "AppsUseLightTheme"
_DWMWA_USE_IMMERSIVE_DARK_MODE = (20, 19)
_DWMWA_BORDER_COLOR = 34
_DWMWA_CAPTION_COLOR = 35
_DWMWA_TEXT_COLOR = 36
_APP_USER_MODEL_ID = "TololoAgent.GUI"
_GA_ROOT = 2

_DARK_CAPTION_COLOR = 0x00242424
_DARK_TEXT_COLOR = 0x00F2F2F2
_LIGHT_CAPTION_COLOR = 0x00F3F3F3
_LIGHT_TEXT_COLOR = 0x00101010


def theme_prefers_dark(theme_name: str) -> bool:
    """根据应用主题判断兜底是否应使用深色标题栏"""
    return theme_name in {"dark", "tololo"}


class WindowCustomizer:
    """统一处理窗口图标与 Windows 标题栏风格"""

    def __init__(self):
        self._watched_windows = {}

    @property
    def is_windows(self) -> bool:
        return os.name == "nt" and ctypes is not None

    def apply_icon(self, window: tk.Tk | tk.Toplevel):
        """为窗口设置应用图标，同时覆盖标题栏和任务栏图标"""
        self._apply_app_user_model_id()

        if ICON_PNG_PATH.exists():
            try:
                icon_image = tk.PhotoImage(file=str(ICON_PNG_PATH))
                window.iconphoto(True, icon_image)
                window._tololo_icon_image = icon_image
            except tk.TclError:
                pass

        if self.is_windows and ICON_ICO_PATH.exists():
            try:
                window.iconbitmap(str(ICON_ICO_PATH))
            except tk.TclError:
                pass

    def _apply_app_user_model_id(self):
        if not self.is_windows:
            return
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(_APP_USER_MODEL_ID)
        except Exception:
            pass

    def watch_titlebar_theme(self, window: tk.Tk | tk.Toplevel, fallback_dark: bool):
        """让 Windows 标题栏尽量跟随系统明暗主题，不支持时退回应用主题"""
        if not self.is_windows:
            return

        key = str(window)
        state = self._watched_windows.get(key)
        if state is None:
            state = {
                "window": window,
                "fallback_dark": fallback_dark,
                "after_id": None,
                "last_dark": None,
            }
            self._watched_windows[key] = state
        else:
            state["fallback_dark"] = fallback_dark

        window.after_idle(lambda: self._apply_titlebar_style(state))
        self._schedule_poll(state)

    def _schedule_poll(self, state: dict):
        window = state["window"]
        if not self._system_theme_available():
            return
        if not self._window_exists(window):
            self._forget_window(window)
            return
        if state["after_id"] is not None:
            try:
                window.after_cancel(state["after_id"])
            except tk.TclError:
                pass
        state["after_id"] = window.after(1200, lambda: self._poll_titlebar_style(str(window)))

    def _poll_titlebar_style(self, window_key: str):
        state = self._watched_windows.get(window_key)
        if not state:
            return

        window = state["window"]
        if not self._window_exists(window):
            self._forget_window(window)
            return

        self._apply_titlebar_style(state)
        self._schedule_poll(state)

    def _apply_titlebar_style(self, state: dict):
        window = state["window"]
        if not self._window_exists(window):
            self._forget_window(window)
            return

        desired_dark = self._get_desired_dark_mode(state["fallback_dark"])
        if state["last_dark"] == desired_dark:
            return

        hwnd = self._get_top_level_hwnd(window)
        if not hwnd:
            return

        value = ctypes.c_int(1 if desired_dark else 0)
        for attr in _DWMWA_USE_IMMERSIVE_DARK_MODE:
            try:
                result = ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd,
                    attr,
                    ctypes.byref(value),
                    ctypes.sizeof(value),
                )
            except Exception:
                result = -1
            if result == 0:
                state["last_dark"] = desired_dark
                try:
                    window.update_idletasks()
                except tk.TclError:
                    pass
                return

        if self._apply_caption_colors(hwnd, desired_dark):
            state["last_dark"] = desired_dark
            try:
                window.update_idletasks()
            except tk.TclError:
                pass

    def _get_desired_dark_mode(self, fallback_dark: bool) -> bool:
        system_dark = self._read_system_dark_mode()
        if system_dark is not None:
            return system_dark
        return fallback_dark

    def _apply_caption_colors(self, hwnd: int, dark: bool) -> bool:
        caption = ctypes.c_int(_DARK_CAPTION_COLOR if dark else _LIGHT_CAPTION_COLOR)
        text = ctypes.c_int(_DARK_TEXT_COLOR if dark else _LIGHT_TEXT_COLOR)
        border = ctypes.c_int(_DARK_CAPTION_COLOR if dark else _LIGHT_CAPTION_COLOR)

        caption_ok = self._set_dwm_int_attribute(hwnd, _DWMWA_CAPTION_COLOR, caption)
        text_ok = self._set_dwm_int_attribute(hwnd, _DWMWA_TEXT_COLOR, text)
        border_ok = self._set_dwm_int_attribute(hwnd, _DWMWA_BORDER_COLOR, border)
        return caption_ok or text_ok or border_ok

    def _set_dwm_int_attribute(self, hwnd: int, attr: int, value: ctypes.c_int) -> bool:
        try:
            result = ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd,
                attr,
                ctypes.byref(value),
                ctypes.sizeof(value),
            )
            return result == 0
        except Exception:
            return False

    def _get_top_level_hwnd(self, window: tk.Tk | tk.Toplevel) -> int:
        try:
            hwnd = int(window.winfo_id())
        except (tk.TclError, ValueError, TypeError):
            return 0

        try:
            top_level = ctypes.windll.user32.GetAncestor(hwnd, _GA_ROOT)
        except Exception:
            top_level = 0
        return top_level or hwnd

    def _read_system_dark_mode(self) -> bool | None:
        if not self._system_theme_available():
            return None

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _PERSONALIZE_KEY) as key:
                value, _ = winreg.QueryValueEx(key, _APPS_USE_LIGHT_THEME)
            return value == 0
        except OSError:
            return None

    def _system_theme_available(self) -> bool:
        return self.is_windows and winreg is not None

    @staticmethod
    def _window_exists(window: tk.Tk | tk.Toplevel) -> bool:
        try:
            return bool(window.winfo_exists())
        except tk.TclError:
            return False

    def _forget_window(self, window: tk.Tk | tk.Toplevel):
        self._watched_windows.pop(str(window), None)


window_customizer = WindowCustomizer()
