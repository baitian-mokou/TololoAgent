"""
主题管理器 — 基于 ttkbootstrap 实现 3+1 套主题动态切换与字体缩放
"""
import ttkbootstrap as tb
from ttkbootstrap.constants import *


# 内置主题映射（ttkbootstrap 主题名）
BUILTIN_THEMES = {
    "dark": "darkly",
    "light": "litera",
    "classic": "flatly",
}

# 默认字体族
DEFAULT_FAMILY = "微软雅黑"

# 基础字体大小映射（不同控件的基础字号）
BASE_FONT_SIZES = {
    "title": 16,      # 标题 Label
    "normal": 10,     # 普通 Label、Button、Entry
    "small": 9,       # 状态信息、小字
    "code": 10,       # 等宽字体（日志、代码）
}


class ThemeManager:
    """主题管理器（单例）"""
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self.style: tb.Style = None
        self.current_scale = 1.0
        self.current_theme = "dark"

    def init(self, root: tb.Window):
        """使用 tb.Window 初始化 Style"""
        self.style = tb.Style(theme="darkly")
        self.current_theme = "dark"
        self.current_scale = 1.0

    def apply_theme(self, theme_name: str, tololo_colors: dict = None):
        """应用主题
        
        Args:
            theme_name: "dark" | "light" | "classic" | "tololo"
            tololo_colors: 自定义颜色字典，仅 theme_name="tololo" 时使用
        """
        if self.style is None:
            return

        if theme_name in BUILTIN_THEMES:
            # 内置主题：直接使用 ttkbootstrap 内置主题
            tb_theme = BUILTIN_THEMES[theme_name]
            if self.style.theme.name != tb_theme:
                self.style.theme_use(tb_theme)
            self.current_theme = theme_name
        elif theme_name == "tololo":
            # 自定义主题：以 darkly 为基底，覆盖关键颜色
            colors = tololo_colors or {}
            primary = colors.get("primary", "#6c5ce7")
            bg = colors.get("bg", "#1a1a2e")
            fg = colors.get("fg", "#e0e0e0")
            accent = colors.get("accent", "#00b894")
            secondary_bg = colors.get("secondary_bg", "#16213e")

            # 切换基底主题
            self.style.theme_use("darkly")
            self.current_theme = "tololo"

            # 覆盖全局颜色
            self.style.configure("TButton",
                background=primary,
                foreground="#ffffff",
                bordercolor=primary,
                focuscolor=primary,
                lightcolor=primary,
                darkcolor=primary,
            )
            self.style.map("TButton",
                background=[("active", accent), ("pressed", accent)],
            )

            self.style.configure("TEntry",
                fieldbackground=secondary_bg,
                foreground=fg,
                bordercolor=primary,
            )
            self.style.map("TEntry",
                fieldbackground=[("focus", bg)],
            )

            self.style.configure("TLabel",
                background=bg,
                foreground=fg,
            )

            self.style.configure("TFrame",
                background=bg,
            )

            self.style.configure("TLabelframe",
                background=bg,
                foreground=fg,
                bordercolor=primary,
            )

            self.style.configure("TLabelframe.Label",
                background=bg,
                foreground=fg,
            )

            self.style.configure("TNotebook",
                background=bg,
                bordercolor=primary,
            )
            self.style.configure("TNotebook.Tab",
                background=secondary_bg,
                foreground=fg,
                bordercolor=primary,
            )
            self.style.map("TNotebook.Tab",
                background=[("selected", primary)],
                foreground=[("selected", "#ffffff")],
            )

            self.style.configure("TCombobox",
                fieldbackground=secondary_bg,
                foreground=fg,
                bordercolor=primary,
                arrowcolor=fg,
            )
            self.style.map("TCombobox",
                fieldbackground=[("focus", bg)],
            )

            self.style.configure("TSpinbox",
                fieldbackground=secondary_bg,
                foreground=fg,
                bordercolor=primary,
                arrowcolor=fg,
            )
            self.style.map("TSpinbox",
                fieldbackground=[("focus", bg)],
            )

            self.style.configure("TScale",
                background=bg,
                troughcolor=secondary_bg,
                slidercolor=primary,
            )

            self.style.configure("TCheckbutton",
                background=bg,
                foreground=fg,
            )
            self.style.map("TCheckbutton",
                background=[("active", bg)],
            )

            self.style.configure("Horizontal.TProgressbar",
                background=primary,
                troughcolor=secondary_bg,
                bordercolor=secondary_bg,
            )

            self.style.configure("Vertical.TProgressbar",
                background=primary,
                troughcolor=secondary_bg,
                bordercolor=secondary_bg,
            )

            # StatusBar（ttk.Label relief="sunken"）
            self.style.configure("StatusBar.TLabel",
                background=secondary_bg,
                foreground=fg,
                relief="sunken",
            )

    def apply_font_scale(self, scale: float):
        """应用全局字体缩放
        
        Args:
            scale: 0.8 ~ 1.5
        """
        if self.style is None:
            return

        self.current_scale = scale

        # 计算不同级别的字体大小
        title_size = max(8, int(BASE_FONT_SIZES["title"] * scale))
        normal_size = max(6, int(BASE_FONT_SIZES["normal"] * scale))
        small_size = max(6, int(BASE_FONT_SIZES["small"] * scale))
        code_size = max(6, int(BASE_FONT_SIZES["code"] * scale))

        # 配置各控件字体
        self.style.configure(".", font=(DEFAULT_FAMILY, normal_size))

        # 标题字体
        self.style.configure("Title.TLabel", font=(DEFAULT_FAMILY, title_size, "bold"))
        self.style.configure("Heading.TLabel", font=(DEFAULT_FAMILY, normal_size, "bold"))
        self.style.configure("Small.TLabel", font=(DEFAULT_FAMILY, small_size))

        # 按钮
        self.style.configure("TButton", font=(DEFAULT_FAMILY, normal_size))

        # 输入框
        self.style.configure("TEntry", font=(DEFAULT_FAMILY, normal_size))
        self.style.configure("TCombobox", font=(DEFAULT_FAMILY, normal_size))

        # 标签框标题
        self.style.configure("TLabelframe.Label", font=(DEFAULT_FAMILY, normal_size))

        # 状态标签
        self.style.configure("StatusBar.TLabel", font=(DEFAULT_FAMILY, small_size))

        # 等宽字体区域（日志、代码）
        # 注意：ScrolledText 需要用 font 参数直接指定，无法通过 style 控制

    def get_menu_colors(self) -> dict:
        """获取当前主题的菜单栏配色"""
        theme = self.current_theme
        if theme == "tololo":
            return {"bg": "#1a1a2e", "fg": "#e0e0e0", "active_bg": "#6c5ce7", "active_fg": "#ffffff"}
        elif theme == "dark":
            return {"bg": "#2d2d2d", "fg": "#ffffff", "active_bg": "#375a7f", "active_fg": "#ffffff"}
        elif theme == "light":
            return {"bg": "#f8f9fa", "fg": "#212529", "active_bg": "#e9ecef", "active_fg": "#212529"}
        elif theme == "classic":
            return {"bg": "#f0f0f0", "fg": "#000000", "active_bg": "#d0d0d0", "active_fg": "#000000"}
        return {"bg": "#f0f0f0", "fg": "#000000", "active_bg": "#d0d0d0", "active_fg": "#000000"}

    def apply_menu_theme(self, menu_bar):
        """给 tk.Menu 菜单栏应用当前主题颜色"""
        import tkinter as tk
        colors = self.get_menu_colors()
        menu_bar.config(bg=colors["bg"], fg=colors["fg"],
                        activebackground=colors["active_bg"],
                        activeforeground=colors["active_fg"])
        # 遍历所有子菜单
        for i in range(menu_bar.index("end") + 1 if menu_bar.index("end") is not None else 0):
            try:
                child = menu_bar.winfo_children()[i]
                if isinstance(child, tk.Menu):
                    child.config(bg=colors["bg"], fg=colors["fg"],
                                 activebackground=colors["active_bg"],
                                 activeforeground=colors["active_fg"])
            except (IndexError, AttributeError, TypeError):
                pass

    def get_scaled_font(self, base_size: int) -> tuple:
        """获取缩放后的字体 (family, size)"""
        return (DEFAULT_FAMILY, max(6, int(base_size * self.current_scale)))

    def get_scaled_code_font(self, base_size: int = 10) -> tuple:
        """获取缩放后的等宽字体 (family, size)"""
        return ("Consolas", max(6, int(base_size * self.current_scale)))
