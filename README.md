# TololoAgent

> 课程展示项目 / Course project demo  
> 作者 / Author: `baitianmeihong`  
> 用途 / Usage: 仅课程展示与学习交流。Not intended for production deployment.

TololoAgent 是一个面向太阳系天文学知识的本地知识图谱问答系统。项目把中文维基、Wikidata、NASA、ESA 等来源的天文知识整理为结构化三元组和叙事文本，再结合 Neo4j、Chroma、Ollama/远程大模型，实现可解释的中文自然语言问答、多源融合和多跳推理。

TololoAgent is a local knowledge-graph QA system for Solar System astronomy. It converts astronomy data from Chinese Wikipedia, Wikidata, NASA and ESA into triples and narrative chunks, stores them in Neo4j and Chroma, and answers Chinese natural-language questions with graph retrieval, vector retrieval, source fusion and multi-hop reasoning.

---

## 目录 / Table of Contents

- [项目亮点](#项目亮点--highlights)
- [功能概览](#功能概览--features)
- [系统架构](#系统架构--architecture)
- [目录结构](#目录结构--project-layout)
- [环境要求](#环境要求--requirements)
- [快速开始](#快速开始--quick-start)
- [本地模型安装](#本地模型安装--local-llm-installation)
- [Neo4j 配置](#neo4j-配置--neo4j-configuration)
- [数据与知识表示](#数据与知识表示--data-and-knowledge-representation)
- [NLP 处理流程](#nlp-处理流程--nlp-pipeline)
- [问答与多跳推理](#问答与多跳推理--qa-and-multi-hop-reasoning)
- [图谱可视化](#图谱可视化--graph-visualization)
- [测试与评估](#测试与评估--tests-and-evaluation)
- [安全与隐私](#安全与隐私--security-and-privacy)
- [English Overview](#english-overview)

---

## 项目亮点 / Highlights

- **知识图谱驱动问答**：用 Neo4j 存储天体、系统、参数、发现者、大气等结构化关系。
- **多源数据接入**：支持中文维基、Wikidata、NASA、ESA 的采集、物化和影子命名空间。
- **向量检索补充上下文**：Chroma 存储叙事文本，用于解释型回答。
- **多跳推理**：支持“卫星 -> 宿主行星 -> 参数/类型/大气”等链式查询。
- **多源融合与质量审查**：对不同来源的数值、实体、关系进行归一化、冲突识别和审查。
- **本地/联网模型切换**：可用 Ollama 本地 `qwen3:4b`，也可配置远程 OpenAI-compatible API。
- **桌面 GUI**：提供爬取、NLP、数据库、质量审查、可视化、问答等页面。
- **课程展示友好**：包含一键启动脚本和一键下载本地模型脚本。

---

## 功能概览 / Features

### 1. 数据采集

- 爬取或读取天文页面。
- 保存原始 HTML/JSON。
- 支持多来源数据适配。

### 2. NLP 抽取

- 使用 BeautifulSoup 解析百科 HTML。
- 使用 jieba 做中文分词、查询解析和关键词提取。
- 从 infobox、正文、章节中抽取三元组。
- 对三元组进行 ontology 校验和噪声过滤。

### 3. 知识存储

- Neo4j：存储实体节点和关系边。
- Chroma：存储叙事文本向量。
- 本地 JSON：保存 triples、narratives、raw data、评估报告。

### 4. 问答 Agent

- 解析自然语言问题。
- 检索 Neo4j 图谱和 Chroma 文本。
- 支持本地 Ollama 和远程 API。
- 输出中文回答，并尽量基于检索证据。

### 5. 多跳推理

示例：

```text
问题：火卫一绕行的行星质量是多少？
推理：火卫一 ORBITS 火星；火星 HAS_MASS 6.4169 × 10 23 kg
答案：火星质量为 6.4169 × 10 23 kg
```

```text
问题：月亮所属行星的直径与质量
推理：月亮 -> 月球；月球 ORBITS 地球；地球 HAS_RADIUS / HAS_MASS
答案：地球直径约 12,742.0 km，质量约 5.97237 × 10 24 kg
```

---

## 系统架构 / Architecture

```mermaid
flowchart LR
    A["Raw Sources<br/>Wikipedia / Wikidata / NASA / ESA"] --> B["Crawler & Source Adapters"]
    B --> C["NLP Pipeline<br/>BeautifulSoup + jieba + rules"]
    C --> D["Triples & Narratives"]
    D --> E["Neo4j Knowledge Graph"]
    D --> F["Chroma Vector Store"]
    G["User Question"] --> H["Query Analyzer"]
    H --> I["Graph Retrieval"]
    H --> J["Vector Retrieval"]
    I --> K["Source Fusion & Multi-hop Reasoning"]
    J --> K
    K --> L["LLM Agent<br/>Ollama / Remote API"]
    L --> M["GUI Answer"]
```

核心链路：

```text
source_adapters / crawler
        -> nlp
        -> knowledge_graph / vector_store
        -> agent
        -> gui / visualization
```

---

## 目录结构 / Project Layout

```text
TololoAgent/
├─ main.py                         # GUI 入口
├─ config.py                       # 全局配置，敏感值优先读环境变量
├─ settings.json                   # 可公开设置，使用环境变量占位
├─ settings.local.example.json     # 本地私密配置示例
├─ 启动托洛洛GUI.bat               # Windows 一键启动 GUI
├─ 一键下载安装Qwen3-4B本地模型.bat # 下载 Ollama 本地 qwen3:4b
├─ src/
│  ├─ agent/                       # 问答 Agent、检索、多跳推理
│  ├─ crawler/                     # 页面爬取
│  ├─ gui/                         # Tkinter 桌面界面
│  ├─ knowledge_graph/             # Neo4j 导入与查询
│  ├─ nlp/                         # HTML 解析、分词、抽取、ontology
│  ├─ source_adapters/             # NASA / Wikidata / ESA 适配器
│  ├─ source_quality/              # 多源融合、值归一化、质量审查
│  ├─ vector_store/                # Chroma 向量检索
│  └─ visualization/               # Flask + D3 图谱可视化
├─ data/                           # 原始数据、三元组、叙事文本、审查数据
├─ docs/                           # 设计文档和报告
├─ evaluation/                     # 评估结果、多跳问题集
├─ scripts/                        # 数据构建、导入、评估、修复脚本
├─ tests/                          # 单元测试和回归测试
└─ tools/                          # 辅助工具
```

本仓库不应提交：

- `venv/`
- `models/`
- `settings.local.json`
- API key、Neo4j 本地密码、Ollama 模型文件

---

## 环境要求 / Requirements

- Windows 10/11
- Python 3.10+
- Neo4j Desktop 或 Neo4j Server
- Ollama（用于本地模型）
- Git

Python 依赖见：

```text
requirements.txt
```

安装依赖：

```powershell
pip install -r requirements.txt
```

---

## 快速开始 / Quick Start

### 1. 克隆项目

```powershell
git clone https://github.com/baitian-mokou/TololoAgent.git
cd TololoAgent
```

### 2. 安装 Python 依赖

```powershell
pip install -r requirements.txt
```

### 3. 配置 Neo4j 密码

推荐用环境变量，不要把真实密码写进 Git：

```powershell
$env:NEO4J_PASSWORD="你的 Neo4j 密码"
```

如果要长期保存，请在系统环境变量中配置 `NEO4J_PASSWORD`。

### 4. 下载本地大模型

双击运行：

```text
一键下载安装Qwen3-4B本地模型.bat
```

该脚本会安装/检查 Ollama，并执行：

```powershell
ollama pull qwen3:4b
```

模型会保存在 Ollama 默认用户目录，不会进入项目文件夹。

### 5. 启动项目

双击运行：

```text
启动托洛洛GUI.bat
```

或命令行运行：

```powershell
python main.py
```

---

## 本地模型安装 / Local LLM Installation

本项目默认使用：

```text
qwen3:4b
```

如果脚本失败，可以手动执行：

```powershell
ollama serve
ollama pull qwen3:4b
```

检查模型：

```powershell
ollama list
```

注意：不要把 Ollama 模型目录放进项目中。`.gitignore` 已忽略 `models/`。

---

## Neo4j 配置 / Neo4j Configuration

默认连接：

```text
URI: bolt://127.0.0.1:7687
User: neo4j
Password: from NEO4J_PASSWORD
```

环境变量：

```powershell
$env:NEO4J_URI="bolt://127.0.0.1:7687"
$env:NEO4J_USER="neo4j"
$env:NEO4J_PASSWORD="你的密码"
```

常用 Cypher 查询：

```cypher
MATCH (j {name: '木星'})-[r]-(m)
RETURN j.name AS subject, type(r) AS relation, m.name AS object
LIMIT 50;
```

查询木星卫星：

```cypher
MATCH (moon)-[:ORBITS]->(j {name: '木星'})
RETURN moon.name AS satellite, j.name AS planet
ORDER BY satellite;
```

查询多跳：

```cypher
MATCH (moon {name: '木卫一'})-[:ORBITS]->(planet)-[:HAS_MASS]->(mass)
RETURN moon.name AS moon, planet.name AS planet, mass.name AS mass;
```

---

## 数据与知识表示 / Data and Knowledge Representation

系统主要使用三元组表示知识：

```text
subject - relation - object
```

示例：

```text
火卫一 - ORBITS - 火星
火星 - HAS_MASS - 6.4169 × 10 23 kg
木卫二 - PART_OF - 伽利略卫星
伽利略卫星 - IS_A - 天然卫星群
冥王星 - HAS_ATMOSPHERE - 甲烷
```

支持的核心关系：

| Relation | 中文含义 | Example |
|---|---|---|
| `IS_A` | 类型 | `火星 IS_A 沙漠行星` |
| `PART_OF` | 属于 | `木卫一 PART_OF 伽利略卫星` |
| `ORBITS` | 绕行 | `月球 ORBITS 地球` |
| `HAS_MASS` | 质量 | `地球 HAS_MASS 5.97237 × 10 24 kg` |
| `HAS_RADIUS` | 半径 | `地球 HAS_RADIUS 6,371.0 km` |
| `HAS_DIAMETER` | 直径派生 | `地球 HAS_DIAMETER 12,742.0 km` |
| `HAS_ATMOSPHERE` | 大气成分 | `木星 HAS_ATMOSPHERE 氢` |
| `DISCOVERED_BY` | 发现者 | `土卫六 DISCOVERED_BY 克里斯蒂安·惠更斯` |
| `LOCATED_IN` | 位于 | `地球 LOCATED_IN 太阳系` |

---

## NLP 处理流程 / NLP Pipeline

NLP 模块位于 `src/nlp/`。

### 使用 BeautifulSoup

`src/nlp/preprocess.py` 使用 BeautifulSoup 解析 HTML：

- 提取 infobox 字段
- 提取页面章节
- 提取正文文本
- 过滤脚注、导航、表格噪声

主要类：

```text
WikiPreprocessor
```

主要函数：

```text
extract_infobox_fields()
extract_infobox()
extract_sections()
segment_sentences()
extract_triples()
```

### 使用 jieba

`src/nlp/query_analyzer.py` 使用 jieba 解析用户问题：

- 分词
- 实体匹配
- 关系意图识别
- 查询上下文构建

主要函数：

```text
build_query_context()
```

示例：

```text
输入：月亮所属行星的直径与质量
输出：
  primary_entity: 月球
  relation_hints: ORBITS, HAS_RADIUS, HAS_MASS
  topic_intents: diameter
```

`src/nlp/narrative_processor.py` 使用 `jieba.analyse.extract_tags()` 提取叙事文本关键词。

### 规则与 ontology 校验

`src/nlp/ontology.py` 负责：

- 关系白名单
- object 标准化
- 三元组合法性检查
- 大气成分拆分
- 噪声过滤

---

## 问答与多跳推理 / QA and Multi-hop Reasoning

核心文件：

```text
src/agent/llm_agent.py
```

主要职责：

- 检测 Ollama/远程模型
- 查询 Neo4j
- 查询 Chroma
- 多源融合
- 多跳推理
- 构造提示词
- 调用 LLM 生成回答

### 已支持的多跳模式

1. 卫星 -> 宿主天体 -> 质量

```text
火卫一 ORBITS 火星
火星 HAS_MASS 6.4169 × 10 23 kg
```

2. 卫星 -> 宿主天体 -> 类型

```text
冥卫一 ORBITS 冥王星
冥王星 IS_A 矮行星
```

3. 卫星 -> 宿主天体 -> 大气

```text
冥卫一 ORBITS 冥王星
冥王星 HAS_ATMOSPHERE 氮 / 甲烷 / 一氧化碳
```

4. 卫星 -> 所属群组 -> 群组属性

```text
木卫二 PART_OF 伽利略卫星
伽利略卫星 IS_A 天然卫星群
```

5. 条件筛选型多跳

```text
哪些属于土星系统的卫星由卡西尼发现？
```

系统会筛选：

```text
PART_OF 土星系统
DISCOVERED_BY 乔瓦尼·多梅尼科·卡西尼
```

6. 直径派生

如果知识库中只有半径，系统会派生直径：

```text
地球 HAS_RADIUS 6,371.0 km
地球 HAS_DIAMETER 12,742.0 km
```

---

## 图谱可视化 / Graph Visualization

核心文件：

```text
src/visualization/app.py
```

功能：

- 从 Neo4j 读取节点和边
- 使用 Flask 提供 `/api/graph`
- 使用 D3.js 展示导向图
- 支持节点筛选、标签筛选、连接数过滤、关系标签显示

启动后默认地址：

```text
http://127.0.0.1:5001
```

---

## 测试与评估 / Tests and Evaluation

运行核心回归测试：

```powershell
python -m unittest tests.test_query_retrieval_and_ollama_fallback tests.test_multi_source_fusion
```

多跳问题集：

```text
evaluation/multi_hop_reasoning_queries.json
```

重要测试文件：

```text
tests/test_query_retrieval_and_ollama_fallback.py
tests/test_multi_source_fusion.py
tests/test_value_normalizer.py
tests/test_neo4j_loader_graph_cleaning.py
tests/test_nasa_fact_sheet_parser.py
```

---

## GitHub 上传说明 / Publishing Notes

推荐上传：

- `src/`
- `scripts/`
- `tests/`
- `docs/`
- `evaluation/`
- `data/`
- `requirements.txt`
- `README.md`
- `.gitignore`
- 一键启动和一键模型安装脚本

不要上传：

- `venv/`
- `models/`
- `settings.local.json`
- API key
- Neo4j 本地密码
- Ollama 模型缓存
- Chroma 本地索引缓存

当前 `.gitignore` 已覆盖这些本地文件。

首次发布可使用：

```powershell
git remote add origin https://github.com/baitian-mokou/TololoAgent.git
git add .
git commit -m "Prepare TololoAgent course project release"
git branch -M main
git push -u origin main
```

如果没有登录 GitHub，请先执行：

```powershell
gh auth login
```

或使用 GitHub Desktop。

---

## 安全与隐私 / Security and Privacy

本项目不会要求把真实 API key 写入 README 或公开配置。

推荐使用环境变量：

```powershell
$env:NEO4J_PASSWORD="your-password"
$env:TOLOLO_REMOTE_API_KEY="your-api-key"
```

`settings.json` 中只应保留占位符：

```json
{
  "connect": {
    "neo4j_password": "${NEO4J_PASSWORD}"
  },
  "llm_source": {
    "api_key": "${TOLOLO_REMOTE_API_KEY}"
  }
}
```

真实值请保存在：

```text
settings.local.json
```

该文件已被 `.gitignore` 忽略。

---

## 常见问题 / FAQ

### Q: 为什么不上传 Ollama 模型？

Ollama 模型体积较大，不适合进入 Git 仓库。本项目提供：

```text
一键下载安装Qwen3-4B本地模型.bat
```

运行后即可获得本地模型。

### Q: 为什么不上传 `venv/`？

虚拟环境与本机平台绑定，体积大且不可移植。请用：

```powershell
pip install -r requirements.txt
```

重建环境。

### Q: Neo4j 查不到结果怎么办？

检查：

1. Neo4j 是否启动。
2. `NEO4J_PASSWORD` 是否正确。
3. 是否已经导入 triples。
4. GUI 设置里的 URI、用户名、密码是否正确。

### Q: 本地模型不可用怎么办？

运行：

```powershell
ollama list
ollama pull qwen3:4b
```

然后重启 GUI。

---

## English Overview

TololoAgent is a course project that demonstrates a local astronomy knowledge-graph QA system. It focuses on Solar System knowledge and combines:

- HTML parsing with BeautifulSoup
- Chinese tokenization and query analysis with jieba
- rule-based triple extraction
- Neo4j graph storage and Cypher queries
- Chroma vector retrieval for narrative context
- Ollama local LLM or remote OpenAI-compatible APIs
- source fusion and multi-hop reasoning
- a Tkinter GUI and a D3.js graph visualization

Typical multi-hop query:

```text
Question: What is the mass of the planet orbited by Phobos?
Reasoning:
  Phobos ORBITS Mars
  Mars HAS_MASS 6.4169 × 10 23 kg
Answer:
  Mars has a mass of 6.4169 × 10 23 kg.
```

Another example:

```text
Question: The diameter and mass of the planet that the Moon belongs to
Reasoning:
  Moon ORBITS Earth
  Earth HAS_RADIUS 6,371.0 km
  Earth HAS_DIAMETER 12,742.0 km
  Earth HAS_MASS 5.97237 × 10 24 kg
```

This repository is for coursework demonstration only. Do not commit private API keys, local Neo4j passwords, virtual environments, or model files.

