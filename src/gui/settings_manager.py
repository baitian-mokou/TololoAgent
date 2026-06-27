"""
设置管理器 — 读写 settings.json，提供统一配置接口
"""
import os
import json

# 默认配置
DEFAULT_SETTINGS = {
    "ui": {
        "theme": "dark",
        "font_scale": 1.0,
        "chat_bg": "#0d1117",
        "chat_fg": "#e6edf3",
        "user_color": "#58a6ff",
        "ai_color": "#3fb950",
        "always_on_top": False,
        "minimize_to_tray": False,
        "language": "zh_CN"
    },
    "tololo_theme": {
        "primary": "#6c5ce7",
        "bg": "#1a1a2e",
        "fg": "#e0e0e0",
        "accent": "#00b894",
        "secondary_bg": "#16213e"
    },
    "connect": {
        "neo4j_uri": "bolt://127.0.0.1:7687",
        "neo4j_user": "neo4j",
        "neo4j_password": "12345678",
        "ollama_url": "http://localhost:11434",
        "ollama_model": "qwen3:4b",
        "ollama_timeout": 60,
        "chroma_path": ""
    },
    "llm_source": {
        "use_remote_api": False,
        "api_base": "https://api.openai.com/v1",
        "remote_model": "deepseek-v4-flash",
        "api_key": ""
    },
    "agent": {
        "system_role": "你是一个专业的太阳系天文学知识助手，基于托洛洛太阳系知识图谱系统为用户解答问题。",
        "retrieval_instruction": "请根据以下知识图谱检索结果，用中文回答用户的问题。如果检索结果不足以回答问题，请如实说明，不要编造信息。回答应简洁准确，可适当补充天文学常识。",
        "fallback_response": "请基于以上知识检索结果回答问题。如果知识库中没有相关信息，请说'知识库中暂无相关信息'，然后你可以基于你的常识补充说明。",
        "temperature": 0.7,
        "top_p": 0.9,
        "style_preset": "default",
        "max_tokens": 2048,
        "history_limit": 10
    },
    "advanced": {
        "crawler_delay": 2.5,
        "crawler_timeout": 30,
        "crawler_concurrency": 1,
        "flask_port": 5001,
        "auto_open_browser": True,
        "auto_check_services": True,
        "save_chat_log": False,
        "chat_log_dir": "",
        "log_level": "INFO",
        "neo4j_search_limit": 20,
        "chroma_search_limit": 5
    }
}


