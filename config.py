"""
托洛洛Agent 全局配置文件
"""
import os

# 项目根目录
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 数据目录
DATA_DIR = os.path.join(BASE_DIR, "data")
RAW_JSON_DIR = os.path.join(DATA_DIR, "raw_json")
TRIPLES_DIR = os.path.join(DATA_DIR, "triples")

# Source Control
ACTIVE_SOURCE = "zh_wikipedia"
ACTIVE_SOURCE_TEST = "nasa"
SOURCE_REGISTRY = {
    "zh_wikipedia": "active",
    "wikidata": "disabled",
    "nasa": "disabled",
    "esa": "disabled",
}
FORMALLY_INTEGRATED_SOURCES = {
    "wikidata": {
        "formal_status": "formally_integrated_shadow",
        "materialization_status": "graph_embedding_materialized",
        "cutover_ready": False,
        "approval_mode": "owner-approved exception",
        "release_phase": "formal_second_source",
    },
}

# 创建目录
for d in [DATA_DIR, RAW_JSON_DIR, TRIPLES_DIR]:
    os.makedirs(d, exist_ok=True)

# Neo4j 配置
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://127.0.0.1:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "")

# Ollama 配置
OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_MODEL = "qwen3:4b"
OLLAMA_TIMEOUT = 60
OLLAMA_MODELS_DIR = os.getenv("OLLAMA_MODELS", "")

# Flask 可视化服务
FLASK_HOST = "127.0.0.1"
FLASK_PORT = 5001
FLASK_DEBUG = False

# 爬虫配置
CRAWLER_DELAY = 2.5
CRAWLER_TIMEOUT = 30
CRAWLER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

# 数据标准
TARGET_TXT_COUNT = 500
MIN_TXT_CHARS = 2000

# NLP配置
ASTRO_DICT_PATH = os.path.join(DATA_DIR, "astronomy_dict.txt")
TERMS_JSON_PATH = os.path.join(BASE_DIR, "astronomy_terms.json")
