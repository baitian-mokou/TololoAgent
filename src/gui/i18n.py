"""
国际化模块 — I18nManager 单例，支持中/英双语即时切换
"""
import re


TRANSLATIONS = {
    "zh_CN": {
        # ── 窗口标题 ──
        "window_title": "🪐 托洛洛Agent — 太阳系知识图谱系统",

        # ── 菜单栏 ──
        "menu_file": "文件",
        "menu_exit": "退出",
        "menu_settings": "设置",
        "menu_terminal": "终端",
        "menu_help": "帮助",
        "menu_about": "关于",
        "terminal_not_available": "当前启动方式没有可显示的控制台终端。",

        # ── 关于对话框 ──
        "about_title": "关于托洛洛Agent",
        "about_text": "托洛洛Agent v2.0\n太阳系知识图谱系统\n技术栈: Python + Neo4j + Ollama + Chroma",

        # ── 主标签页 ──
        "tab_agent": " 🤖 Agent对话 ",
        "tab_data_engineering": " 📦 数据工程 ",

        # ── 内嵌标签页 ──
        "tab_crawler": " 🕷爬虫 ",
        "tab_nlp": " 🧠NLP处理 ",
        "tab_database": " 🗄️ 数据库 ",
        "tab_visualize": " 📊 可视化 ",

        # ── Agent对话页 ──
        "agent_title": "🤖 智能Agent — 探索太阳系知识图谱",
        "agent_ollama_status_ok": "✅ Ollama: 运行中",
        "agent_ollama_status_fail": "❌ Ollama: 未运行",
        "agent_ollama_status_checking": "⏳ Ollama: 检测中...",
        "agent_ollama_status_error": "❌ Ollama: 检测失败",
        "agent_model_status_ok": "✅ 模型: {model}",
        "agent_model_status_pending": "⏳ 模型: {model} (未下载)",
        "agent_model_status_checking": "⏳ 模型: 检测中...",
        "agent_remote_status_ok": "✅ 联网API: 已启用",
        "agent_remote_model_status_ok": "✅ 联网模型: {model}",
        "agent_refresh_status": "🔄 刷新状态",
        "agent_ask_label": "提问:",
        "agent_ask_button": "🤖 智能问答",
        "agent_ask_thinking": "⏳ 思考中...",
        "agent_toggle_detail": "📋 检索详情 ▶",
        "agent_toggle_detail_open": "📋 检索详情 ▼",
        "agent_clear_button": "🗑 清空",
        "agent_chat_history": "对话历史",
        "agent_user_prefix": "\n🧑 你: ",
        "agent_assistant_prefix": "\n托洛洛: ",
        "agent_waiting": "⏳ 正在检索知识库并生成回答...\n",
        "agent_cleared": "👋 对话已清空，请输入新的问题。",
        "agent_cancelled_model_changed": "⚠️ 模型设置已变更，上一条回答已取消。",
        "agent_ollama_not_running": "❌ Ollama 服务未运行！请先启动 Ollama。",
        "agent_model_not_available": "❌ 模型 {model} 未下载！请先运行 `ollama pull {model}`",
        "agent_search_result_title": "检索详情面板",
        "agent_neo4j_result_title": "Neo4j 关系查询结果",
        "agent_chroma_result_title": "Chroma 语义搜索结果",
        "agent_no_neo4j_result": "未找到相关关系",
        "agent_no_chroma_result": "未找到相关语义片段",
        "agent_neo4j_found": "找到 {count} 条关系:",
        "agent_chroma_found": "找到 {count} 个相关片段:",
        "agent_searching_neo4j": "🔍 搜索: {query}\n",
        "agent_neo4j_not_connected": "❌ Neo4j 未连接",
        "agent_neo4j_no_result": "未找到相关结果",
        "agent_neo4j_result_header": "找到 {count} 条关系:",
        "agent_searching_chroma": "🔍 语义搜索: {query}\n",
        "agent_chroma_no_result": "未找到相关片段",
        "agent_chroma_result_header": "找到 {count} 个相关片段:",

        # ── 爬虫页 ──
        "crawler_title": "🕷️ 多源受控采集 — 太阳系来源入库",
        "crawler_btn_start": "🚀 开始爬取",
        "crawler_btn_source_zh_wikipedia": "中文维基",
        "crawler_btn_source_wikidata": "Wikidata",
        "crawler_btn_source_nasa": "NASA",
        "crawler_btn_source_esa": "ESA",
        "crawler_btn_source_all": "全部爬取（调试）",
        "crawler_cleanup_label": "删除对应来源采集产物:",
        "crawler_btn_delete_source": "删除{source}",
        "crawler_btn_stop": "⏹ 停止",
        "crawler_start_log": "🚀 开始爬取维基百科太阳系数据...\n",
        "crawler_start_log_source": "🚀 开始执行 {source} 受控采集，limit={limit}",
        "crawler_start_log_all": "🚀 开始执行全部来源受控采集，来源数={count}，每源limit={limit}",
        "crawler_progress_source": "🔄 正在处理第 {current}/{total} 个来源：{source}",
        "crawler_complete": "✅ 爬取完成！新爬取 {success} 个页面，共 {total} 个页面",
        "crawler_complete_source": "✅ {source} 完成：raw={raw}，triples={triples}，narratives={narratives}",
        "crawler_complete_all": "✅ 全部来源采集完成，共处理 {count} 个来源",
        "crawler_delete_confirm_title": "确认删除采集数据",
        "crawler_delete_confirm_message": "确定删除 {source} 的全部采集产物吗？\n\n这会清理 raw_json、triples、ingestion report，以及对应 source 的图/向量检索数据。",
        "crawler_delete_start": "🧹 开始删除 {source} 的采集产物...",
        "crawler_delete_complete": "✅ {source} 清理完成：删除目录={deleted_dirs}，删除文件={deleted_files}，缺失目录={missing_dirs}，缺失文件={missing_files}",
        "crawler_delete_runtime": "ℹ️ 运行时清理：Neo4j={graph_status}，Chroma={chroma_status}",
        "crawler_error": "❌ 爬虫错误: {error}",
        "crawler_stopped": "⏹ 停止操作...",
        "crawler_log_title": "运行日志",

        # ── NLP页 ──
        "nlp_title": "🧠 NLP预处理 — 实体识别与关系抽取",
        "nlp_desc": "从 data/raw_json/{source}/*.json 读取当前来源原始记录（HTML 或 API JSON）→ 来源适配标准化 → 关系三元组 → 叙事片段",
        "nlp_btn_start": "🧠 开始NLP处理",
        "nlp_start_log": "🧠 开始NLP预处理...\n",
        "nlp_start_log_source": "🧠 开始 {source} 的NLP预处理...\n",
        "nlp_complete": "✅ NLP完成！共 {triples} 个三元组, {narratives} 个叙事片段",
        "nlp_next_step": "ℹ️ NLP 已生成本地 JSON 文件；如需 Neo4j 节点数变化，请到数据库页点击“导入三元组到Neo4j”。",
        "nlp_error": "❌ NLP错误: {error}",
        "nlp_log_title": "运行日志",

        # ── 数据库页 ──
        "db_title": "🗄️ 数据库管理 — Neo4j + Chroma 向量库",
        "db_neo4j_frame": "Neo4j 图数据库",
        "db_btn_import_neo4j": "📥 导入三元组到Neo4j",
        "db_btn_refresh": "🔄 刷新状态",
        "db_neo4j_waiting": "Neo4j: 等待连接...",
        "db_neo4j_connected": "✅ 已连接 | 节点: {nodes} | 关系: {rels} | 标签: {labels}种",
        "db_neo4j_failed": "❌ Neo4j 连接失败",
        "db_neo4j_imported": "✅ Neo4j导入完成！{nodes}节点, {rels}关系",
        "db_chroma_frame": "Chroma 向量库（叙事知识）",
        "db_btn_import_chroma": "📥 导入叙事到Chroma",
        "db_chroma_waiting": "Chroma: 等待连接...",
        "db_chroma_ready": "✅ 已就绪 | 记录数: {total}",
        "db_chroma_imported": "✅ Chroma导入完成！{count}条",
        "db_danger_frame": "危险操作",
        "db_btn_clear_all": "🧹 一键清空 Neo4j + Chroma",
        "db_clear_confirm_title": "确认清空知识库",
        "db_clear_confirm_msg": "此操作会删除 Neo4j 图数据库中的全部节点/关系，并清空 Chroma 向量库。\n\n该操作不可撤销，确定继续吗？",
        "db_clear_start": "🧹 开始清空 Neo4j 与 Chroma...",
        "db_clear_neo4j_done": "✅ Neo4j 已清空",
        "db_clear_neo4j_failed": "❌ Neo4j 未连接，无法清空",
        "db_clear_neo4j_error": "❌ Neo4j 清空失败: {error}",
        "db_clear_chroma_done": "✅ Chroma 已清空，删除 {count} 条向量记录",
        "db_clear_chroma_error": "❌ Chroma 清空失败: {error}",
        "db_clear_done": "✅ 知识库已全部清空",
        "db_clear_partial": "⚠️ 清空操作已结束，但有部分数据库未成功清空，请查看上方日志",
        "db_log_title": "操作日志",

        # ── 可视化页 ──
        "vis_title": "📊 可视化 — D3.js力导向知识图谱",
        "vis_desc": "从Neo4j读取知识图谱数据，在浏览器中展示力导向图",
        "vis_btn_start": "🚀 启动可视化服务",
        "vis_btn_stop": "⏹ 停止服务",
        "vis_btn_open": "🌐 打开浏览器",
        "vis_status_idle": "状态: 未启动",
        "vis_status_running": "✅ 服务已运行 http://127.0.0.1:{port}",
        "vis_status_stopped": "状态: 已停止（后台线程随GUI退出）",
        "vis_log_title": "操作日志",
        "vis_starting": "🚀 启动可视化服务 http://127.0.0.1:{port} ...",
        "vis_started": "✅ 可视化服务启动成功！",
        "vis_stopped": "⏹ 可视化服务将在GUI关闭后停止",
        "vis_browser_opened": "🌐 已打开浏览器 http://127.0.0.1:{port}",
        "vis_log_startup": "日志文件: 控制台",

        # ── 设置对话框 ──
        "settings_title": "⚙️ 设置",
        "settings_tab_ui": " 🎨 界面与语言 ",
        "settings_tab_connect": " 🔗 服务连接 ",
        "settings_tab_agent": " 🤖 Agent提示词 ",
        "settings_tab_advanced": " ⚙️ 高级 ",

        # 界面标签页
        "settings_theme_frame": "主题与语言",
        "settings_theme_label": "界面主题:",
        "settings_lang_label": "界面语言:",
        "settings_font_scale_label": "字体缩放:",
        "settings_color_frame": "对话区颜色",
        "settings_color_bg": "对话背景色:",
        "settings_color_fg": "对话文字色:",
        "settings_color_user": "用户消息色:",
        "settings_color_ai": "AI消息色:",
        "settings_opt_frame": "其他选项",
        "settings_always_top": "窗口置顶（始终在最前）",
        "settings_min_tray": "启动时最小化到托盘",

        # 自定义主题
        "settings_tololo_frame": "托洛洛自定义主题",
        "settings_tololo_primary": "主色调:",
        "settings_tololo_bg": "背景色:",
        "settings_tololo_fg": "文字色:",
        "settings_tololo_accent": "强调色:",
        "settings_tololo_secondary_bg": "次要背景色:",
        "settings_tololo_pick": "🎨",

        # 连接标签页
        "settings_neo4j_frame": "Neo4j 图数据库",
        "settings_neo4j_uri": "连接地址:",
        "settings_neo4j_user": "用户名:",
        "settings_neo4j_pwd": "密码:",
        "settings_neo4j_test": "🧪 测试",
        "settings_neo4j_success": "✅ Neo4j 连接成功！",
        "settings_neo4j_fail": "❌ 连接失败: {error}",
        "settings_ollama_frame": "Ollama 本地大模型",
        "settings_ollama_url": "API地址:",
        "settings_ollama_model": "模型名:",
        "settings_ollama_timeout": "超时(秒):",
        "settings_ollama_refresh": "🔄 从Ollama拉取模型列表",
        "settings_ollama_test": "🧪 测试连接",
        "settings_ollama_ok": "✅ Ollama 连接成功",
        "settings_ollama_models_found": "✅ 找到 {count} 个模型",
        "settings_ollama_no_models": "⚠️ 未找到模型",
        "settings_chroma_frame": "Chroma 向量库路径",
        "settings_chroma_path": "路径:",
        "settings_chroma_browse": "📂 选择",

        # Agent提示词标签页
        "settings_llm_source_frame": "🌐 大语言模型来源",
        "settings_use_remote": "使用远程API服务（关闭则使用本地Ollama）",
        "settings_api_base": "API 地址:",
        "settings_api_model": "API 模型:",
        "settings_api_key": "API 密钥:",
        "settings_param_frame": "🎛️ 推理参数",
        "settings_temperature": "🌡️ 感情温度:",
        "settings_temp_hint": " 低←严谨 →创意",
        "settings_top_p": "🎯 Top-P 采样:",
        "settings_max_tokens": "📏 单次最大回复:",
        "settings_tokens_unit": "tokens",
        "settings_system_prompt_frame": "📝 系统提示词",
        "settings_system_role": "系统角色设定:",
        "settings_retrieval_instruction": "检索后回答指引:",
        "settings_fallback": "知识不足时的回复语:",

        # 高级标签页
        "settings_advanced_crawler_frame": "爬虫设置",
        "settings_crawler_delay": "请求延迟(秒):",
        "settings_crawler_timeout": "超时(秒):",
        "settings_crawler_concurrency": "最大并发数:",
        "settings_search_limit": "知识检索上限:",
        "settings_neo4j_limit": "Neo4j:",
        "settings_chroma_limit": "Chroma:",
        "settings_vis_frame": "可视化服务",
        "settings_flask_port": "端口号:",
        "settings_auto_browser": "启动后自动打开浏览器",
        "settings_log_frame": "日志与记录",
        "settings_log_level": "日志级别:",
        "settings_save_chat": "保存对话记录到",
        "settings_chat_log_browse": "📂 选择",
        "settings_auto_check": "启动时自动检测Ollama/Neo4j状态",

        # 按钮
        "settings_btn_reset": "🔄 恢复默认",
        "settings_btn_cancel": "取消",
        "settings_btn_ok": "确定",
        "settings_saved": "✅ 设置已保存！",

        # 确认对话框
        "settings_confirm_reset": "确认",
        "settings_confirm_reset_msg": "重置所有设置为默认值？\n（仅重置当前对话框，需点击保存生效）",

        # ── 状态栏 ──
        "status_ready": "就绪",

        # ── 通用 ──
        "error": "错误",
        "save_failed": "保存设置失败: {error}",
    },

    "en_US": {
        # ── Window Title ──
        "window_title": "🪐 TololoAgent — Solar System Knowledge Graph System",

        # ── Menu ──
        "menu_file": "File",
        "menu_exit": "Exit",
        "menu_settings": "Settings",
        "menu_terminal": "Terminal",
        "menu_help": "Help",
        "menu_about": "About",
        "terminal_not_available": "No console terminal is available for the current launch mode.",

        # ── About Dialog ──
        "about_title": "About TololoAgent",
        "about_text": "TololoAgent v2.0\nSolar System Knowledge Graph System\nTech Stack: Python + Neo4j + Ollama + Chroma",

        # ── Main Tabs ──
        "tab_agent": " 🤖 Agent Chat ",
        "tab_data_engineering": " 📦 Data Engineering ",

        # ── Inner Tabs ──
        "tab_crawler": " 🕷 Crawler ",
        "tab_nlp": " 🧠 NLP ",
        "tab_database": " 🗄️ Database ",
        "tab_visualize": " 📊 Visualize ",

        # ── Agent Tab ──
        "agent_title": "🤖 Smart Agent — Explore the Solar System",
        "agent_ollama_status_ok": "✅ Ollama: Running",
        "agent_ollama_status_fail": "❌ Ollama: Not Running",
        "agent_ollama_status_checking": "⏳ Ollama: Checking...",
        "agent_ollama_status_error": "❌ Ollama: Check Failed",
        "agent_model_status_ok": "✅ Model: {model}",
        "agent_model_status_pending": "⏳ Model: {model} (not downloaded)",
        "agent_model_status_checking": "⏳ Model: Checking...",
        "agent_remote_status_ok": "✅ Online API: Enabled",
        "agent_remote_model_status_ok": "✅ Online Model: {model}",
        "agent_refresh_status": "🔄 Refresh",
        "agent_ask_label": "Ask:",
        "agent_ask_button": "🤖 Ask AI",
        "agent_ask_thinking": "⏳ Thinking...",
        "agent_toggle_detail": "📋 Details ▶",
        "agent_toggle_detail_open": "📋 Details ▼",
        "agent_clear_button": "🗑 Clear",
        "agent_chat_history": "Chat History",
        "agent_user_prefix": "\n🧑 You: ",
        "agent_assistant_prefix": "\nTololo: ",
        "agent_waiting": "⏳ Searching knowledge base and generating answer...\n",
        "agent_cleared": "👋 Chat cleared. Enter a new question.",
        "agent_cancelled_model_changed": "⚠️ Model settings changed. The previous answer was cancelled.",
        "agent_ollama_not_running": "❌ Ollama service is not running! Please start Ollama first.",
        "agent_model_not_available": "❌ Model {model} not found! Please run `ollama pull {model}`",
        "agent_search_result_title": "Search Details",
        "agent_neo4j_result_title": "Neo4j Graph Results",
        "agent_chroma_result_title": "Chroma Semantic Results",
        "agent_no_neo4j_result": "No related relations found",
        "agent_no_chroma_result": "No relevant semantic snippets found",
        "agent_neo4j_found": "Found {count} relations:",
        "agent_chroma_found": "Found {count} relevant snippets:",
        "agent_searching_neo4j": "🔍 Search: {query}\n",
        "agent_neo4j_not_connected": "❌ Neo4j not connected",
        "agent_neo4j_no_result": "No results found",
        "agent_neo4j_result_header": "Found {count} relations:",
        "agent_searching_chroma": "🔍 Semantic Search: {query}\n",
        "agent_chroma_no_result": "No relevant snippets found",
        "agent_chroma_result_header": "Found {count} relevant snippets:",

        # ── Crawler Tab ──
        "crawler_title": "🕷️ Controlled Multi-Source Ingestion",
        "crawler_btn_start": "🚀 Start Crawling",
        "crawler_btn_source_zh_wikipedia": "ZH Wikipedia",
        "crawler_btn_source_wikidata": "Wikidata",
        "crawler_btn_source_nasa": "NASA",
        "crawler_btn_source_esa": "ESA",
        "crawler_btn_source_all": "Crawl All (Debug)",
        "crawler_cleanup_label": "Delete source ingestion outputs:",
        "crawler_btn_delete_source": "Delete {source}",
        "crawler_btn_stop": "⏹ Stop",
        "crawler_start_log": "🚀 Start crawling Wikipedia solar system data...\n",
        "crawler_start_log_source": "🚀 Start controlled ingestion for {source}, limit={limit}",
        "crawler_start_log_all": "🚀 Start controlled ingestion for all sources, count={count}, per-source limit={limit}",
        "crawler_progress_source": "🔄 Processing source {current}/{total}: {source}",
        "crawler_complete": "✅ Crawl complete! {success} new pages, {total} total pages",
        "crawler_complete_source": "✅ {source} finished: raw={raw}, triples={triples}, narratives={narratives}",
        "crawler_complete_all": "✅ Finished controlled ingestion for all sources: {count} sources",
        "crawler_delete_confirm_title": "Confirm deletion",
        "crawler_delete_confirm_message": "Delete all ingestion outputs for {source}?\n\nThis removes raw_json, triples, the ingestion report, and the source-specific graph/vector retrieval data.",
        "crawler_delete_start": "🧹 Start deleting ingestion outputs for {source}...",
        "crawler_delete_complete": "✅ {source} cleanup finished: deleted_dirs={deleted_dirs}, deleted_files={deleted_files}, missing_dirs={missing_dirs}, missing_files={missing_files}",
        "crawler_delete_runtime": "ℹ️ Runtime cleanup: Neo4j={graph_status}, Chroma={chroma_status}",
        "crawler_error": "❌ Crawler error: {error}",
        "crawler_stopped": "⏹ Stopping...",
        "crawler_log_title": "Log",

        # ── NLP Tab ──
        "nlp_title": "🧠 NLP Preprocessing — Entity Recognition & Relation Extraction",
        "nlp_desc": "Read source raw records (HTML or API JSON) from data/raw_json/{source}/*.json → Source-aware normalization → Triples → Narratives",
        "nlp_btn_start": "🧠 Start NLP",
        "nlp_start_log": "🧠 Start NLP preprocessing...\n",
        "nlp_start_log_source": "🧠 Start NLP preprocessing for {source}...\n",
        "nlp_complete": "✅ NLP complete! {triples} triples, {narratives} narratives",
        "nlp_next_step": "ℹ️ NLP generated local JSON files. To update Neo4j node counts, open Database and click “Import Triples to Neo4j”.",
        "nlp_error": "❌ NLP error: {error}",
        "nlp_log_title": "Log",

        # ── Database Tab ──
        "db_title": "🗄️ Database Management — Neo4j + Chroma Vector Store",
        "db_neo4j_frame": "Neo4j Graph Database",
        "db_btn_import_neo4j": "📥 Import Triples to Neo4j",
        "db_btn_refresh": "🔄 Refresh",
        "db_neo4j_waiting": "Neo4j: Waiting for connection...",
        "db_neo4j_connected": "✅ Connected | Nodes: {nodes} | Rels: {rels} | Labels: {labels}",
        "db_neo4j_failed": "❌ Neo4j connection failed",
        "db_neo4j_imported": "✅ Neo4j import complete! {nodes} nodes, {rels} relations",
        "db_chroma_frame": "Chroma Vector Store (Narratives)",
        "db_btn_import_chroma": "📥 Import Narratives to Chroma",
        "db_chroma_waiting": "Chroma: Waiting...",
        "db_chroma_ready": "✅ Ready | Records: {total}",
        "db_chroma_imported": "✅ Chroma import complete! {count} entries",
        "db_danger_frame": "Danger Zone",
        "db_btn_clear_all": "🧹 Clear Neo4j + Chroma",
        "db_clear_confirm_title": "Confirm Knowledge Base Clear",
        "db_clear_confirm_msg": "This will delete all Neo4j nodes/relationships and clear the Chroma vector store.\n\nThis action cannot be undone. Continue?",
        "db_clear_start": "🧹 Clearing Neo4j and Chroma...",
        "db_clear_neo4j_done": "✅ Neo4j cleared",
        "db_clear_neo4j_failed": "❌ Neo4j is not connected, cannot clear",
        "db_clear_neo4j_error": "❌ Failed to clear Neo4j: {error}",
        "db_clear_chroma_done": "✅ Chroma cleared, removed {count} vector records",
        "db_clear_chroma_error": "❌ Failed to clear Chroma: {error}",
        "db_clear_done": "✅ Knowledge base cleared",
        "db_clear_partial": "⚠️ Clear operation finished, but part of the databases failed. Check the log above",
        "db_log_title": "Operation Log",

        # ── Visualize Tab ──
        "vis_title": "📊 Visualization — D3.js Force-Directed Graph",
        "vis_desc": "Load knowledge graph data from Neo4j and display in browser",
        "vis_btn_start": "🚀 Start Visualization",
        "vis_btn_stop": "⏹ Stop Service",
        "vis_btn_open": "🌐 Open Browser",
        "vis_status_idle": "Status: Not Started",
        "vis_status_running": "✅ Running at http://127.0.0.1:{port}",
        "vis_status_stopped": "Status: Stopped (exits with GUI)",
        "vis_log_title": "Log",
        "vis_starting": "🚀 Starting visualization service http://127.0.0.1:{port} ...",
        "vis_started": "✅ Visualization service started!",
        "vis_stopped": "⏹ Visualization service will stop when GUI closes",
        "vis_browser_opened": "🌐 Browser opened http://127.0.0.1:{port}",
        "vis_log_startup": "Log file: Console",

        # ── Settings Dialog ──
        "settings_title": "⚙️ Settings",
        "settings_tab_ui": " 🎨 Interface & Language ",
        "settings_tab_connect": " 🔗 Connections ",
        "settings_tab_agent": " 🤖 Agent Prompts ",
        "settings_tab_advanced": " ⚙️ Advanced ",

        # UI Tab
        "settings_theme_frame": "Theme & Language",
        "settings_theme_label": "Theme:",
        "settings_lang_label": "Language:",
        "settings_font_scale_label": "Font Scale:",
        "settings_color_frame": "Chat Colors",
        "settings_color_bg": "Chat Background:",
        "settings_color_fg": "Chat Text:",
        "settings_color_user": "User Color:",
        "settings_color_ai": "AI Color:",
        "settings_opt_frame": "Other Options",
        "settings_always_top": "Always on Top",
        "settings_min_tray": "Minimize to Tray on Start",

        # Custom Theme
        "settings_tololo_frame": "Tololo Custom Theme",
        "settings_tololo_primary": "Primary:",
        "settings_tololo_bg": "Background:",
        "settings_tololo_fg": "Text Color:",
        "settings_tololo_accent": "Accent:",
        "settings_tololo_secondary_bg": "Secondary BG:",
        "settings_tololo_pick": "🎨",

        # Connection Tab
        "settings_neo4j_frame": "Neo4j Graph Database",
        "settings_neo4j_uri": "URI:",
        "settings_neo4j_user": "User:",
        "settings_neo4j_pwd": "Password:",
        "settings_neo4j_test": "🧪 Test",
        "settings_neo4j_success": "✅ Neo4j connected successfully!",
        "settings_neo4j_fail": "❌ Connection failed: {error}",
        "settings_ollama_frame": "Ollama Local LLM",
        "settings_ollama_url": "API URL:",
        "settings_ollama_model": "Model:",
        "settings_ollama_timeout": "Timeout(s):",
        "settings_ollama_refresh": "🔄 Fetch Model List",
        "settings_ollama_test": "🧪 Test Connection",
        "settings_ollama_ok": "✅ Ollama connected successfully",
        "settings_ollama_models_found": "✅ Found {count} models",
        "settings_ollama_no_models": "⚠️ No models found",
        "settings_chroma_frame": "Chroma Vector Store Path",
        "settings_chroma_path": "Path:",
        "settings_chroma_browse": "📂 Browse",

        # Agent Prompts Tab
        "settings_llm_source_frame": "🌐 LLM Source",
        "settings_use_remote": "Use Remote API (uncheck for local Ollama)",
        "settings_api_base": "API Base:",
        "settings_api_model": "API Model:",
        "settings_api_key": "API Key:",
        "settings_param_frame": "🎛️ Inference Parameters",
        "settings_temperature": "🌡️ Temperature:",
        "settings_temp_hint": " Low←Precise →Creative",
        "settings_top_p": "🎯 Top-P:",
        "settings_max_tokens": "📏 Max Tokens:",
        "settings_tokens_unit": "tokens",
        "settings_system_prompt_frame": "📝 System Prompt",
        "settings_system_role": "System Role:",
        "settings_retrieval_instruction": "Retrieval Instruction:",
        "settings_fallback": "Fallback Response:",

        # Advanced Tab
        "settings_advanced_crawler_frame": "Crawler Settings",
        "settings_crawler_delay": "Delay(s):",
        "settings_crawler_timeout": "Timeout(s):",
        "settings_crawler_concurrency": "Concurrency:",
        "settings_search_limit": "Search Limits:",
        "settings_neo4j_limit": "Neo4j:",
        "settings_chroma_limit": "Chroma:",
        "settings_vis_frame": "Visualization Service",
        "settings_flask_port": "Port:",
        "settings_auto_browser": "Auto-open Browser",
        "settings_log_frame": "Logging & Records",
        "settings_log_level": "Log Level:",
        "settings_save_chat": "Save Chat Logs to",
        "settings_chat_log_browse": "📂 Browse",
        "settings_auto_check": "Auto-check Ollama/Neo4j on Startup",

        # Buttons
        "settings_btn_reset": "🔄 Reset Defaults",
        "settings_btn_cancel": "Cancel",
        "settings_btn_ok": "Save",
        "settings_saved": "✅ Settings saved!",

        # Confirm Dialog
        "settings_confirm_reset": "Confirm",
        "settings_confirm_reset_msg": "Reset all settings to defaults?\n(Only resets the dialog, click Save to apply)",

        # ── Status Bar ──
        "status_ready": "Ready",

        # ── General ──
        "error": "Error",
        "save_failed": "Failed to save settings: {error}",
    },
}


class I18nManager:
    """国际化管理器（单例）"""
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
        self.current_lang = "zh_CN"

    def set_language(self, lang: str):
        """设置当前语言"""
        if lang in TRANSLATIONS:
            self.current_lang = lang

    def t(self, key: str, **kwargs) -> str:
        """获取翻译文本，支持格式化参数"""
        lang_dict = TRANSLATIONS.get(self.current_lang, TRANSLATIONS["zh_CN"])
        text = lang_dict.get(key, key)
        if kwargs:
            try:
                text = text.format(**kwargs)
            except KeyError:
                pass
        return text

    def get_language(self) -> str:
        return self.current_lang
