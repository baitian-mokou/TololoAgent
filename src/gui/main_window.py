"""
托洛洛Agent 主窗口 (ttkbootstrap)
"""
import sys
import os
import json
import threading
import webbrowser
import tkinter as tk
from tkinter import scrolledtext, messagebox
from datetime import datetime, timezone
import ttkbootstrap as tb
from ttkbootstrap.constants import *

from src.gui.components.widget_settings import SettingsDialog
from src.gui.console_manager import (
    has_console,
    hide_console,
    is_console_minimized,
    is_console_visible,
    show_console,
    shutdown_console_manager,
)
from src.gui.settings_manager import SettingsManager
from src.gui.i18n import I18nManager
from src.gui.theme_manager import ThemeManager
from src.gui.window_customization import window_customizer, theme_prefers_dark

# 项目根目录常量（替代所有重复的 sys.path.insert 表达式）
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class BaseTab:
    """标签页基类 — 封装所有重复的 _log / ScrolledText / sys.path 逻辑"""
    def __init__(self, parent, main_window):
        self.main = main_window
        self.i18n = I18nManager()
        self.frame = tb.Frame(parent, padding=20)
        self.log_text = None  # 子类需在 _build_ui 中通过 _create_log_text 初始化

    def _log(self, msg):
        """向 log_text 追加消息（子类需先初始化 self.log_text）"""
        self.log_text.config(state="normal")
        self.log_text.insert("end", msg + "\n")
        self.log_text.see("end")
        self.log_text.config(state="disabled")

    def _create_log_text(self, height=25):
        """创建统一风格的 ScrolledText 控件"""
        st = scrolledtext.ScrolledText(
            self.frame, height=height, state="disabled",
            font=("Consolas", 10), bg="#1e1e1e", fg="#d4d4d4",
            wrap="word", relief="sunken", borderwidth=2
        )
        st.pack(fill="both", expand=True)
        return st

    def refresh_texts(self):
        """语言刷新入口，子类可重写"""
        pass

    def _add_path(self):
        """将项目根目录加入 sys.path（避免重复插入）"""
        if PROJECT_ROOT not in sys.path:
            sys.path.insert(0, PROJECT_ROOT)


class MainWindow:
    """主窗口"""
    def __init__(self):
        self.settings = SettingsManager()
        self.data = self.settings.get_all()
        ui = self.data.get("ui", {})
        self.i18n = I18nManager()
        self.i18n.set_language(ui.get("language", "zh_CN"))

        # 使用 ttkbootstrap Window
        self.root = tb.Window(themename="darkly")
        self.root.title(self.i18n.t("window_title"))
        self.root.geometry("1200x800")
        self.root.minsize(900, 600)
        window_customizer.apply_icon(self.root)

        # 初始化主题管理器
        self.theme_mgr = ThemeManager()
        self.theme_mgr.init(self.root)

        # 应用当前设置的主题和字体
        self._apply_settings(ui)

        self._create_menu()

        # ── 外层主标签页（两级结构） ─────────────────
        self.notebook = tb.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=5, pady=5)

        # 第一个主标签页：Agent对话（最常用，独立展示）
        self.agent_tab = AgentTab(self.notebook, self)
        self.notebook.add(self.agent_tab.frame, text=self.i18n.t("tab_agent"))

        # 第二个主标签页：数据工程（整合数据获取+处理+存储相关功能）
        self.data_frame = tb.Frame(self.notebook, padding=5)
        self.notebook.add(self.data_frame, text=self.i18n.t("tab_data_engineering"))

        # 内部嵌套标签页：爬虫 / NLP处理 / 数据库 / 可视化
        self.inner_notebook = tb.Notebook(self.data_frame)
        self.inner_notebook.pack(fill="both", expand=True)

        self.crawl_tab = CrawlTab(self.inner_notebook, self)
        self.nlp_tab = NlpTab(self.inner_notebook, self)
        self.db_tab = DatabaseTab(self.inner_notebook, self)
        self.quality_review_tab = QualityReviewTab(self.inner_notebook, self)
        self.visualize_tab = VisualizeTab(self.inner_notebook, self)

        self.inner_notebook.add(self.crawl_tab.frame, text=self.i18n.t("tab_crawler"))
        self.inner_notebook.add(self.nlp_tab.frame, text=self.i18n.t("tab_nlp"))
        self.inner_notebook.add(self.db_tab.frame, text=self.i18n.t("tab_database"))
        self.inner_notebook.add(self.quality_review_tab.frame, text="质量复查")
        self.inner_notebook.add(self.visualize_tab.frame, text=self.i18n.t("tab_visualize"))

        self.status_var = tk.StringVar(value=self.i18n.t("status_ready"))
        status_bar = tb.Label(self.root, textvariable=self.status_var,
                              relief="sunken", anchor="w", style="StatusBar.TLabel")
        status_bar.pack(side="bottom", fill="x")
        self._console_watch_job = None
        self._schedule_console_state_watch()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _apply_settings(self, ui):
        """应用主题和字体缩放（初始化时）"""
        tololo = self.data.get("tololo_theme", {})
        theme_name = ui.get("theme", "dark")
        self.theme_mgr.apply_theme(theme_name, tololo)
        self.theme_mgr.apply_font_scale(ui.get("font_scale", 1.0))
        self.root.attributes("-topmost", ui.get("always_on_top", False))
        window_customizer.watch_titlebar_theme(self.root, theme_prefers_dark(theme_name))

    def _create_menu(self):
        """用 tb.Frame + tb.Label 模拟菜单栏，完全跟随主题"""
        # 如果已有菜单栏，销毁重建
        if hasattr(self, 'menu_bar_frame'):
            self.menu_bar_frame.destroy()

        self.menu_bar_frame = tb.Frame(self.root)
        # 确保菜单栏始终在 notebook 上方
        if hasattr(self, 'notebook'):
            self.menu_bar_frame.pack(side="top", fill="x", before=self.notebook)
        else:
            self.menu_bar_frame.pack(side="top", fill="x")

        # 存储当前打开的弹出菜单
        self._active_popup = None

        # 获取当前主题的菜单配色，用于 popup 菜单项
        self._menu_colors = self.theme_mgr.get_menu_colors()

        # 菜单项定义： (label_key, items)
        # items = [(label_key, command), ...]  或 None 表示无下拉菜单
        menu_defs = [
            ("menu_file", [
                ("menu_exit", self.root.quit),
            ]),
            ("menu_settings", None),  # 直接命令，无下拉
            ("menu_help", [
                ("menu_about", self._show_about),
            ]),
            ("menu_terminal", None),  # 直接命令，无下拉
        ]

        for defn in menu_defs:
            label_key = defn[0]
            items = defn[1]
            label_text = self.i18n.t(label_key)

            # 每个菜单项作为一个 tb.Label，完全跟随主题配色
            lbl = tb.Label(
                self.menu_bar_frame,
                text=f"  {label_text}  ",
                font=(self.theme_mgr.get_scaled_font(10)),
            )
            lbl.pack(side="left", padx=1, pady=2)

            if items is None:
                # 直接命令：点击即触发
                lbl.bind("<Button-1>", lambda e, lk=label_key: self._on_menu_command(lk))
            else:
                # 有下拉菜单：绑定点击弹出
                lbl.bind("<Button-1>", lambda e, lk=label_key, its=items: self._show_popup(e, lk, its))

    def _on_menu_command(self, label_key):
        """处理直接点击的菜单命令"""
        self._close_popup()
        if label_key == "menu_settings":
            self._open_settings()
        elif label_key == "menu_terminal":
            self._show_terminal()

    def _show_popup(self, event, label_key, items):
        """显示下拉弹出菜单（相对位置，自动避开屏幕边界）"""
        self._close_popup()

        popup = tk.Toplevel(self.root)
        popup.overrideredirect(True)
        popup.attributes("-topmost", True)

        # 弹出面板使用 tb.Frame，完全跟随主题
        frame = tb.Frame(popup)
        frame.pack(fill="both", expand=True)

        # 填充子菜单项
        for item in items:
            if item is None:
                sep_frame = tb.Frame(frame, height=1)
                sep_frame.pack(fill="x", padx=5, pady=2)
                continue

            item_key, command = item
            item_text = self.i18n.t(item_key)

            item_lbl = tb.Label(
                frame,
                text=f"  {item_text}  ",
                font=(self.theme_mgr.get_scaled_font(10)),
                padding=(5, 2),
            )
            item_lbl.pack(fill="x", padx=2, pady=1)

            # ttk.Label 自动跟随主题配色
            item_lbl.bind("<Button-1>", lambda e, cmd=command: self._on_popup_item(cmd))

        # 弹出后立即刷新计算实际尺寸
        self.root.update_idletasks()

        # 获取菜单 label 位置
        widget = event.widget
        x = widget.winfo_rootx()
        y = widget.winfo_rooty() + widget.winfo_height()

        # 获取弹出窗口实际尺寸
        popup.update_idletasks()
        pw = popup.winfo_reqwidth()
        ph = popup.winfo_reqheight()

        # 获取屏幕尺寸
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()

        # 检查底部空间是否足够，不够则向上弹出
        if y + ph > screen_height:
            y = widget.winfo_rooty() - ph

        # 检查右侧空间
        if x + pw > screen_width:
            x = screen_width - pw - 5

        popup.geometry(f"{pw}x{ph}+{x}+{y}")

        self._active_popup = popup

        # 点击外部关闭
        popup.bind("<FocusOut>", lambda e: self._close_popup())

    def _on_popup_item(self, command):
        """点击下拉菜单项"""
        self._close_popup()
        command()

    def _close_popup(self):
        """关闭当前打开的弹出菜单"""
        if self._active_popup:
            try:
                self._active_popup.destroy()
            except tk.TclError:
                pass
            self._active_popup = None

    def _open_settings(self):
        """打开设置面板"""
        SettingsDialog(self.root, on_save_callback=self._on_settings_saved)

    def _show_about(self):
        messagebox.showinfo(self.i18n.t("about_title"), self.i18n.t("about_text"))

    def _show_terminal(self):
        if is_console_visible():
            if not hide_console():
                messagebox.showinfo(
                    self.i18n.t("menu_terminal"),
                    self.i18n.t("terminal_not_available"),
                )
            return

        if not show_console():
            messagebox.showinfo(
                self.i18n.t("menu_terminal"),
                self.i18n.t("terminal_not_available"),
            )

    def _on_close(self):
        if self._console_watch_job is not None:
            try:
                self.root.after_cancel(self._console_watch_job)
            except tk.TclError:
                pass
            self._console_watch_job = None
        shutdown_console_manager()
        self.root.destroy()

    def _schedule_console_state_watch(self):
        if not has_console():
            return

        def monitor():
            self._console_watch_job = None
            try:
                if is_console_minimized():
                    hide_console()
            finally:
                if self.root.winfo_exists():
                    self._console_watch_job = self.root.after(350, self._schedule_console_state_watch)

        self._console_watch_job = self.root.after(350, monitor)

    def _on_settings_saved(self, data):
        """设置保存后的完整回调：刷新当前界面"""
        ui = data.get("ui", {})
        tololo = data.get("tololo_theme", {})

        # 1. 应用主题
        theme_name = ui.get("theme", "dark")
        self.theme_mgr.apply_theme(theme_name, tololo)

        # 2. 应用字体缩放
        self.theme_mgr.apply_font_scale(ui.get("font_scale", 1.0))

        # 3. 窗口置顶
        self.root.attributes("-topmost", ui.get("always_on_top", False))
        window_customizer.watch_titlebar_theme(self.root, theme_prefers_dark(theme_name))

        # 4. 语言切换
        self.i18n.set_language(ui.get("language", "zh_CN"))
        self._update_all_tab_texts()

        # 5. 更新对话区颜色
        if hasattr(self, 'agent_tab'):
            self.agent_tab.cancel_active_request_if_model_changed(data)
            self.agent_tab.chat_text.config(
                bg=ui.get("chat_bg", "#0d1117"),
                fg=ui.get("chat_fg", "#e6edf3")
            )
            self.agent_tab.chat_text.tag_config("user", foreground=ui.get("user_color", "#58a6ff"))
            self.agent_tab.chat_text.tag_config("assistant", foreground=ui.get("ai_color", "#3fb950"))

        # 6. 强制刷新
        self.root.update_idletasks()

    def _update_all_tab_texts(self):
        """刷新所有标签页的文本（语言切换时调用）"""
        self.root.title(self.i18n.t("window_title"))
        self._create_menu()

        self.notebook.tab(0, text=self.i18n.t("tab_agent"))
        self.notebook.tab(1, text=self.i18n.t("tab_data_engineering"))

        self.inner_notebook.tab(0, text=self.i18n.t("tab_crawler"))
        self.inner_notebook.tab(1, text=self.i18n.t("tab_nlp"))
        self.inner_notebook.tab(2, text=self.i18n.t("tab_database"))
        self.inner_notebook.tab(3, text="质量复查")
        self.inner_notebook.tab(4, text=self.i18n.t("tab_visualize"))

        self.crawl_tab.refresh_texts()
        self.nlp_tab.refresh_texts()
        self.db_tab.refresh_texts()
        self.quality_review_tab.refresh_texts()
        self.visualize_tab.refresh_texts()
        self.agent_tab.refresh_texts()

        self.status_var.set(self.i18n.t("status_ready"))

    def run(self):
        self.root.mainloop()