class SettingsManager:
    """设置管理器（单例）"""
    DEFAULT_SETTINGS = DEFAULT_SETTINGS
    PRIVATE_SETTINGS_FILENAME = "settings.local.json"
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
        self._settings_path = None
        self._private_settings_path = None
        self._data = {}

    @property
    def settings_path(self) -> str:
        if self._settings_path is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            self._settings_path = os.path.join(base_dir, "settings.json")
        return self._settings_path

    @property
    def private_settings_path(self) -> str:
        if self._private_settings_path is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            self._private_settings_path = os.path.join(base_dir, self.PRIVATE_SETTINGS_FILENAME)
        return self._private_settings_path

    def load(self) -> dict:
        """加载 settings.json，不存在时创建默认文件"""
        if os.path.exists(self.settings_path):
            try:
                with open(self.settings_path, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
                # 合并默认值（确保新版本新增的字段不会缺失）
                self._data = self._deep_merge(DEFAULT_SETTINGS, self._data)
                self._data = self._deep_merge(self._data, self._load_private_settings())
                self._apply_environment_overrides(self._data)
                return self._data
            except Exception:
                pass
        # 文件不存在或解析失败，创建默认配置
        self._data = dict(DEFAULT_SETTINGS)
        self._data = self._deep_merge(self._data, self._load_private_settings())
        self._apply_environment_overrides(self._data)
        self.save()
        return self._data

    def save(self, data: dict = None):
        """保存设置到文件"""
        if data is not None:
            self._data = data
        public_data, private_data = self._split_private_settings(self._data)
        # 确保目录存在
        os.makedirs(os.path.dirname(self.settings_path), exist_ok=True)
        with open(self.settings_path, "w", encoding="utf-8") as f:
            json.dump(public_data, f, ensure_ascii=False, indent=2)
        if private_data:
            with open(self.private_settings_path, "w", encoding="utf-8") as f:
                json.dump(private_data, f, ensure_ascii=False, indent=2)

    def get(self, *keys, default=None):
        """深层获取值，如 get('connect', 'neo4j_uri')"""
        val = self._data
        for k in keys:
            if isinstance(val, dict):
                val = val.get(k)
                if val is None:
                    return default
            else:
                return default
        return val if val is not None else default

    def set(self, *args):
        """设置值：set('connect', 'neo4j_uri', 'bolt://...') 或 set(key1, key2, value)"""
        if len(args) < 2:
            return
        *keys, value = args
        d = self._data
        for k in keys[:-1]:
            if k not in d or not isinstance(d[k], dict):
                d[k] = {}
            d = d[k]
        d[keys[-1]] = value

    def get_all(self) -> dict:
        """获取完整设置字典"""
        if not self._data:
            self.load()
        return dict(self._data)

    def reset_to_defaults(self):
        """重置为默认值"""
        self._data = dict(DEFAULT_SETTINGS)
        self.save()

    @staticmethod
    def _deep_merge(default, custom):
        """递归合并，确保默认值填充分支"""
        result = dict(default)
        for k, v in custom.items():
            if k in result and isinstance(result[k], dict) and isinstance(v, dict):
                result[k] = SettingsManager._deep_merge(result[k], v)
            else:
                result[k] = v
        return result

    def _load_private_settings(self) -> dict:
        try:
            if os.path.exists(self.private_settings_path):
                with open(self.private_settings_path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            return {}
        return {}

    @staticmethod
    def _resolve_env_reference(value, env_names):
        text = str(value or "").strip()
        if text.startswith("${") and text.endswith("}"):
            return os.getenv(text[2:-1], "")
        for env_name in env_names:
            env_value = os.getenv(env_name)
            if env_value:
                return env_value
        return value

    def _apply_environment_overrides(self, data: dict) -> None:
        connect = data.setdefault("connect", {})
        llm_source = data.setdefault("llm_source", {})
        connect["neo4j_uri"] = os.getenv("NEO4J_URI", connect.get("neo4j_uri", "bolt://127.0.0.1:7687"))
        connect["neo4j_user"] = os.getenv("NEO4J_USER", connect.get("neo4j_user", "neo4j"))
        connect["neo4j_password"] = self._resolve_env_reference(
            connect.get("neo4j_password", ""),
            ("NEO4J_PASSWORD",),
        )
        llm_source["api_key"] = self._resolve_env_reference(
            llm_source.get("api_key", ""),
            ("TOLOLO_REMOTE_API_KEY", "DEEPSEEK_API_KEY", "OPENAI_API_KEY"),
        )

    @staticmethod
    def _is_env_reference(value) -> bool:
        text = str(value or "").strip()
        return text.startswith("${") and text.endswith("}")

    def _split_private_settings(self, data: dict):
        public_data = json.loads(json.dumps(data, ensure_ascii=False))
        private_data = {}
        connect = public_data.setdefault("connect", {})
        llm_source = public_data.setdefault("llm_source", {})

        neo4j_password = str(connect.get("neo4j_password", "") or "").strip()
        if neo4j_password and not self._is_env_reference(neo4j_password):
            private_data.setdefault("connect", {})["neo4j_password"] = neo4j_password
            connect["neo4j_password"] = "${NEO4J_PASSWORD}"

        api_key = str(llm_source.get("api_key", "") or "").strip()
        if api_key and not self._is_env_reference(api_key):
            private_data.setdefault("llm_source", {})["api_key"] = api_key
            llm_source["api_key"] = "${TOLOLO_REMOTE_API_KEY}"

        return public_data, private_data

    def to_config_dict(self) -> dict:
        """转换为类似 config.py 的扁平字典（给旧代码兼容用）"""
        data = self._data
        return {
            "NEO4J_URI": data.get("connect", {}).get("neo4j_uri", "bolt://127.0.0.1:7687"),
            "NEO4J_USER": data.get("connect", {}).get("neo4j_user", "neo4j"),
            "NEO4J_PASSWORD": data.get("connect", {}).get("neo4j_password", ""),
            "OLLAMA_BASE_URL": data.get("connect", {}).get("ollama_url", "http://localhost:11434"),
            "OLLAMA_MODEL": data.get("connect", {}).get("ollama_model", "qwen3:4b"),
            "OLLAMA_TIMEOUT": data.get("connect", {}).get("ollama_timeout", 60),
            "FLASK_PORT": data.get("advanced", {}).get("flask_port", 5001),
            "CRAWLER_DELAY": data.get("advanced", {}).get("crawler_delay", 2.5),
            "CRAWLER_TIMEOUT": data.get("advanced", {}).get("crawler_timeout", 30),
            "USE_REMOTE_API": data.get("llm_source", {}).get("use_remote_api", False),
            "API_BASE": data.get("llm_source", {}).get("api_base", ""),
            "REMOTE_MODEL": data.get("llm_source", {}).get("remote_model", "deepseek-v4-flash"),
            "API_KEY": data.get("llm_source", {}).get("api_key", ""),
            "TEMPERATURE": data.get("agent", {}).get("temperature", 0.7),
            "TOP_P": data.get("agent", {}).get("top_p", 0.9),
            "MAX_TOKENS": data.get("agent", {}).get("max_tokens", 2048),
        }
