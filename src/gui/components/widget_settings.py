"""
设置对话框 — 4个标签页：界面/连接/Agent提示词/高级
添加 tololo 自定义主题面板 + 完整 i18n 翻译
"""
import sys
import os
import threading
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog, colorchooser

# 确保项目根目录在 sys.path 中
_project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)
from src.gui.settings_manager import SettingsManager
from src.gui.i18n import I18nManager
from src.gui.window_customization import window_customizer, theme_prefers_dark


class SettingsDialog:
    """设置对话框"""

    def __init__(self, parent, on_save_callback=None):
        self.parent = parent
        self.on_save_callback = on_save_callback
        self.settings = SettingsManager()
        self.data = self.settings.get_all()
        self.i18n = I18nManager()

        self.dialog = tk.Toplevel(parent)
        self.dialog.withdraw()
        self.dialog.title(self.i18n.t("settings_title"))
        self.dialog.geometry("820x860")
        self.dialog.minsize(760, 720)
        self.dialog.transient(parent)
        window_customizer.apply_icon(self.dialog)
        window_customizer.watch_titlebar_theme(
            self.dialog,
            theme_prefers_dark(self.data.get("ui", {}).get("theme", "dark")),
        )

        # 主 Notebook
        self.notebook = ttk.Notebook(self.dialog, padding=(5, 5, 5, 5))
        self.notebook.pack(side="top", fill="both", expand=True)
        self._button_bar = None

        self._build_ui_tab()
        self._build_connect_tab()
        self._build_agent_tab()
        self._build_advanced_tab()

        # 先在隐藏状态下完成布局和定位，避免从左上角闪现再瞬移
        self.dialog.update_idletasks()
        self._center_dialog()
        self.dialog.deiconify()
        self.dialog.lift()
        self.dialog.grab_set()
        self.dialog.focus_force()

    def _center_dialog(self):
        self.dialog.update_idletasks()
        pw = self.parent.winfo_width()
        ph = self.parent.winfo_height()
        px = self.parent.winfo_x()
        py = self.parent.winfo_y()
        dw = self.dialog.winfo_width()
        dh = self.dialog.winfo_height()
        x = px + (pw - dw) // 2
        y = py + (ph - dh) // 2
        self.dialog.geometry(f"+{x}+{y}")

    # ─── UI 标签页 ─────────────────────────────────────

    def _build_ui_tab(self):
        frame = ttk.Frame(self.notebook, padding=15)
        self.notebook.add(frame, text=self.i18n.t("settings_tab_ui"))

        # ── 主题与语言 ──
        theme_frame = ttk.LabelFrame(frame, text=self.i18n.t("settings_theme_frame"))
        theme_frame.pack(fill="x", pady=(0, 10))

        row1 = ttk.Frame(theme_frame)
        row1.pack(fill="x", pady=3)
        ttk.Label(row1, text=self.i18n.t("settings_theme_label"), width=14).pack(side="left")
        self.theme_var = tk.StringVar(value=self.data.get("ui", {}).get("theme", "dark"))
        theme_combo = ttk.Combobox(
            row1, textvariable=self.theme_var,
            values=["dark", "light", "classic", "tololo"],
            state="readonly", width=20
        )
        theme_combo.pack(side="left")
        self.theme_var.trace_add("write", self._on_theme_changed)

        row2 = ttk.Frame(theme_frame)
        row2.pack(fill="x", pady=3)
        ttk.Label(row2, text=self.i18n.t("settings_lang_label"), width=14).pack(side="left")
        self.lang_var = tk.StringVar(value=self.data.get("ui", {}).get("language", "zh_CN"))
        ttk.Combobox(row2, textvariable=self.lang_var, values=["zh_CN", "en_US"], state="readonly", width=20).pack(side="left")

        row3 = ttk.Frame(theme_frame)
        row3.pack(fill="x", pady=3)
        ttk.Label(row3, text=self.i18n.t("settings_font_scale_label"), width=14).pack(side="left")
        self.font_scale_var = tk.DoubleVar(value=self.data.get("ui", {}).get("font_scale", 1.0))
        scale = ttk.Scale(row3, from_=0.8, to=1.5, variable=self.font_scale_var, orient="horizontal", length=150)
        scale.pack(side="left", padx=5)
        self.font_scale_label = ttk.Label(row3, text=f"{self.font_scale_var.get():.1f}x", width=6)
        self.font_scale_label.pack(side="left")
        scale.config(command=lambda v: self.font_scale_label.config(text=f"{float(v):.1f}x"))

        # ── 托洛洛自定义主题面板（默认隐藏） ──
        self.tololo_frame = ttk.LabelFrame(frame, text=self.i18n.t("settings_tololo_frame"))
        # 不在 init 时 pack，由 _on_theme_changed 控制

        # 5个颜色输入框
        tololo = self.data.get("tololo_theme", {})
        tololo_fields = [
            ("settings_tololo_primary", "primary", tololo.get("primary", "#6c5ce7")),
            ("settings_tololo_bg", "bg", tololo.get("bg", "#1a1a2e")),
            ("settings_tololo_fg", "fg", tololo.get("fg", "#e0e0e0")),
            ("settings_tololo_accent", "accent", tololo.get("accent", "#00b894")),
            ("settings_tololo_secondary_bg", "secondary_bg", tololo.get("secondary_bg", "#16213e")),
        ]
        self.tololo_color_vars = {}
        self.tololo_color_previews = {}

        for label_key, key, default in tololo_fields:
            row = ttk.Frame(self.tololo_frame)
            row.pack(fill="x", pady=2, padx=10)
            ttk.Label(row, text=self.i18n.t(label_key), width=14).pack(side="left")

            var = tk.StringVar(value=default)
            self.tololo_color_vars[key] = var

            entry = ttk.Entry(row, textvariable=var, width=20)
            entry.pack(side="left", padx=2)

            # 取色按钮
            def make_pick_cb(v):
                return lambda: self._pick_color(v)
            ttk.Button(row, text=self.i18n.t("settings_tololo_pick"), width=3,
                       command=make_pick_cb(var)).pack(side="left", padx=1)

            # 预览方块
            preview = tk.Label(row, text="  ■  ", fg=var.get(), font=("Consolas", 14))
            preview.pack(side="left", padx=2)
            self.tololo_color_previews[key] = preview
            var.trace_add("write", lambda *a, p=preview, v=var: p.config(fg=v.get()))

        # 根据当前主题决定是否显示 tololo 面板
        if self.theme_var.get() == "tololo":
            self.tololo_frame.pack(fill="x", pady=(0, 10))

        # ── 对话区颜色 ──
        color_frame = ttk.LabelFrame(frame, text=self.i18n.t("settings_color_frame"))
        color_frame.pack(fill="x", pady=(0, 10))

        ui = self.data.get("ui", {})
        colors = [
            ("settings_color_bg", "chat_bg", ui.get("chat_bg", "#0d1117")),
            ("settings_color_fg", "chat_fg", ui.get("chat_fg", "#e6edf3")),
            ("settings_color_user", "user_color", ui.get("user_color", "#58a6ff")),
            ("settings_color_ai", "ai_color", ui.get("ai_color", "#3fb950")),
        ]
        self.color_vars = {}
        for label_key, key, default in colors:
            row = ttk.Frame(color_frame)
            row.pack(fill="x", pady=2)
            ttk.Label(row, text=self.i18n.t(label_key), width=14).pack(side="left")
            var = tk.StringVar(value=self.data.get("ui", {}).get(key, default))
            self.color_vars[key] = var
            entry = ttk.Entry(row, textvariable=var, width=20)
            entry.pack(side="left", padx=2)
            # 颜色预览小方块
            preview = tk.Label(row, text="  ■  ", fg=var.get(), font=("Consolas", 14))
            preview.pack(side="left", padx=2)
            var.trace_add("write", lambda *a, p=preview, v=var: p.config(fg=v.get()))
            # 取色按钮
            def make_color_pick_cb(v):
                return lambda: self._pick_color(v)
            ttk.Button(row, text=self.i18n.t("settings_tololo_pick"), width=3,
                       command=make_color_pick_cb(var)).pack(side="left", padx=1)

        # ── 其他选项 ──
        opt_frame = ttk.LabelFrame(frame, text=self.i18n.t("settings_opt_frame"))
        opt_frame.pack(fill="x")
        self.always_top_var = tk.BooleanVar(value=self.data.get("ui", {}).get("always_on_top", False))
        ttk.Checkbutton(opt_frame, text=self.i18n.t("settings_always_top"), variable=self.always_top_var).pack(anchor="w")
        self.min_tray_var = tk.BooleanVar(value=self.data.get("ui", {}).get("minimize_to_tray", False))
        ttk.Checkbutton(opt_frame, text=self.i18n.t("settings_min_tray"), variable=self.min_tray_var).pack(anchor="w")

        self._add_tab_buttons(frame, "ui")

    def _on_theme_changed(self, *args):
        """主题选择变化时，显示/隐藏 tololo 自定义面板"""
        window_customizer.watch_titlebar_theme(
            self.dialog,
            theme_prefers_dark(self.theme_var.get()),
        )
        if self.theme_var.get() == "tololo":
            self.tololo_frame.pack(fill="x", pady=(0, 10), after=self._get_theme_frame())
        else:
            self.tololo_frame.pack_forget()

    def _get_theme_frame(self):
        """获取 UI 标签页中第一个 LabelFrame 的引用，用于插入顺序"""
        for child in self.notebook.winfo_children():
            if isinstance(child, ttk.Frame):
                for sub in child.winfo_children():
                    return child
        return None

    def _pick_color(self, var):
        """打开取色器"""
        color = colorchooser.askcolor(title=self.i18n.t("settings_tololo_pick"), color=var.get())
        if color and color[1]:
            var.set(color[1])

    # ─── 连接标签页 ───────────────────────────────────

    def _build_connect_tab(self):
        frame = ttk.Frame(self.notebook, padding=15)
        self.notebook.add(frame, text=self.i18n.t("settings_tab_connect"))

        conn = self.data.get("connect", {})

        # Neo4j
        neo4j_frame = ttk.LabelFrame(frame, text=self.i18n.t("settings_neo4j_frame"))
        neo4j_frame.pack(fill="x", pady=(0, 10))

        fields = [
            (self.i18n.t("settings_neo4j_uri"), "neo4j_uri", conn.get("neo4j_uri", "bolt://127.0.0.1:7687")),
            (self.i18n.t("settings_neo4j_user"), "neo4j_user", conn.get("neo4j_user", "neo4j")),
        ]
        self.connect_entries = {}
        for i, (label, key, default) in enumerate(fields):
            row = ttk.Frame(neo4j_frame)
            row.pack(fill="x", pady=2)
            ttk.Label(row, text=label, width=12).pack(side="left")
            var = tk.StringVar(value=default)
            self.connect_entries[key] = var
            ttk.Entry(row, textvariable=var, width=40).pack(side="left", fill="x", expand=True, padx=2)

        # 密码单独（用 show="*"）
        row_pwd = ttk.Frame(neo4j_frame)
        row_pwd.pack(fill="x", pady=2)
        ttk.Label(row_pwd, text=self.i18n.t("settings_neo4j_pwd"), width=12).pack(side="left")
        self.neo4j_pwd_var = tk.StringVar(value=conn.get("neo4j_password", "12345678"))
        self.neo4j_pwd_entry = ttk.Entry(row_pwd, textvariable=self.neo4j_pwd_var, width=40, show="*")
        self.neo4j_pwd_entry.pack(side="left", fill="x", expand=True, padx=2)
        self.neo4j_pwd_show = True
        ttk.Button(row_pwd, text="👁", width=3, command=self._toggle_neo4j_pwd).pack(side="left", padx=2)
        ttk.Button(row_pwd, text=self.i18n.t("settings_neo4j_test"), command=self._test_neo4j).pack(side="left", padx=(5, 0))

        # Ollama
        ollama_frame = ttk.LabelFrame(frame, text=self.i18n.t("settings_ollama_frame"))
        ollama_frame.pack(fill="x", pady=(0, 10))

        fields2 = [
            (self.i18n.t("settings_ollama_url"), "ollama_url", conn.get("ollama_url", "http://localhost:11434")),
            (self.i18n.t("settings_ollama_model"), "ollama_model", conn.get("ollama_model", "qwen3:4b")),
            (self.i18n.t("settings_ollama_timeout"), "ollama_timeout", str(conn.get("ollama_timeout", 60))),
        ]
        for i, (label, key, default) in enumerate(fields2):
            row = ttk.Frame(ollama_frame)
            row.pack(fill="x", pady=2)
            ttk.Label(row, text=label, width=12).pack(side="left")
            var = tk.StringVar(value=default)
            self.connect_entries[key] = var
            ttk.Entry(row, textvariable=var, width=40).pack(side="left", fill="x", expand=True, padx=2)

        # 刷新模型列表 + 测试按钮
        row_btn = ttk.Frame(ollama_frame)
        row_btn.pack(fill="x", pady=5)
        ttk.Button(row_btn, text=self.i18n.t("settings_ollama_refresh"), command=self._refresh_models).pack(side="left", padx=2)
        ttk.Button(row_btn, text=self.i18n.t("settings_ollama_test"), command=self._test_ollama).pack(side="left", padx=2)
        self.ollama_status = ttk.Label(row_btn, text="", foreground="gray")
        self.ollama_status.pack(side="left", padx=5)

        # Chroma
        chroma_frame = ttk.LabelFrame(frame, text=self.i18n.t("settings_chroma_frame"))
        chroma_frame.pack(fill="x")
        row_c = ttk.Frame(chroma_frame)
        row_c.pack(fill="x")
        ttk.Label(row_c, text=self.i18n.t("settings_chroma_path"), width=12).pack(side="left")
        self.chroma_path_var = tk.StringVar(value=conn.get("chroma_path", ""))
        ttk.Entry(row_c, textvariable=self.chroma_path_var, width=40).pack(side="left", fill="x", expand=True, padx=2)
        ttk.Button(row_c, text=self.i18n.t("settings_chroma_browse"), command=self._browse_chroma_path).pack(side="left", padx=2)

        self._add_tab_buttons(frame, "connect")

    def _toggle_neo4j_pwd(self):
        self.neo4j_pwd_show = not self.neo4j_pwd_show
        self.neo4j_pwd_entry.config(show="" if self.neo4j_pwd_show else "*")

    def _test_neo4j(self):
        def worker():
            try:
                from neo4j import GraphDatabase
                uri = self.connect_entries["neo4j_uri"].get()
                user = self.connect_entries["neo4j_user"].get()
                pwd = self.neo4j_pwd_var.get()
                driver = GraphDatabase.driver(uri, auth=(user, pwd))
                with driver.session() as session:
                    session.run("RETURN 1")
                driver.close()
                self.dialog.after(0, lambda: messagebox.showinfo(
                    self.i18n.t("settings_neo4j_frame"),
                    self.i18n.t("settings_neo4j_success")))
            except Exception as e:
                self.dialog.after(0, lambda: messagebox.showerror(
                    self.i18n.t("settings_neo4j_frame"),
                    self.i18n.t("settings_neo4j_fail", error=str(e))))
        threading.Thread(target=worker, daemon=True).start()

    def _test_ollama(self):
        url = self.connect_entries["ollama_url"].get().rstrip('/')
        def worker():
            try:
                import urllib.request, json
                req = urllib.request.Request(f"{url}/api/tags")
                with urllib.request.urlopen(req, timeout=5) as resp:
                    self.dialog.after(0, lambda: self.ollama_status.config(
                        text=self.i18n.t("settings_ollama_ok"), foreground="green"))
            except Exception as e:
                self.dialog.after(0, lambda: self.ollama_status.config(
                    text=f"❌ {e}", foreground="red"))
        threading.Thread(target=worker, daemon=True).start()

    def _refresh_models(self):
        url = self.connect_entries["ollama_url"].get().rstrip('/')
        def worker():
            try:
                import urllib.request, json
                req = urllib.request.Request(f"{url}/api/tags")
                with urllib.request.urlopen(req, timeout=5) as resp:
                    data = json.loads(resp.read().decode())
                    models = [m["name"] for m in data.get("models", [])]
                    if models:
                        self.dialog.after(0, lambda: self.connect_entries["ollama_model"].set(models[0]))
                        self.dialog.after(0, lambda: self.ollama_status.config(
                            text=self.i18n.t("settings_ollama_models_found", count=len(models)),
                            foreground="green"))
                    else:
                        self.dialog.after(0, lambda: self.ollama_status.config(
                            text=self.i18n.t("settings_ollama_no_models"),
                            foreground="orange"))
            except Exception as e:
                self.dialog.after(0, lambda: self.ollama_status.config(
                    text=f"❌ {e}", foreground="red"))
        threading.Thread(target=worker, daemon=True).start()

    def _browse_chroma_path(self):
        path = filedialog.askdirectory(title=self.i18n.t("settings_chroma_frame"))
        if path:
            self.chroma_path_var.set(path)

    # ─── Agent 标签页 ──────────────────────────────────

    def _build_agent_tab(self):
        frame = ttk.Frame(self.notebook, padding=15)
        self.notebook.add(frame, text=self.i18n.t("settings_tab_agent"))

        agent = self.data.get("agent", {})
        llm_src = self.data.get("llm_source", {})

        # ── LLM来源 ──
        src_frame = ttk.LabelFrame(frame, text=self.i18n.t("settings_llm_source_frame"))
        src_frame.pack(fill="x", pady=(0, 10))

        row_switch = ttk.Frame(src_frame)
        row_switch.pack(fill="x", pady=2)
        self.use_remote_var = tk.BooleanVar(value=llm_src.get("use_remote_api", False))
        ttk.Checkbutton(row_switch, text=self.i18n.t("settings_use_remote"),
                        variable=self.use_remote_var, command=self._toggle_remote_api).pack(side="left")

        row_api = ttk.Frame(src_frame)
        row_api.pack(fill="x", pady=2)
        ttk.Label(row_api, text=self.i18n.t("settings_api_base"), width=12).pack(side="left")
        self.api_base_var = tk.StringVar(value=llm_src.get("api_base", "https://api.openai.com/v1"))
        self.api_base_entry = ttk.Entry(row_api, textvariable=self.api_base_var, width=50)
        self.api_base_entry.pack(side="left", fill="x", expand=True, padx=2)

        row_model = ttk.Frame(src_frame)
        row_model.pack(fill="x", pady=2)
        ttk.Label(row_model, text=self.i18n.t("settings_api_model"), width=12).pack(side="left")
        api_base = self.api_base_var.get()
        remote_model = llm_src.get("remote_model") or (
            "deepseek-v4-flash" if "deepseek" in str(api_base).lower() else "deepseek-v4-flash"
        )
        self.remote_model_var = tk.StringVar(value=remote_model)
        self.remote_model_combo = ttk.Combobox(
            row_model,
            textvariable=self.remote_model_var,
            values=("deepseek-v4-flash", "deepseek-v4-pro"),
            width=47,
        )
        self.remote_model_combo.pack(side="left", fill="x", expand=True, padx=2)

        row_key = ttk.Frame(src_frame)
        row_key.pack(fill="x", pady=2)
        ttk.Label(row_key, text=self.i18n.t("settings_api_key"), width=12).pack(side="left")
        self.api_key_var = tk.StringVar(value=llm_src.get("api_key", ""))
        self.api_key_entry = ttk.Entry(row_key, textvariable=self.api_key_var, width=50, show="*")
        self.api_key_entry.pack(side="left", fill="x", expand=True, padx=2)
        self.api_key_show = True
        ttk.Button(row_key, text="👁", width=3, command=self._toggle_api_key).pack(side="left")

        # 初始化灰色状态
        self._toggle_remote_api()

        # ── 推理参数 ──
        param_frame = ttk.LabelFrame(frame, text=self.i18n.t("settings_param_frame"))
        param_frame.pack(fill="x", pady=(0, 10))

        row_t = ttk.Frame(param_frame)
        row_t.pack(fill="x", pady=2)
        ttk.Label(row_t, text=self.i18n.t("settings_temperature"), width=16).pack(side="left")
        self.temp_var = tk.DoubleVar(value=agent.get("temperature", 0.7))
        temp_scale = ttk.Scale(row_t, from_=0.0, to=2.0, variable=self.temp_var,
                               orient="horizontal", length=200)
        temp_scale.pack(side="left", padx=5)
        self.temp_label = ttk.Label(row_t, text=f"{self.temp_var.get():.1f}", width=6)
        self.temp_label.pack(side="left")
        temp_scale.config(command=lambda v: self.temp_label.config(text=f"{float(v):.1f}"))
        ttk.Label(row_t, text=self.i18n.t("settings_temp_hint"),
                  font=("微软雅黑", 8), foreground="#888").pack(side="left", padx=5)

        row_p = ttk.Frame(param_frame)
        row_p.pack(fill="x", pady=2)
        ttk.Label(row_p, text=self.i18n.t("settings_top_p"), width=16).pack(side="left")
        self.topp_var = tk.DoubleVar(value=agent.get("top_p", 0.9))
        topp_scale = ttk.Scale(row_p, from_=0.0, to=1.0, variable=self.topp_var,
                               orient="horizontal", length=200)
        topp_scale.pack(side="left", padx=5)
        self.topp_label = ttk.Label(row_p, text=f"{self.topp_var.get():.2f}", width=6)
        self.topp_label.pack(side="left")
        topp_scale.config(command=lambda v: self.topp_label.config(text=f"{float(v):.2f}"))

        row_m = ttk.Frame(param_frame)
        row_m.pack(fill="x", pady=2)
        ttk.Label(row_m, text=self.i18n.t("settings_max_tokens"), width=16).pack(side="left")
        self.max_tokens_var = tk.IntVar(value=agent.get("max_tokens", 2048))
        ttk.Spinbox(row_m, from_=128, to=8192, increment=128,
                    textvariable=self.max_tokens_var, width=10).pack(side="left", padx=5)
        ttk.Label(row_m, text=self.i18n.t("settings_tokens_unit")).pack(side="left")

        # ── 系统提示词 ──
        prompt_frame = ttk.LabelFrame(frame, text=self.i18n.t("settings_system_prompt_frame"))
        prompt_frame.pack(fill="both", expand=True)

        ttk.Label(prompt_frame, text=self.i18n.t("settings_system_role"),
                  font=("微软雅黑", 9, "bold")).pack(anchor="w")
        self.system_role_text = scrolledtext.ScrolledText(
            prompt_frame, height=4, font=("Consolas", 9), wrap="word")
        self.system_role_text.pack(fill="x", pady=(2, 8))
        self.system_role_text.insert("1.0", agent.get("system_role", ""))
        self.system_role_text.config(state="normal")

        ttk.Label(prompt_frame, text=self.i18n.t("settings_retrieval_instruction"),
                  font=("微软雅黑", 9, "bold")).pack(anchor="w")
        self.retrieval_text = scrolledtext.ScrolledText(
            prompt_frame, height=3, font=("Consolas", 9), wrap="word")
        self.retrieval_text.pack(fill="x", pady=(2, 8))
        self.retrieval_text.insert("1.0", agent.get("retrieval_instruction", ""))

        ttk.Label(prompt_frame, text=self.i18n.t("settings_fallback"),
                  font=("微软雅黑", 9, "bold")).pack(anchor="w")
        self.fallback_text = scrolledtext.ScrolledText(
            prompt_frame, height=2, font=("Consolas", 9), wrap="word")
        self.fallback_text.pack(fill="x", pady=(2, 0))
        self.fallback_text.insert("1.0", agent.get("fallback_response", ""))

        self._add_tab_buttons(frame, "agent")

    def _toggle_remote_api(self):
        """切换远程API时启用/禁用地址和密钥输入框"""
        state = "normal" if self.use_remote_var.get() else "disabled"
        self.api_base_entry.config(state=state)
        self.remote_model_combo.config(state=state)
        self.api_key_entry.config(state=state)

    def _toggle_api_key(self):
        self.api_key_show = not self.api_key_show
        self.api_key_entry.config(show="" if self.api_key_show else "*")

    # ─── 高级标签页 ───────────────────────────────────

    def _build_advanced_tab(self):
        frame = ttk.Frame(self.notebook, padding=15)
        self.notebook.add(frame, text=self.i18n.t("settings_tab_advanced"))

        adv = self.data.get("advanced", {})

        # 爬虫
        crawler_frame = ttk.LabelFrame(frame, text=self.i18n.t("settings_advanced_crawler_frame"))
        crawler_frame.pack(fill="x", pady=(0, 10))

        c1 = ttk.Frame(crawler_frame)
        c1.pack(fill="x", pady=2)
        ttk.Label(c1, text=self.i18n.t("settings_crawler_delay"), width=16).pack(side="left")
        self.crawl_delay_var = tk.DoubleVar(value=adv.get("crawler_delay", 2.5))
        ttk.Entry(c1, textvariable=self.crawl_delay_var, width=10).pack(side="left")

        ttk.Label(c1, text="  ", width=2).pack(side="left")
        ttk.Label(c1, text=self.i18n.t("settings_crawler_timeout"), width=12).pack(side="left")
        self.crawl_timeout_var = tk.IntVar(value=adv.get("crawler_timeout", 30))
        ttk.Entry(c1, textvariable=self.crawl_timeout_var, width=10).pack(side="left")

        c2 = ttk.Frame(crawler_frame)
        c2.pack(fill="x", pady=2)
        ttk.Label(c2, text=self.i18n.t("settings_crawler_concurrency"), width=16).pack(side="left")
        self.crawl_concur_var = tk.IntVar(value=adv.get("crawler_concurrency", 1))
        ttk.Spinbox(c2, from_=1, to=5, textvariable=self.crawl_concur_var, width=8).pack(side="left")

        ttk.Label(c2, text="  ", width=2).pack(side="left")
        ttk.Label(c2, text=self.i18n.t("settings_search_limit"), width=14).pack(side="left")
        ttk.Label(c2, text=self.i18n.t("settings_neo4j_limit")).pack(side="left")
        self.neo4j_limit_var = tk.IntVar(value=adv.get("neo4j_search_limit", 20))
        ttk.Spinbox(c2, from_=5, to=100, textvariable=self.neo4j_limit_var, width=6).pack(side="left", padx=2)
        ttk.Label(c2, text=self.i18n.t("settings_chroma_limit")).pack(side="left")
        self.chroma_limit_var = tk.IntVar(value=adv.get("chroma_search_limit", 5))
        ttk.Spinbox(c2, from_=1, to=20, textvariable=self.chroma_limit_var, width=6).pack(side="left", padx=2)

        # 可视化
        vis_frame = ttk.LabelFrame(frame, text=self.i18n.t("settings_vis_frame"))
        vis_frame.pack(fill="x", pady=(0, 10))

        v1 = ttk.Frame(vis_frame)
        v1.pack(fill="x", pady=2)
        ttk.Label(v1, text=self.i18n.t("settings_flask_port"), width=16).pack(side="left")
        self.flask_port_var = tk.IntVar(value=adv.get("flask_port", 5001))
        ttk.Spinbox(v1, from_=1024, to=65535, textvariable=self.flask_port_var, width=10).pack(side="left")

        self.auto_browser_var = tk.BooleanVar(value=adv.get("auto_open_browser", True))
        ttk.Checkbutton(v1, text=self.i18n.t("settings_auto_browser"), variable=self.auto_browser_var).pack(side="left", padx=10)

        # 日志
        log_frame = ttk.LabelFrame(frame, text=self.i18n.t("settings_log_frame"))
        log_frame.pack(fill="x")

        l1 = ttk.Frame(log_frame)
        l1.pack(fill="x", pady=2)
        ttk.Label(l1, text=self.i18n.t("settings_log_level"), width=16).pack(side="left")
        self.log_level_var = tk.StringVar(value=adv.get("log_level", "INFO"))
        ttk.Combobox(l1, textvariable=self.log_level_var, values=["DEBUG", "INFO", "WARNING"], state="readonly", width=12).pack(side="left")

        l2 = ttk.Frame(log_frame)
        l2.pack(fill="x", pady=2)
        self.save_chat_var = tk.BooleanVar(value=adv.get("save_chat_log", False))
        ttk.Checkbutton(l2, text=self.i18n.t("settings_save_chat"), variable=self.save_chat_var).pack(side="left")
        self.chat_log_dir_var = tk.StringVar(value=adv.get("chat_log_dir", ""))
        ttk.Entry(l2, textvariable=self.chat_log_dir_var, width=30).pack(side="left", fill="x", expand=True, padx=2)
        ttk.Button(l2, text=self.i18n.t("settings_chat_log_browse"), command=self._browse_chat_log).pack(side="left", padx=2)

        l3 = ttk.Frame(log_frame)
        l3.pack(fill="x", pady=2)
        self.auto_check_var = tk.BooleanVar(value=adv.get("auto_check_services", True))
        ttk.Checkbutton(l3, text=self.i18n.t("settings_auto_check"), variable=self.auto_check_var).pack(anchor="w")

        self._add_tab_buttons(frame, "advanced")

    def _browse_chat_log(self):
        path = filedialog.askdirectory(title=self.i18n.t("settings_save_chat"))
        if path:
            self.chat_log_dir_var.set(path)

    def _add_tab_buttons(self, parent, tab_name):
        """添加固定在对话框底部的 恢复默认/取消/确定 按钮"""
        if self._button_bar is not None:
            return
        btn_frame = ttk.Frame(self.dialog)
        btn_frame.pack(side="bottom", fill="x", padx=12, pady=(6, 10))
        self._button_bar = btn_frame
        ttk.Button(btn_frame, text=self.i18n.t("settings_btn_reset"), command=self._reset_defaults, width=12).pack(side="left", padx=2)
        ttk.Label(btn_frame, text="").pack(side="left", fill="x", expand=True)
        ttk.Button(btn_frame, text=self.i18n.t("settings_btn_cancel"), command=self.dialog.destroy, width=8).pack(side="right", padx=2)
        ttk.Button(btn_frame, text=self.i18n.t("settings_btn_ok"), command=self._save, width=8).pack(side="right", padx=2)

    # ─── 保存与重置 ───────────────────────────────────

    def _collect_data(self) -> dict:
        """从所有控件收集数据"""
        return {
            "ui": {
                "theme": self.theme_var.get(),
                "font_scale": self.font_scale_var.get(),
                "chat_bg": self.color_vars["chat_bg"].get(),
                "chat_fg": self.color_vars["chat_fg"].get(),
                "user_color": self.color_vars["user_color"].get(),
                "ai_color": self.color_vars["ai_color"].get(),
                "always_on_top": self.always_top_var.get(),
                "minimize_to_tray": self.min_tray_var.get(),
                "language": self.lang_var.get(),
            },
            "tololo_theme": {
                "primary": self.tololo_color_vars["primary"].get(),
                "bg": self.tololo_color_vars["bg"].get(),
                "fg": self.tololo_color_vars["fg"].get(),
                "accent": self.tololo_color_vars["accent"].get(),
                "secondary_bg": self.tololo_color_vars["secondary_bg"].get(),
            },
            "connect": {
                "neo4j_uri": self.connect_entries["neo4j_uri"].get(),
                "neo4j_user": self.connect_entries["neo4j_user"].get(),
                "neo4j_password": self.neo4j_pwd_var.get(),
                "ollama_url": self.connect_entries["ollama_url"].get(),
                "ollama_model": self.connect_entries["ollama_model"].get(),
                "ollama_timeout": int(self.connect_entries["ollama_timeout"].get()),
                "chroma_path": self.chroma_path_var.get(),
            },
            "llm_source": {
                "use_remote_api": self.use_remote_var.get(),
                "api_base": self.api_base_var.get(),
                "remote_model": self.remote_model_var.get(),
                "api_key": self.api_key_var.get(),
            },
            "agent": {
                "system_role": self.system_role_text.get("1.0", "end-1c"),
                "retrieval_instruction": self.retrieval_text.get("1.0", "end-1c"),
                "fallback_response": self.fallback_text.get("1.0", "end-1c"),
                "temperature": self.temp_var.get(),
                "top_p": self.topp_var.get(),
                "style_preset": "default",
                "max_tokens": self.max_tokens_var.get(),
                "history_limit": 10,
            },
            "advanced": {
                "crawler_delay": self.crawl_delay_var.get(),
                "crawler_timeout": self.crawl_timeout_var.get(),
                "crawler_concurrency": self.crawl_concur_var.get(),
                "flask_port": self.flask_port_var.get(),
                "auto_open_browser": self.auto_browser_var.get(),
                "auto_check_services": self.auto_check_var.get(),
                "save_chat_log": self.save_chat_var.get(),
                "chat_log_dir": self.chat_log_dir_var.get(),
                "log_level": self.log_level_var.get(),
                "neo4j_search_limit": self.neo4j_limit_var.get(),
                "chroma_search_limit": self.chroma_limit_var.get(),
            },
        }

    def _save(self):
        """收集数据 → 保存 → 回调 → 关闭"""
        try:
            data = self._collect_data()
            self.settings.save(data)
            if self.on_save_callback:
                self.on_save_callback(data)
            self.dialog.destroy()
        except Exception as e:
            messagebox.showerror(self.i18n.t("error"),
                                 self.i18n.t("save_failed", error=str(e)))

    def _reset_defaults(self):
        defaults = SettingsManager.DEFAULT_SETTINGS
        # 将默认值填充到控件
        self.theme_var.set(defaults["ui"]["theme"])
        self.font_scale_var.set(defaults["ui"]["font_scale"])
        self.lang_var.set(defaults["ui"]["language"])
        self.color_vars["chat_bg"].set(defaults["ui"]["chat_bg"])
        self.color_vars["chat_fg"].set(defaults["ui"]["chat_fg"])
        self.color_vars["user_color"].set(defaults["ui"]["user_color"])
        self.color_vars["ai_color"].set(defaults["ui"]["ai_color"])
        self.always_top_var.set(defaults["ui"]["always_on_top"])
        self.min_tray_var.set(defaults["ui"]["minimize_to_tray"])

        # tololo theme
        tololo = defaults.get("tololo_theme", {})
        self.tololo_color_vars["primary"].set(tololo.get("primary", "#6c5ce7"))
        self.tololo_color_vars["bg"].set(tololo.get("bg", "#1a1a2e"))
        self.tololo_color_vars["fg"].set(tololo.get("fg", "#e0e0e0"))
        self.tololo_color_vars["accent"].set(tololo.get("accent", "#00b894"))
        self.tololo_color_vars["secondary_bg"].set(tololo.get("secondary_bg", "#16213e"))

        self.connect_entries["neo4j_uri"].set(defaults["connect"]["neo4j_uri"])
        self.connect_entries["neo4j_user"].set(defaults["connect"]["neo4j_user"])
        self.neo4j_pwd_var.set(defaults["connect"]["neo4j_password"])
        self.connect_entries["ollama_url"].set(defaults["connect"]["ollama_url"])
        self.connect_entries["ollama_model"].set(defaults["connect"]["ollama_model"])
        self.connect_entries["ollama_timeout"].set(str(defaults["connect"]["ollama_timeout"]))
        self.chroma_path_var.set(defaults["connect"]["chroma_path"])

        self.use_remote_var.set(defaults["llm_source"]["use_remote_api"])
        self.api_base_var.set(defaults["llm_source"]["api_base"])
        self.remote_model_var.set(defaults["llm_source"]["remote_model"])
        self.api_key_var.set(defaults["llm_source"]["api_key"])
        self._toggle_remote_api()

        self.temp_var.set(defaults["agent"]["temperature"])
        self.temp_label.config(text=f"{defaults['agent']['temperature']:.1f}")
        self.topp_var.set(defaults["agent"]["top_p"])
        self.topp_label.config(text=f"{defaults['agent']['top_p']:.2f}")
        self.max_tokens_var.set(defaults["agent"]["max_tokens"])
        self.system_role_text.delete("1.0", "end")
        self.system_role_text.insert("1.0", defaults["agent"]["system_role"])
        self.retrieval_text.delete("1.0", "end")
        self.retrieval_text.insert("1.0", defaults["agent"]["retrieval_instruction"])
        self.fallback_text.delete("1.0", "end")
        self.fallback_text.insert("1.0", defaults["agent"]["fallback_response"])

        self.crawl_delay_var.set(defaults["advanced"]["crawler_delay"])
        self.crawl_timeout_var.set(defaults["advanced"]["crawler_timeout"])
        self.crawl_concur_var.set(defaults["advanced"]["crawler_concurrency"])
        self.flask_port_var.set(defaults["advanced"]["flask_port"])
        self.auto_browser_var.set(defaults["advanced"]["auto_open_browser"])
        self.auto_check_var.set(defaults["advanced"]["auto_check_services"])
        self.save_chat_var.set(defaults["advanced"]["save_chat_log"])
        self.chat_log_dir_var.set(defaults["advanced"]["chat_log_dir"])
        self.log_level_var.set(defaults["advanced"]["log_level"])
        self.neo4j_limit_var.set(defaults["advanced"]["neo4j_search_limit"])
        self.chroma_limit_var.set(defaults["advanced"]["chroma_search_limit"])

        # 更新 tololo 面板可见性
        self._on_theme_changed()