# ───────────────── BaseTab 的四个数据工程子标签页 ────────────────

class CrawlTab(BaseTab):
    """爬虫管理标签页"""
    def __init__(self, parent, main_window):
        super().__init__(parent, main_window)
        self._build_ui()

    def _build_ui(self):
        self.title_label = tb.Label(self.frame, text=self.i18n.t("crawler_title"),
                                  font=("微软雅黑", 16, "bold"), style="Title.TLabel")
        self.title_label.pack(anchor="w", pady=(0, 15))
        btn_frame = tb.Frame(self.frame)
        btn_frame.pack(fill="x", pady=(0, 10))
        self.btn_crawl = tb.Button(btn_frame, text=self.i18n.t("crawler_btn_start"),
                                  command=self._start_crawl)
        self.btn_crawl.pack(side="left", padx=(0, 5))
        self.btn_stop = tb.Button(btn_frame, text=self.i18n.t("crawler_btn_stop"),
                                 command=self._stop, state="disabled")
        self.btn_stop.pack(side="left", padx=5)
        self.progress = tb.Progressbar(self.frame, mode="determinate", value=0)
        self.progress.pack(fill="x", pady=(0, 10))
        self.log_title = tb.Label(self.frame, text=self.i18n.t("crawler_log_title"),
                                font=("微软雅黑", 10, "bold"), style="Heading.TLabel")
        self.log_title.pack(anchor="w")
        self.log_text = self._create_log_text(25)

    def refresh_texts(self):
        self.title_label.config(text=self.i18n.t("crawler_title"))
        self.btn_crawl.config(text=self.i18n.t("crawler_btn_start"))
        self.btn_stop.config(text=self.i18n.t("crawler_btn_stop"))
        self.log_title.config(text=self.i18n.t("crawler_log_title"))

    def _set_buttons(self, running=True):
        self.btn_crawl.config(state="disabled" if running else "normal")
        self.btn_stop.config(state="normal" if running else "disabled")

    def _start_crawl(self):
        self.log_text.config(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.config(state="disabled")
        self._set_buttons(True)
        self.progress["value"] = 0
        self._log(self.i18n.t("crawler_start_log"))
        def worker():
            try:
                self._add_path()
                from src.crawler.spider import TololoCrawler
                crawler = TololoCrawler()
                crawler.set_progress_callback(
                    lambda c, t, m: self.frame.after(0, lambda c=c, t=t, m=m: self._progress_update(c, t, m))
                )
                success, total = crawler.crawl_all()
                self.frame.after(0, lambda success=success, crawler=crawler: self._log(
                    self.i18n.t("crawler_complete", success=success, total=len(crawler.crawled_titles))))
            except Exception as exc:
                self.frame.after(0, lambda err_msg=str(exc): self._log(
                    self.i18n.t("crawler_error", error=err_msg)))
            finally:
                self.frame.after(0, lambda: self._set_buttons(False))
        threading.Thread(target=worker, daemon=True).start()

    def _progress_update(self, current, total, message):
        if total > 0:
            self.progress["maximum"] = total
            self.progress["value"] = current
        self._log(message)

    def _stop(self):
        self._log(self.i18n.t("crawler_stopped"))
        self._set_buttons(False)


class NlpTab(BaseTab):
    """NLP预处理标签页"""
    def __init__(self, parent, main_window):
        super().__init__(parent, main_window)
        self._build_ui()

    def _build_ui(self):
        self.title_label = tb.Label(self.frame, text=self.i18n.t("nlp_title"),
                                  font=("微软雅黑", 16, "bold"), style="Title.TLabel")
        self.title_label.pack(anchor="w", pady=(0, 15))
        self.info_label = tb.Label(self.frame, text=self.i18n.t("nlp_desc"),
                                font=("微软雅黑", 10), foreground="#555")
        self.info_label.pack(anchor="w", pady=(0, 15))
        self.btn_process = tb.Button(self.frame, text=self.i18n.t("nlp_btn_start"),
                                    command=self._start_nlp)
        self.btn_process.pack(anchor="w", pady=(0, 10))
        self.progress = tb.Progressbar(self.frame, mode="determinate", value=0)
        self.progress.pack(fill="x", pady=(0, 10))
        self.log_title = tb.Label(self.frame, text=self.i18n.t("nlp_log_title"),
                                font=("微软雅黑", 10, "bold"), style="Heading.TLabel")
        self.log_title.pack(anchor="w")
        self.log_text = self._create_log_text(25)

    def refresh_texts(self):
        self.title_label.config(text=self.i18n.t("nlp_title"))
        self.info_label.config(text=self.i18n.t("nlp_desc"))
        self.btn_process.config(text=self.i18n.t("nlp_btn_start"))
        self.log_title.config(text=self.i18n.t("nlp_log_title"))

    def _start_nlp(self):
        self.log_text.config(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.config(state="disabled")
        self.btn_process.config(state="disabled")
        self.progress["value"] = 0
        self._log(self.i18n.t("nlp_start_log"))
        def worker():
            try:
                self._add_path()
                from src.nlp.nlp_pipeline import NlpPipeline
                def callback(c, t, m):
                    self.frame.after(0, lambda: self._log(m))
                    if t > 0:
                        self.frame.after(0, lambda: self.progress.configure(maximum=t, value=c))
                pipeline = NlpPipeline(progress_callback=callback)
                t, n = pipeline.process_all()
                self.frame.after(0, lambda: self._log(
                    self.i18n.t("nlp_complete", triples=t, narratives=n)))
                self.frame.after(0, lambda: self._log(self.i18n.t("nlp_next_step")))
                if hasattr(self.main, 'db_tab'):
                    self.frame.after(0, self.main.db_tab._refresh_neo4j)
                    self.frame.after(0, self.main.db_tab._refresh_chroma)
            except Exception as e:
                self.frame.after(0, lambda: self._log(
                    self.i18n.t("nlp_error", error=str(e))))
                import traceback
                self.frame.after(0, lambda: self._log(traceback.format_exc()))
            finally:
                self.frame.after(0, lambda: self.btn_process.config(state="normal"))
        threading.Thread(target=worker, daemon=True).start()


class DatabaseTab(BaseTab):
    """数据库管理标签页"""
    def __init__(self, parent, main_window):
        super().__init__(parent, main_window)
        self._build_ui()

    def _build_ui(self):
        self.title_label = tb.Label(self.frame, text=self.i18n.t("db_title"),
                                  font=("微软雅黑", 16, "bold"), style="Title.TLabel")
        self.title_label.pack(anchor="w", pady=(0, 15))

        # Neo4j
        neo4j_frame = tb.LabelFrame(self.frame, text=self.i18n.t("db_neo4j_frame"))
        neo4j_frame.pack(fill="x", pady=(0, 10))

        btn_neo4j = tb.Frame(neo4j_frame)
        btn_neo4j.pack(fill="x")
        self.btn_import_neo4j = tb.Button(btn_neo4j, text=self.i18n.t("db_btn_import_neo4j"),
                                          command=self._import_neo4j)
        self.btn_import_neo4j.pack(side="left", padx=(0,5))
        self.btn_refresh_neo4j = tb.Button(btn_neo4j, text=self.i18n.t("db_btn_refresh"),
                                           command=self._refresh_neo4j)
        self.btn_refresh_neo4j.pack(side="left", padx=5)
        self.neo4j_status = tb.Label(neo4j_frame, text=self.i18n.t("db_neo4j_waiting"),
                                   font=("Consolas",10), foreground="#555")
        self.neo4j_status.pack(anchor="w", pady=(5,0))

        # Chroma
        chroma_frame = tb.LabelFrame(self.frame, text=self.i18n.t("db_chroma_frame"))
        chroma_frame.pack(fill="x", pady=(0, 10))
        btn_chroma = tb.Frame(chroma_frame)
        btn_chroma.pack(fill="x")
        self.btn_import_chroma = tb.Button(btn_chroma, text=self.i18n.t("db_btn_import_chroma"),
                                           command=self._import_chroma)
        self.btn_import_chroma.pack(side="left", padx=(0,5))
        self.btn_refresh_chroma = tb.Button(btn_chroma, text=self.i18n.t("db_btn_refresh"),
                                            command=self._refresh_chroma)
        self.btn_refresh_chroma.pack(side="left", padx=5)
        self.chroma_status = tb.Label(chroma_frame, text=self.i18n.t("db_chroma_waiting"),
                                    font=("Consolas",10), foreground="#555")
        self.chroma_status.pack(anchor="w", pady=(5,0))

        # Danger zone
        danger_frame = tb.LabelFrame(self.frame, text=self.i18n.t("db_danger_frame"))
        danger_frame.pack(fill="x", pady=(0, 10))
        self.btn_clear_all = tb.Button(
            danger_frame,
            text=self.i18n.t("db_btn_clear_all"),
            command=self._clear_all_databases,
            bootstyle="danger",
        )
        self.btn_clear_all.pack(anchor="w", padx=5, pady=6)

        self.log_title = tb.Label(self.frame, text=self.i18n.t("db_log_title"),
                                font=("微软雅黑", 10, "bold"), style="Heading.TLabel")
        self.log_title.pack(anchor="w")
        self.log_text = self._create_log_text(14)

        self.frame.after(500, self._refresh_neo4j)
        self.frame.after(500, self._refresh_chroma)

    def refresh_texts(self):
        self.title_label.config(text=self.i18n.t("db_title"))
        # LabelFrame 标题
        for child in self.frame.winfo_children():
            if isinstance(child, tb.LabelFrame):
                if "Neo4j" in child.cget("text") or "Neo4j" in str(child.cget("text")):
                    child.config(text=self.i18n.t("db_neo4j_frame"))
                elif "Chroma" in child.cget("text") or "Chroma" in str(child.cget("text")):
                    child.config(text=self.i18n.t("db_chroma_frame"))
                elif child.cget("text") in (
                    self.i18n.t("db_danger_frame"),
                    "危险操作",
                    "Danger Zone",
                ):
                    child.config(text=self.i18n.t("db_danger_frame"))
        self.btn_import_neo4j.config(text=self.i18n.t("db_btn_import_neo4j"))
        self.btn_refresh_neo4j.config(text=self.i18n.t("db_btn_refresh"))
        self.btn_import_chroma.config(text=self.i18n.t("db_btn_import_chroma"))
        self.btn_refresh_chroma.config(text=self.i18n.t("db_btn_refresh"))
        self.btn_clear_all.config(text=self.i18n.t("db_btn_clear_all"))
        self.log_title.config(text=self.i18n.t("db_log_title"))

    @staticmethod
    def _count_json_items(pattern):
        import glob
        import json
        count = 0
        file_count = 0
        for path in glob.glob(pattern):
            file_count += 1
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                count += len(data) if isinstance(data, list) else 0
            except Exception:
                continue
        return file_count, count

    def _refresh_neo4j(self):
        def worker():
            try:
                self._add_path()
                from src.knowledge_graph.neo4j_loader import Neo4jLoader
                loader = Neo4jLoader()
                if loader.driver:
                    s = loader.get_stats()
                    text = self.i18n.t("db_neo4j_connected",
                                       nodes=s['nodes'],
                                       rels=s['rels'],
                                       labels=len(s['labels']))
                    loader.close()
                else:
                    text = self.i18n.t("db_neo4j_failed")
                self.frame.after(0, lambda: self.neo4j_status.config(
                    text=text, foreground="green" if "✅" in text else "red"))
            except Exception as e:
                self.frame.after(0, lambda e=e: self.neo4j_status.config(
                    text=f"❌ {e}", foreground="red"))
        threading.Thread(target=worker, daemon=True).start()

    def _refresh_chroma(self):
        def worker():
            try:
                self._add_path()
                from src.vector_store.chroma_store import ChromaStore
                store = ChromaStore()
                s = store.get_stats()
                text = self.i18n.t("db_chroma_ready", total=s['total'])
                self.frame.after(0, lambda: self.chroma_status.config(text=text, foreground="green"))
            except Exception as e:
                self.frame.after(0, lambda e=e: self.chroma_status.config(
                    text=f"⏳ Chroma: {e}", foreground="orange"))
        threading.Thread(target=worker, daemon=True).start()

    def _import_neo4j(self):
        self._log(f"📥 {self.i18n.t('db_btn_import_neo4j')}")
        def worker():
            try:
                self._add_path()
                from src.knowledge_graph.neo4j_loader import Neo4jLoader
                loader = Neo4jLoader()
                if loader.driver:
                    nodes, rels = loader.load_all_triples()
                    self.frame.after(0, lambda: self._log(
                        self.i18n.t("db_neo4j_imported", nodes=nodes, rels=rels)))
                    loader.close()
                    self._refresh_neo4j()
                else:
                    self.frame.after(0, lambda: self._log("❌ Neo4j " + self.i18n.t("db_neo4j_failed")))
            except Exception as e:
                self.frame.after(0, lambda e=e: self._log(f"❌ Neo4j错误: {e}"))
        threading.Thread(target=worker, daemon=True).start()

    def _import_chroma(self):
        self._log(f"📥 {self.i18n.t('db_btn_import_chroma')}")
        def worker():
            try:
                self._add_path()
                from src.vector_store.chroma_store import ChromaStore
                store = ChromaStore()
                count = store.load_all_narratives(replace_existing=True)
                self.frame.after(0, lambda: self._log(
                    self.i18n.t("db_chroma_imported", count=count)))
                self._refresh_chroma()
            except Exception as e:
                self.frame.after(0, lambda e=e: self._log(f"❌ Chroma错误: {e}"))
        threading.Thread(target=worker, daemon=True).start()

    def _set_db_buttons(self, enabled=True):
        state = "normal" if enabled else "disabled"
        self.btn_import_neo4j.config(state=state)
        self.btn_refresh_neo4j.config(state=state)
        self.btn_import_chroma.config(state=state)
        self.btn_refresh_chroma.config(state=state)
        self.btn_clear_all.config(state=state)

    def _clear_all_databases(self):
        confirmed = messagebox.askyesno(
            self.i18n.t("db_clear_confirm_title"),
            self.i18n.t("db_clear_confirm_msg"),
            icon="warning",
        )
        if not confirmed:
            return

        self._set_db_buttons(False)
        self._log(self.i18n.t("db_clear_start"))

        def worker():
            neo4j_ok = False
            chroma_ok = False
            neo4j_msg = ""
            chroma_msg = ""

            try:
                self._add_path()
                from src.knowledge_graph.neo4j_loader import Neo4jLoader
                loader = Neo4jLoader()
                if loader.driver:
                    loader.clear_database()
                    loader.close()
                    neo4j_ok = True
                    neo4j_msg = self.i18n.t("db_clear_neo4j_done")
                else:
                    neo4j_msg = self.i18n.t("db_clear_neo4j_failed")
            except Exception as e:
                neo4j_msg = self.i18n.t("db_clear_neo4j_error", error=str(e))

            try:
                from src.vector_store.chroma_store import ChromaStore
                store = ChromaStore()
                count = store.clear_database()
                chroma_ok = True
                chroma_msg = self.i18n.t("db_clear_chroma_done", count=count)
            except Exception as e:
                chroma_msg = self.i18n.t("db_clear_chroma_error", error=str(e))

            def finish():
                self._log(neo4j_msg)
                self._log(chroma_msg)
                if neo4j_ok and chroma_ok:
                    self._log(self.i18n.t("db_clear_done"))
                else:
                    self._log(self.i18n.t("db_clear_partial"))
                self._set_db_buttons(True)
                self._refresh_neo4j()
                self._refresh_chroma()

            self.frame.after(0, finish)

        threading.Thread(target=worker, daemon=True).start()


class QualityReviewTab(BaseTab):
    """质量复查标签页：只记录审批并预览合并，不写数据库。"""
    def __init__(self, parent, main_window):
        super().__init__(parent, main_window)
        self.queue_path = os.path.join(PROJECT_ROOT, "data", "quality_review", "quality_review_queue.json")
        self.decisions_path = os.path.join(PROJECT_ROOT, "data", "quality_review", "quality_review_decisions.json")
        self.report_path = os.path.join(PROJECT_ROOT, "evaluation", "quality_review_apply_report.json")
        self.gui_report_path = os.path.join(PROJECT_ROOT, "evaluation", "quality_review_gui_report.json")
        self.items = []
        self.decisions_by_patch = {}
        self._build_ui()
        self._refresh_queue()

    def _build_ui(self):
        self.title_label = tb.Label(
            self.frame,
            text="质量复查 - 有争议数据审批台",
            font=("微软雅黑", 16, "bold"),
            style="Title.TLabel",
        )
        self.title_label.pack(anchor="w", pady=(0, 8))
        self.desc_label = tb.Label(
            self.frame,
            text="这里只审批待复查数据；默认只生成预览，不写 Chroma 或 Neo4j。",
            font=("微软雅黑", 10),
            foreground="#777",
        )
        self.desc_label.pack(anchor="w", pady=(0, 12))

        body = tb.Frame(self.frame)
        body.pack(fill="both", expand=True)

        left = tb.Frame(body)
        left.pack(side="left", fill="both", expand=True, padx=(0, 10))
        right = tb.Frame(body)
        right.pack(side="left", fill="both", expand=True)

        columns = ("subject", "relation", "issue_type", "risk_level", "human_decision")
        self.tree = tb.Treeview(left, columns=columns, show="headings", height=18)
        headings = {
            "subject": "对象",
            "relation": "关系",
            "issue_type": "问题类型",
            "risk_level": "风险",
            "human_decision": "决定",
        }
        widths = {"subject": 110, "relation": 120, "issue_type": 170, "risk_level": 70, "human_decision": 80}
        for column in columns:
            self.tree.heading(column, text=headings[column])
            self.tree.column(column, width=widths[column], anchor="w", stretch=True)
        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar = tb.Scrollbar(left, orient="vertical", command=self.tree.yview)
        scrollbar.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.bind("<<TreeviewSelect>>", lambda _event: self._show_selected_detail())

        self.detail_title = tb.Label(right, text="复查详情", font=("微软雅黑", 12, "bold"))
        self.detail_title.pack(anchor="w", pady=(0, 6))
        self.detail_text = scrolledtext.ScrolledText(
            right,
            height=18,
            state="disabled",
            font=("微软雅黑", 10),
            wrap="word",
            relief="sunken",
            borderwidth=1,
        )
        self.detail_text.pack(fill="both", expand=True)

        decision_buttons = tb.Frame(right)
        decision_buttons.pack(fill="x", pady=(8, 4))
        self.btn_approve = tb.Button(decision_buttons, text="通过", command=lambda: self._set_decision("approved"), bootstyle="success")
        self.btn_defer = tb.Button(decision_buttons, text="暂缓", command=lambda: self._set_decision("deferred"), bootstyle="warning")
        self.btn_reject = tb.Button(decision_buttons, text="拒绝", command=lambda: self._set_decision("rejected"), bootstyle="danger")
        for button in (self.btn_approve, self.btn_defer, self.btn_reject):
            button.pack(side="left", padx=(0, 6))

        tool_buttons = tb.Frame(right)
        tool_buttons.pack(fill="x", pady=(4, 8))
        self.btn_refresh = tb.Button(tool_buttons, text="刷新", command=self._refresh_queue)
        self.btn_build = tb.Button(tool_buttons, text="生成队列", command=self._build_queue)
        self.btn_dry_run = tb.Button(tool_buttons, text="预演合并", command=self._dry_run_apply)
        self.btn_apply = tb.Button(tool_buttons, text="合并低风险标注", command=self._apply_metadata_only, bootstyle="danger")
        self.btn_export = tb.Button(tool_buttons, text="导出复查报告", command=self._export_review_report)
        self.btn_show_report = tb.Button(tool_buttons, text="显示最近 apply report", command=self._show_apply_report)
        for button in (self.btn_refresh, self.btn_build, self.btn_dry_run, self.btn_apply, self.btn_export, self.btn_show_report):
            button.pack(side="left", padx=(0, 6))

        self.log_title = tb.Label(self.frame, text="操作记录", font=("微软雅黑", 10, "bold"), style="Heading.TLabel")
        self.log_title.pack(anchor="w", pady=(8, 0))
        self.log_text = self._create_log_text(7)

    def refresh_texts(self):
        self.title_label.config(text="质量复查 - 有争议数据审批台")
        self.desc_label.config(text="这里只审批待复查数据；默认只生成预览，不写 Chroma 或 Neo4j。")

    def _load_json(self, path, default):
        if not os.path.exists(path):
            return default
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)

    def _dump_json(self, path, payload):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")

    def _refresh_queue(self):
        queue = self._load_json(self.queue_path, {"items": []})
        decisions = self._load_json(self.decisions_path, {"decisions": []})
        self.decisions_by_patch = {
            item.get("patch_id"): item for item in decisions.get("decisions", []) if item.get("patch_id")
        }
        self.items = queue.get("items", [])
        for row in self.tree.get_children():
            self.tree.delete(row)
        for item in self.items:
            decision = self.decisions_by_patch.get(item.get("patch_id"), {})
            human_decision = decision.get("human_decision") or item.get("human_decision", "pending")
            self.tree.insert(
                "",
                "end",
                iid=item.get("review_id"),
                values=(
                    item.get("subject", ""),
                    item.get("relation", ""),
                    self._issue_label(item.get("issue_type", "")),
                    self._risk_label(item.get("risk_level", "")),
                    self._decision_label(human_decision),
                ),
            )
        self._log(f"已加载 {len(self.items)} 条复查记录。")
        if self.items and not self.tree.selection():
            self.tree.selection_set(self.items[0].get("review_id"))
            self._show_selected_detail()

    def _selected_item(self):
        selection = self.tree.selection()
        if not selection:
            return None
        review_id = selection[0]
        for item in self.items:
            if item.get("review_id") == review_id:
                return item
        return None

    def _show_selected_detail(self):
        item = self._selected_item()
        if not item:
            return
        decision = self.decisions_by_patch.get(item.get("patch_id"), {})
        lines = [
            f"对象：{item.get('subject', '')}",
            f"关系：{item.get('relation', '')}",
            f"问题：{self._issue_label(item.get('issue_type', ''))}",
            f"风险：{self._risk_label(item.get('risk_level', ''))}",
            f"当前决定：{self._decision_label(decision.get('human_decision') or item.get('human_decision', 'pending'))}",
            "",
            f"当前值：{self._format_value(item.get('current_value'))}",
            f"候选值：{self._format_value(item.get('proposed_value')) if item.get('proposed_value') else self._format_metadata(item.get('proposed_metadata'))}",
            "",
            f"系统建议：{item.get('system_recommendation', '建议人工复核。')}",
            f"风险说明：{self._risk_explanation(item)}",
            "",
            "来源证据：",
        ]
        lines.extend(self._format_evidence(item.get("source_evidence", {})))
        if decision.get("human_reason"):
            lines.extend(["", f"审批说明：{decision.get('human_reason')}"])
        self.detail_text.config(state="normal")
        self.detail_text.delete("1.0", "end")
        self.detail_text.insert("end", "\n".join(lines))
        self.detail_text.config(state="disabled")

    def _set_decision(self, human_decision):
        item = self._selected_item()
        if not item:
            messagebox.showinfo("质量复查", "请先选择一条复查记录。")
            return
        payload = self._load_json(self.decisions_path, {"schema_version": "quality_review_decisions_v1", "decisions": []})
        decisions = payload.setdefault("decisions", [])
        target = None
        for decision in decisions:
            if decision.get("patch_id") == item.get("patch_id"):
                target = decision
                break
        if target is None:
            target = {"review_id": item.get("review_id"), "patch_id": item.get("patch_id")}
            decisions.append(target)

        now = datetime.now(timezone.utc).isoformat()
        reason_by_decision = {
            "approved": "approved_in_gui",
            "deferred": "deferred_in_gui",
            "rejected": "rejected_in_gui",
        }
        target.update({
            "review_id": item.get("review_id"),
            "patch_id": item.get("patch_id"),
            "subject": item.get("subject"),
            "relation": item.get("relation"),
            "issue_type": item.get("issue_type"),
            "risk_level": item.get("risk_level"),
            "change_type": item.get("change_type"),
            "human_decision": human_decision,
            "human_reason": reason_by_decision[human_decision],
            "approved_action": item.get("action") if human_decision == "approved" else None,
            "safe_to_apply": bool(item.get("safe_to_apply")) if human_decision == "approved" else False,
            "reviewed_by": "gui",
            "reviewed_at": now,
            "updated_at": now,
        })
        self._dump_json(self.decisions_path, payload)
        self._log(f"{item.get('subject')} / {item.get('relation')} 已标记为：{self._decision_label(human_decision)}。")
        self._refresh_queue()
        self.tree.selection_set(item.get("review_id"))
        self._show_selected_detail()

    def _build_queue(self):
        self._run_worker("正在生成质量复查队列...", self._build_queue_worker)

    def _build_queue_worker(self):
        self._add_path()
        from scripts.build_quality_review_queue import build_quality_review_queue
        result = build_quality_review_queue()
        self.frame.after(0, lambda: self._log(f"队列已生成：{result['item_count']} 条，待处理 {result['pending_count']} 条。"))
        self.frame.after(0, self._refresh_queue)

    def _dry_run_apply(self):
        self._run_worker("正在生成 dry-run 合并预览...", lambda: self._apply_worker(False))

    def _apply_metadata_only(self):
        confirmed = messagebox.askyesno(
            "确认合并低风险标注",
            "此操作只写入已通过的 metadata-only 标注，并会先生成备份和 rollback manifest。\n\n高风险 value change 不会写入。继续吗？",
            icon="warning",
        )
        if confirmed:
            self._run_worker("正在合并低风险标注（会先生成备份）...", lambda: self._apply_worker(True))

    def _apply_worker(self, should_apply):
        self._add_path()
        from scripts.apply_quality_patches import apply_quality_patch
        result = apply_quality_patch(apply=should_apply, allow_value_change=False)
        mode = "合并低风险标注" if should_apply else "预演合并"
        self.frame.after(
            0,
            lambda: self._log(
                f"{mode}完成：approved {result.get('approved_count', 0)} 项，实际应用 {result.get('applied_count', 0)} 项；Chroma/Neo4j 未写入。"
            ),
        )
        self.frame.after(0, self._show_apply_report)

    def _export_review_report(self):
        queue = self._load_json(self.queue_path, {"items": [], "summary": {}})
        decisions = self._load_json(self.decisions_path, {"decisions": []})
        decision_by_patch = {item.get("patch_id"): item for item in decisions.get("decisions", []) if item.get("patch_id")}
        rows = []
        for item in queue.get("items", []):
            decision = decision_by_patch.get(item.get("patch_id"), {})
            rows.append({
                "patch_id": item.get("patch_id"),
                "subject": item.get("subject"),
                "relation": item.get("relation"),
                "issue_type": item.get("issue_type"),
                "risk_level": item.get("risk_level"),
                "human_decision": decision.get("human_decision") or item.get("human_decision"),
                "has_external_review": bool(item.get("source_evidence", {}).get("external_review")),
                "system_recommendation": item.get("system_recommendation"),
            })
        payload = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "queue_summary": queue.get("summary", {}),
            "decision_count": len(decisions.get("decisions", [])),
            "items": rows,
        }
        self._dump_json(self.gui_report_path, payload)
        self._log(f"复查报告已导出：{self.gui_report_path}")

    def _show_apply_report(self):
        report = self._load_json(self.report_path, None)
        if not report:
            self._log("还没有 apply report。请先点击“预演合并”。")
            return
        lines = [
            "最近 apply report",
            "",
            f"dry_run：{report.get('dry_run')}",
            f"apply：{report.get('apply')}",
            f"approved_count：{report.get('approved_count', 0)}",
            f"applied_count：{report.get('applied_count', 0)}",
            f"skipped_count：{report.get('skipped_count', 0)}",
            f"formal_values_changed：{report.get('formal_values_changed')}",
            f"backup_dir：{report.get('backup_dir') or '无'}",
            f"rollback_manifest：{(report.get('rollback_manifest') or {}).get('path') or '无'}",
            f"Chroma 写入：{report.get('chroma_written')}",
            f"Neo4j 写入：{report.get('neo4j_written')}",
        ]
        errors = report.get("errors") or []
        if errors:
            lines.extend(["", "错误："])
            lines.extend(f"- {error}" for error in errors)
        self.detail_text.config(state="normal")
        self.detail_text.delete("1.0", "end")
        self.detail_text.insert("end", "\n".join(lines))
        self.detail_text.config(state="disabled")
        self._log("已显示最近 apply report。")

    def _run_worker(self, start_message, target):
        self._log(start_message)
        def worker():
            try:
                target()
            except Exception as exc:
                self.frame.after(0, lambda exc=exc: self._log(f"操作失败：{exc}"))
        threading.Thread(target=worker, daemon=True).start()

    def _issue_label(self, value):
        return {
            "true_value_conflict": "事实值冲突",
            "measurement_kind_mismatch": "测量口径不明",
            "source_granularity_mismatch": "来源精度差异",
            "manual_review": "人工复核",
        }.get(value, value or "待判断")

    def _risk_label(self, value):
        return {"high": "高", "medium": "中", "low": "低"}.get(value, value or "未定")

    def _decision_label(self, value):
        return {"pending": "待审批", "approved": "通过", "rejected": "拒绝", "deferred": "暂缓"}.get(value, value or "待审批")

    def _format_value(self, value):
        if isinstance(value, list):
            return "、".join(str(item) for item in value)
        return str(value or "无")

    def _format_metadata(self, value):
        if not value:
            return "不改事实值；仅补充元数据。"
        labels = []
        if value.get("measurement_kind"):
            labels.append(f"测量口径：{value.get('measurement_kind')}")
        if value.get("quality_status"):
            labels.append(f"质量状态：{value.get('quality_status')}")
        return "；".join(labels) if labels else "仅补充元数据。"

    def _format_evidence(self, evidence):
        values = evidence.get("values_by_source", {})
        lines = []
        for source, source_values in values.items():
            lines.append(f"- {source}: {self._format_value(source_values)}")
        packet = evidence.get("evidence_by_source", {})
        for source, records in packet.items():
            for record in records[:2]:
                raw = record.get("raw_value", "")
                kind = record.get("measurement_kind", "")
                parsed = record.get("parse_status", "")
                title = record.get("source_title", "")
                lines.append(f"- {source} 证据：{title}，原值 {raw}，口径 {kind or '未标注'}，解析 {parsed or '未说明'}")
        if evidence.get("audit_reason"):
            lines.append(f"- 审计说明：{evidence.get('audit_reason')}")
        external = evidence.get("external_review") or {}
        if external:
            lines.append(
                f"- 外部复核：{external.get('recommendation') or external.get('action')}，"
                f"比较结果 {external.get('comparison_result') or '未说明'}，置信度 {external.get('confidence')}"
            )
            external_evidence = external.get("external_evidence") or {}
            if external_evidence:
                value = external_evidence.get("normalized_value") or external_evidence.get("object") or ""
                url = external_evidence.get("source_url") or ""
                license_text = external_evidence.get("source_license") or external_evidence.get("license_hint") or ""
                lines.append(f"- 外部证据：{value or '未给出标准化值'}；来源 {url or '未给出链接'}；许可 {license_text or '未说明'}")
        return lines or ["- 暂无可显示证据。"]

    def _risk_explanation(self, item):
        if item.get("risk_level") == "high":
            return "这类记录可能改变正式事实值，默认只进入计划，不直接写入。"
        if item.get("change_type") == "metadata_only":
            return "仅补充质量/测量口径元数据，不改变正式事实值。"
        return "需要人工判断后再决定是否进入后续处理。"


class VisualizeTab(BaseTab):
    """可视化标签页 — 直接从同一进程启动Flask"""
    def __init__(self, parent, main_window):
        super().__init__(parent, main_window)
        self.flask_thread = None
        self.flask_running = False
        self._build_ui()

    def _build_ui(self):
        self.title_label = tb.Label(self.frame, text=self.i18n.t("vis_title"),
                                  font=("微软雅黑", 16, "bold"), style="Title.TLabel")
        self.title_label.pack(anchor="w", pady=(0, 15))
        self.desc_label = tb.Label(self.frame, text=self.i18n.t("vis_desc"),
                                font=("微软雅黑", 10), foreground="#555")
        self.desc_label.pack(anchor="w", pady=(0, 15))

        btn_frame = tb.Frame(self.frame)
        btn_frame.pack(fill="x")
        self.btn_start = tb.Button(btn_frame, text=self.i18n.t("vis_btn_start"),
                                  command=self._start)
        self.btn_start.pack(side="left", padx=(0, 5))
        self.btn_stop = tb.Button(btn_frame, text=self.i18n.t("vis_btn_stop"),
                                 command=self._stop, state="disabled")
        self.btn_stop.pack(side="left", padx=5)
        self.btn_open = tb.Button(btn_frame, text=self.i18n.t("vis_btn_open"),
                                 command=self._open_browser, state="disabled")
        self.btn_open.pack(side="left", padx=5)

        self.status_label = tb.Label(self.frame, text=self.i18n.t("vis_status_idle"),
                                   font=("Consolas", 10))
        self.status_label.pack(anchor="w", pady=10)

        self.log_title = tb.Label(self.frame, text=self.i18n.t("vis_log_title"),
                                font=("微软雅黑", 10, "bold"), style="Heading.TLabel")
        self.log_title.pack(anchor="w")
        self.log_text = self._create_log_text(20)

    def refresh_texts(self):
        self.title_label.config(text=self.i18n.t("vis_title"))
        self.desc_label.config(text=self.i18n.t("vis_desc"))
        self.btn_start.config(text=self.i18n.t("vis_btn_start"))
        self.btn_stop.config(text=self.i18n.t("vis_btn_stop"))
        self.btn_open.config(text=self.i18n.t("vis_btn_open"))
        self.log_title.config(text=self.i18n.t("vis_log_title"))
        if not self.flask_running:
            self.status_label.config(text=self.i18n.t("vis_status_idle"))

    def _start(self):
        port = self.main.settings.get("advanced", "flask_port", default=5001)
        self._log(self.i18n.t("vis_starting", port=port))
        self.btn_start.config(state="disabled")
        self.flask_running = True

        def run_flask():
            self._add_path()
            from src.visualization.app import app
            from config import FLASK_HOST, FLASK_PORT
            app.run(host=FLASK_HOST, port=FLASK_PORT, debug=False, use_reloader=False)

        self.flask_thread = threading.Thread(target=run_flask, daemon=True)
        self.flask_thread.start()

        self.frame.after(1000, lambda: self._check_started())

    def _check_started(self):
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.connect(('127.0.0.1', 5001))
            s.close()
            self.status_label.config(
                text=self.i18n.t("vis_status_running", port=5001), foreground="green")
            self._log(self.i18n.t("vis_started"))
            self.btn_stop.config(state="normal")
            self.btn_open.config(state="normal")
            self._open_browser()
        except:
            self.frame.after(500, self._check_started)

    def _stop(self):
        self.flask_running = False
        self._log(self.i18n.t("vis_stopped"))
        self.btn_start.config(state="normal")
        self.btn_stop.config(state="disabled")
        self.btn_open.config(state="disabled")
        self.status_label.config(text=self.i18n.t("vis_status_stopped"), foreground="gray")

    def _open_browser(self):
        webbrowser.open('http://127.0.0.1:5001')
        self._log(self.i18n.t("vis_browser_opened", port=5001))


# ───────────────── Agent 对话标签页 ────────────────

class AgentTab(BaseTab):
    """Agent对话标签页 — 知识搜索 + LLM智能问答"""
    def __init__(self, parent, main_window):
        super().__init__(parent, main_window)
        self._assistant_prefix_text = self._assistant_prefix()
        self._ask_in_progress = False
        self._request_epoch = 0
        self._active_llm_signature = None
        self._build_ui()
    def _build_ui(self):
        self.title_label = tb.Label(self.frame, text=self.i18n.t("agent_title"),
                                  font=("微软雅黑", 16, "bold"), style="Title.TLabel")
        self.title_label.pack(anchor="w", pady=(0, 5))

        # ── 状态栏 ──
        status_frame = tb.Frame(self.frame)
        status_frame.pack(fill="x", pady=(0, 8))
        self.ollama_label = tk.Label(status_frame, text=self.i18n.t("agent_ollama_status_checking"),
                                     font=("Consolas", 9), fg="#555", bg="#f0f0f0")
        self.ollama_label.pack(side="left", padx=(0, 15))
        self.model_label = tk.Label(status_frame, text=self.i18n.t("agent_model_status_checking"),
                                    font=("Consolas", 9), fg="#555", bg="#f0f0f0")
        self.model_label.pack(side="left", padx=(0, 10))
        self.btn_refresh_status = tb.Button(status_frame, text=self.i18n.t("agent_refresh_status"),
                                            command=self._refresh_all_status, width=12)
        self.btn_refresh_status.pack(side="left")

        # ── 输入行 ──
        input_row = tb.Frame(self.frame)
        input_row.pack(fill="x", pady=(0, 8))
        tb.Label(input_row, text=self.i18n.t("agent_ask_label"),
                 font=("微软雅黑", 10)).pack(side="left", padx=(0, 5))
        self.query_var = tk.StringVar()
        self.query_entry = tb.Entry(input_row, textvariable=self.query_var,
                                   font=("微软雅黑", 10))
        self.query_entry.pack(side="left", padx=(0, 5), fill="x", expand=True)
        self.query_entry.bind("<Return>", self._on_query_return)
        self.btn_ask = tb.Button(input_row, text=self.i18n.t("agent_ask_button"),
                                command=self._ask_llm)
        self.btn_ask.pack(side="left", padx=2)
        self.btn_toggle = tb.Button(input_row, text=self.i18n.t("agent_toggle_detail"),
                                   command=self._toggle_result)
        self.btn_toggle.pack(side="left", padx=2)
        tb.Button(input_row, text=self.i18n.t("agent_clear_button"),
                  command=self._clear_chat, width=8).pack(side="left", padx=2)

        # ── 内容容器（pack 放入 frame，内部用 grid 实现4:6布局） ──
        self.content_frame = tb.Frame(self.frame)
        self.content_frame.pack(fill="both", expand=True, pady=(5, 0))
        self.content_frame.grid_columnconfigure(0, weight=1)

        # ── 检索结果面板（默认隐藏） ──
        self.result_visible = False
        self.result_frame = tb.LabelFrame(self.content_frame, text=self.i18n.t("agent_search_result_title"))
        # 左右子面板各占50%（grid 精确控制 1:1）
        result_inner = tb.Frame(self.result_frame)
        result_inner.pack(fill="both", expand=True)
        result_inner.grid_columnconfigure(0, weight=1)
        result_inner.grid_columnconfigure(1, weight=1)
        result_inner.grid_rowconfigure(0, weight=1)

        nf = tb.LabelFrame(result_inner, text=self.i18n.t("agent_neo4j_result_title"))
        nf.grid(row=0, column=0, sticky="nsew", padx=(0, 2))
        self.neo4j_result = scrolledtext.ScrolledText(
            nf, state="disabled",
            font=("Consolas", 9), bg="#161b22", fg="#c9d1d9",
            wrap="word", relief="sunken", borderwidth=1)
        self.neo4j_result.pack(fill="both", expand=True)

        cf = tb.LabelFrame(result_inner, text=self.i18n.t("agent_chroma_result_title"))
        cf.grid(row=0, column=1, sticky="nsew", padx=(2, 0))
        self.chroma_result = scrolledtext.ScrolledText(
            cf, state="disabled",
            font=("Consolas", 9), bg="#161b22", fg="#c9d1d9",
            wrap="word", relief="sunken", borderwidth=1)
        self.chroma_result.pack(fill="both", expand=True)

        # ── 对话历史 ──
        self.chat_frame = tb.LabelFrame(self.content_frame, text=self.i18n.t("agent_chat_history"))
        self.chat_text = scrolledtext.ScrolledText(
            self.chat_frame, state="disabled",
            font=("微软雅黑", 10), bg="#0d1117", fg="#e6edf3",
            wrap="word", relief="sunken", borderwidth=1,
            insertbackground="#e6edf3"
        )
        self.chat_text.pack(fill="both", expand=True)
        # 颜色标签
        self.chat_text.tag_config("user", foreground="#58a6ff", font=("微软雅黑", 10, "bold"))
        self.chat_text.tag_config("assistant", foreground="#3fb950", font=("微软雅黑", 10, "bold"))
        self.chat_text.tag_config("info", foreground="#d29922", font=("微软雅黑", 9))
        self.chat_text.tag_config("error", foreground="#f85149", font=("微软雅黑", 9, "bold"))
        self.chat_text.tag_config("token", foreground="#e6edf3")

        # grid 布局：result_frame(row=0, weight=4), chat_frame(row=1, weight=6)
        self.result_frame.grid(row=0, column=0, sticky="nsew", pady=(0, 5))
        self.result_frame.grid_remove()  # 默认隐藏
        self.chat_frame.grid(row=1, column=0, sticky="nsew")
        self.content_frame.grid_rowconfigure(0, weight=4)
        self.content_frame.grid_rowconfigure(1, weight=6)

        # ── 对话历史存储 ──
        self.chat_history = []

        # 延迟检测状态
        self.frame.after(500, self._refresh_all_status)

    def refresh_texts(self):
        self.title_label.config(text=self.i18n.t("agent_title"))
        # LabelFrame 标题
        for child in self.frame.winfo_children():
            if isinstance(child, tb.LabelFrame):
                if "chat" in child.cget("text").lower() or "对话" in child.cget("text"):
                    child.config(text=self.i18n.t("agent_chat_history"))
        if self._ask_in_progress:
            self.btn_ask.config(state="disabled", text=self.i18n.t("agent_ask_thinking"))
        else:
            self.btn_ask.config(state="normal", text=self.i18n.t("agent_ask_button"))
        if hasattr(self, "btn_refresh_status"):
            self.btn_refresh_status.config(text=self.i18n.t("agent_refresh_status"))
        self.btn_toggle.config(text=self.i18n.t("agent_toggle_detail") if not self.result_visible
                               else self.i18n.t("agent_toggle_detail_open"))

    def _toggle_result(self):
        """切换检索详情面板的显示/隐藏（grid 布局，上下4:6，左右各50%）"""
        if self.result_visible:
            # 隐藏结果面板，聊天面板占满
            self.result_frame.grid_remove()
            self.content_frame.grid_rowconfigure(0, weight=0)
            self.content_frame.grid_rowconfigure(1, weight=1)
            self.btn_toggle.config(text=self.i18n.t("agent_toggle_detail"))
            self.result_visible = False
        else:
            # 显示结果面板，4:6 比例
            self.result_frame.grid()
            self.content_frame.grid_rowconfigure(0, weight=4)
            self.content_frame.grid_rowconfigure(1, weight=6)
            self.btn_toggle.config(text=self.i18n.t("agent_toggle_detail_open"))
            self.result_visible = True

    # ─── 状态检测 ──

    def _update_llm_status_labels(self, ollama_ok: bool, model_ok: bool, model: str):
        if ollama_ok:
            self.ollama_label.config(text=self.i18n.t("agent_ollama_status_ok"), fg="green")
        else:
            self.ollama_label.config(text=self.i18n.t("agent_ollama_status_fail"), fg="red")

        if model_ok:
            self.model_label.config(
                text=self.i18n.t("agent_model_status_ok", model=model), fg="green")
        else:
            self.model_label.config(
                text=self.i18n.t("agent_model_status_pending", model=model), fg="orange")

    def _update_remote_status_labels(self, model: str):
        self.ollama_label.config(text=self.i18n.t("agent_remote_status_ok"), fg="green")
        self.model_label.config(
            text=self.i18n.t("agent_remote_model_status_ok", model=model), fg="green")

    def _refresh_all_status(self):
        """检测 Ollama 和模型状态"""
        if hasattr(self, "btn_refresh_status"):
            self.btn_refresh_status.config(state="disabled")
        self.ollama_label.config(text=self.i18n.t("agent_ollama_status_checking"), fg="#555")
        self.model_label.config(text=self.i18n.t("agent_model_status_checking"), fg="#555")

        def worker():
            try:
                self._add_path()
                from src.agent.llm_agent import LLMAgent
                agent = LLMAgent()

                if agent.use_remote_api:
                    self.frame.after(0, lambda: self._update_remote_status_labels(
                        agent.remote_model))
                    return

                ollama_ok = agent.is_ollama_running()
                model_ok = agent.is_model_available() if ollama_ok else False

                self.frame.after(0, lambda: self._update_llm_status_labels(
                    ollama_ok, model_ok, agent.model))
            except Exception:
                self.frame.after(0, lambda: self.ollama_label.config(
                    text=self.i18n.t("agent_ollama_status_error"), fg="red"))
            finally:
                self.frame.after(0, lambda: self.btn_refresh_status.config(state="normal")
                                 if hasattr(self, "btn_refresh_status") else None)
        threading.Thread(target=worker, daemon=True).start()

    # ─── 智能问答 ──

    def _on_query_return(self, event=None):
        self._ask_llm()
        return "break"

    @staticmethod
    def _llm_signature_from_data(data: dict) -> tuple:
        llm_src = data.get("llm_source", {})
        conn = data.get("connect", {})
        remote = bool(llm_src.get("use_remote_api", False))
        if remote:
            api_base = str(llm_src.get("api_base", ""))
            model = (
                llm_src.get("remote_model")
                or ("deepseek-v4-flash" if "deepseek" in api_base.lower() else "")
            )
            return ("remote", api_base.rstrip("/"), str(model or ""))
        return (
            "local",
            str(conn.get("ollama_url", "")).rstrip("/"),
            str(conn.get("ollama_model", "")),
        )

    def _current_llm_signature(self) -> tuple:
        try:
            return self._llm_signature_from_data(self.main.settings.get_all())
        except Exception:
            return ()

    def _is_current_request(self, epoch: int) -> bool:
        return epoch == self._request_epoch

    def _schedule_if_current(self, epoch: int, callback):
        self.frame.after(0, lambda: callback() if self._is_current_request(epoch) else None)

    def cancel_active_request_if_model_changed(self, data: dict):
        if not self._ask_in_progress:
            return
        new_signature = self._llm_signature_from_data(data)
        if self._active_llm_signature == new_signature:
            return

        self._request_epoch += 1
        self._active_llm_signature = None
        self._replace_last_assistant(self.i18n.t("agent_cancelled_model_changed"))
        self._finish_ask()

    def _finish_ask(self):
        self._ask_in_progress = False
        self._active_llm_signature = None
        self.btn_ask.config(state="normal", text=self.i18n.t("agent_ask_button"))
        self.query_entry.config(state="normal")

    def _ask_llm(self):
        if self._ask_in_progress:
            return

        query = self.query_var.get().strip()
        if not query:
            return

        self._ask_in_progress = True
        self._request_epoch += 1
        request_epoch = self._request_epoch
        self._active_llm_signature = self._current_llm_signature()
        self.btn_ask.config(state="disabled", text=self.i18n.t("agent_ask_thinking"))
        self.query_entry.config(state="disabled")

        self._append_chat("user", query)
        self._append_chat("assistant", self.i18n.t("agent_waiting"))

        def worker():
            try:
                self._add_path()
                from src.agent.llm_agent import LLMAgent
                agent = LLMAgent()
                self._schedule_if_current(request_epoch, lambda: self._set_assistant_prefix(agent))

                if agent.use_remote_api:
                    self._schedule_if_current(request_epoch, lambda: self._update_remote_status_labels(
                        agent.remote_model))
                else:
                    ollama_ok = agent.is_ollama_running()
                    if not ollama_ok:
                        self._schedule_if_current(request_epoch, lambda: self._update_llm_status_labels(
                            False, False, agent.model))
                        err = self.i18n.t("agent_ollama_not_running")
                        self._schedule_if_current(request_epoch, lambda: self._replace_last_assistant(err))
                        self._schedule_if_current(request_epoch, lambda: self._append_chat("error", err))
                        return

                    model_ok = agent.is_model_available()
                    self._schedule_if_current(request_epoch, lambda: self._update_llm_status_labels(
                        True, model_ok, agent.model))
                    if not model_ok:
                        err = self.i18n.t("agent_model_not_available", model=agent.model)
                        self._schedule_if_current(request_epoch, lambda: self._replace_last_assistant(err))
                        self._schedule_if_current(request_epoch, lambda: self._append_chat("error", err))
                        return

                neo4j_results = agent.search_neo4j(query)
                chroma_results = agent.search_chroma(query)
                if not self._is_current_request(request_epoch):
                    return

                self._schedule_if_current(request_epoch, lambda: self._show_neo4j_results(neo4j_results))
                self._schedule_if_current(request_epoch, lambda: self._show_chroma_results(chroma_results))

                if neo4j_results or chroma_results:
                    self._schedule_if_current(
                        request_epoch,
                        lambda: self._toggle_result() if not self.result_visible else None,
                    )

                full_response = []
                def on_token(token):
                    full_response.append(token)
                    self._schedule_if_current(request_epoch, lambda token=token: self._append_token(token))

                answer = agent.chat(
                    user_input=query,
                    neo4j_results=neo4j_results,
                    chroma_results=chroma_results,
                    history=self.chat_history,
                    on_token=on_token,
                )
                if not self._is_current_request(request_epoch):
                    return

                self.chat_history.append({"role": "user", "content": query})
                self.chat_history.append({"role": "assistant", "content": answer})
                if len(self.chat_history) > 10:
                    self.chat_history = self.chat_history[-10:]

                self._schedule_if_current(request_epoch, lambda: self._replace_last_assistant(
                    "✅ " + answer if not answer.startswith("[错误]") else answer
                ))

            except Exception as e:
                import traceback
                err = f"❌ 错误: {e}\n{traceback.format_exc()}"
                self._schedule_if_current(request_epoch, lambda: self._replace_last_assistant(err))
                self._schedule_if_current(request_epoch, lambda: self._append_chat("error", err))
            finally:
                self._schedule_if_current(request_epoch, self._finish_ask)

        threading.Thread(target=worker, daemon=True).start()

    def _assistant_prefix(self, agent=None) -> str:
        model = "Qwen3"
        remote = False
        if agent is not None:
            model = str(getattr(agent, "model", "") or model)
            remote = bool(getattr(agent, "use_remote_api", False))
            if remote:
                model = str(getattr(agent, "remote_model", "") or model)
        else:
            try:
                data = self.main.settings.get_all()
                model = str(data.get("connect", {}).get("ollama_model", model) or model)
                llm_src = data.get("llm_source", {})
                remote = bool(llm_src.get("use_remote_api", False))
                if remote:
                    model = str(
                        llm_src.get("remote_model")
                        or ("deepseek-v4-flash" if "deepseek" in str(llm_src.get("api_base", "")).lower() else model)
                    )
            except Exception:
                pass
        if remote:
            suffix = f"{model} / 联网" if self.i18n.current_lang != "en_US" else f"{model} / Online"
        else:
            suffix = model
        name = "托洛洛" if self.i18n.current_lang != "en_US" else "Tololo"
        return f"\n{name}（{suffix}）: "

    def _set_assistant_prefix(self, agent=None):
        self._assistant_prefix_text = self._assistant_prefix(agent)

    def _append_chat(self, role, text):
        self.chat_text.config(state="normal")
        if role == "user":
            self.chat_text.insert("end", self.i18n.t("agent_user_prefix"), "user")
            self.chat_text.insert("end", f"{text}\n", "user")
        elif role == "assistant":
            self.chat_text.insert("end", self._assistant_prefix_text, "assistant")
            self.chat_text.insert("end", f"{text}\n", "assistant")
        elif role == "error":
            self.chat_text.insert("end", f"\n⚠️ {text}\n", "error")
        self.chat_text.see("end")
        self.chat_text.config(state="disabled")
    def _append_token(self, token):
        self.chat_text.config(state="normal")
        self.chat_text.insert("end", token, "token")
        self.chat_text.see("end")
        self.chat_text.config(state="disabled")

    def _replace_last_assistant(self, text):
        self.chat_text.config(state="normal")
        content = self.chat_text.get("1.0", "end-1c")
        stems = ["\n🤖 Qwen3: ", "\n🤖 AI: ", "\n🪐 托洛洛", "\n🪐 Tololo", "\n托洛洛", "\nTololo"]
        last_idx = -1
        for stem in stems:
            idx = content.rfind(stem)
            if idx > last_idx:
                last_idx = idx
        if last_idx != -1:
            self.chat_text.delete(f"1.0 + {last_idx} chars", "end-1c")
        self.chat_text.insert("end", self._assistant_prefix_text, "assistant")
        self.chat_text.insert("end", f"{text}\n", "assistant")
        self.chat_text.see("end")
        self.chat_text.config(state="disabled")
    def _clear_chat(self):
        self.chat_text.config(state="normal")
        self.chat_text.delete("1.0", "end")
        self.chat_text.config(state="disabled")
        self.chat_history = []
        self.neo4j_result.config(state="normal")
        self.neo4j_result.delete("1.0", "end")
        self.neo4j_result.config(state="disabled")
        self.chroma_result.config(state="normal")
        self.chroma_result.delete("1.0", "end")
        self.chroma_result.config(state="disabled")
        self._append_chat("assistant", self.i18n.t("agent_cleared"))

    def _append_text(self, widget, text):
        widget.config(state="normal")
        widget.insert("end", text + "\n")
        widget.see("end")
        widget.config(state="disabled")

    def _show_neo4j_results(self, records):
        self.neo4j_result.config(state="normal")
        self.neo4j_result.delete("1.0", "end")
        if not records:
            self.neo4j_result.insert("end", self.i18n.t("agent_no_neo4j_result"))
        else:
            self.neo4j_result.insert("end",
                self.i18n.t("agent_neo4j_found", count=len(records)) + "\n")
            for r in records:
                self.neo4j_result.insert("end",
                    f"  ({r['subject']}) -[{r['relation']}]-> ({r['object']})\n")
        self.neo4j_result.config(state="disabled")

    def _show_chroma_results(self, results):
        self.chroma_result.config(state="normal")
        self.chroma_result.delete("1.0", "end")
        if not results:
            self.chroma_result.insert("end", self.i18n.t("agent_no_chroma_result"))
        else:
            self.chroma_result.insert("end",
                self.i18n.t("agent_chroma_found", count=len(results)) + "\n")
            for r in results:
                self.chroma_result.insert("end",
                    f"  [{r.get('rank', '?')}] {r.get('page_title', '未知')} "
                    f"(相关度: {r.get('score', 0):.2f})\n"
                    f"      {r.get('content', '')[:80]}...\n")
        self.chroma_result.config(state="disabled")


def run_gui():
    app = MainWindow()
    app.root.after(800, hide_console)
    app.run()
