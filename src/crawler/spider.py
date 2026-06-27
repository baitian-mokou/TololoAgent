"""
爬虫核心 - 爬取维基百科太阳系页面 HTML DOM + 原始文本
保存 html（结构化）与 raw_text（字数校验/兼容），预处理由 preprocess.py 完成
"""
import requests
import json
import time
import os
import re
from bs4 import BeautifulSoup
from urllib.parse import unquote
from config import ACTIVE_SOURCE, RAW_JSON_DIR, CRAWLER_USER_AGENT, CRAWLER_DELAY, CRAWLER_TIMEOUT
from src.source_control import ORIGIN_INTERNAL_LINK, SOURCE_ROLE, normalize_origin


class TololoCrawler:
    """太阳系知识图谱爬虫 - HTML全文爬取"""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": f"{CRAWLER_USER_AGENT} (TololoAgent/1.0; academic project)"
        })
        self.base_url = "https://zh.wikipedia.org"
        self.api_url = f"{self.base_url}/w/api.php"
        self.raw_dir = RAW_JSON_DIR
        os.makedirs(self.raw_dir, exist_ok=True)
        self.last_fetch_source = None
        self.last_fetch_error = None
        self.last_attempted_api = False
        self.last_attempted_html_fallback = False
        self.last_fetch_status = None
        self.last_fetch_attempt_errors = {"api": None, "html": None}

        # 断点续爬：读取已有 _html.json
        self.crawled_titles = self._get_crawled_titles()
        self.progress_callback = None  # func(current, total, message)

        # 统计
        self.new_count = 0
        self.skipped_count = 0
        self.error_count = 0

        # 天文关键词（用于链接过滤）
        self.astronomy_keywords = [
            '星', '太阳', '行星', '卫星', '轨道', '天文', '宇宙', '恒星',
            '彗星', '小行星', '银河', '星系', '星际', '天体', '磁场',
            '大气层', '地质', '探测', '飞船', '航天', '望远镜', '空间站',
            '引力', '速度', '单位', '定律', '辐射', '粒子', '物质',
            '水星','金星','地球','火星','木星','土星','天王星','海王星',
            '冥王星','谷神星','阋神星','鸟神星','妊神星',
            '月球','月亮','太阳系',
            '阿波罗','旅行者','卡西尼','新视野','嫦娥','哈勃','火星车','玉兔',
        ]

        # 排除的页面类型
        self.exclude_patterns = [
            r'^Help:', r'^Wikipedia:', r'^Template:', r'^Category:',
            r'^Portal:', r'^Special:', r'^Talk:', r'^File:', r'^Module:',
            r'^MediaWiki:', r'^Book:', r'^Draft:', r'^TimedText:',
            r'^讨论:', r'^用户:', r'^维基百科:', r'^帮助:', r'^模板:',
            r'^文件:', r'^分类:', r'^主题:', r'^MediaWiki:',
        ]

        # 种子页面
        self.seed_pages = [
            {"title": "太阳", "category": "Star"},
            {"title": "太阳系", "category": "System"},
            {"title": "水星", "category": "Planet"},
            {"title": "金星", "category": "Planet"},
            {"title": "地球", "category": "Planet"},
            {"title": "火星", "category": "Planet"},
            {"title": "木星", "category": "Planet"},
            {"title": "土星", "category": "Planet"},
            {"title": "天王星", "category": "Planet"},
            {"title": "海王星", "category": "Planet"},
            {"title": "冥王星", "category": "DwarfPlanet"},
            {"title": "谷神星", "category": "DwarfPlanet"},
            {"title": "阋神星", "category": "DwarfPlanet"},
            {"title": "鸟神星", "category": "DwarfPlanet"},
            {"title": "妊神星", "category": "DwarfPlanet"},
            {"title": "月球", "category": "Satellite"},
            {"title": "火卫一", "category": "Satellite"},
            {"title": "火卫二", "category": "Satellite"},
            {"title": "木卫一", "category": "Satellite"},
            {"title": "木卫二", "category": "Satellite"},
            {"title": "木卫三", "category": "Satellite"},
            {"title": "木卫四", "category": "Satellite"},
            {"title": "土卫六", "category": "Satellite"},
            {"title": "土卫五", "category": "Satellite"},
            {"title": "土卫四", "category": "Satellite"},
            {"title": "土卫三", "category": "Satellite"},
            {"title": "土卫二", "category": "Satellite"},
            {"title": "土卫一", "category": "Satellite"},
            {"title": "土卫七", "category": "Satellite"},
            {"title": "土卫八", "category": "Satellite"},
            {"title": "天卫三", "category": "Satellite"},
            {"title": "天卫四", "category": "Satellite"},
            {"title": "天卫二", "category": "Satellite"},
            {"title": "天卫一", "category": "Satellite"},
            {"title": "天卫五", "category": "Satellite"},
            {"title": "海卫一", "category": "Satellite"},
            {"title": "冥卫一", "category": "Satellite"},
            {"title": "小行星", "category": "Asteroid"},
            {"title": "彗星", "category": "Comet"},
            {"title": "哈雷彗星", "category": "Comet"},
            {"title": "行星轨道", "category": "Concept"},
            {"title": "开普勒定律", "category": "Concept"},
            {"title": "轨道离心率", "category": "Concept"},
            {"title": "小行星带", "category": "Concept"},
            {"title": "柯伊伯带", "category": "Concept"},
            {"title": "奥尔特云", "category": "Concept"},
            {"title": "行星环", "category": "Concept"},
            {"title": "天体磁场", "category": "Concept"},
            {"title": "行星大气层", "category": "Concept"},
            {"title": "太阳系形成与演化假说", "category": "Concept"},
            {"title": "行星适居性", "category": "Concept"},
            {"title": "近地天体", "category": "Concept"},
            {"title": "阿波罗计划", "category": "Mission"},
            {"title": "旅行者计划", "category": "Mission"},
            {"title": "卡西尼-惠更斯号", "category": "Mission"},
            {"title": "新视野号", "category": "Mission"},
            {"title": "火星探测", "category": "Mission"},
            {"title": "嫦娥工程", "category": "Mission"},
            {"title": "哈勃空间望远镜", "category": "Mission"},
            {"title": "火星车", "category": "Mission"},
            {"title": "类地行星", "category": "Concept"},
            {"title": "气态巨行星", "category": "Concept"},
            {"title": "冰巨星", "category": "Concept"},
            {"title": "系外行星", "category": "Concept"},
            {"title": "日球层", "category": "Concept"},
            {"title": "太阳风", "category": "Concept"},
            {"title": "宇宙速度", "category": "Concept"},
            {"title": "万有引力定律", "category": "Concept"},
            {"title": "天文单位", "category": "Concept"},
            {"title": "光年", "category": "Concept"},
            {"title": "银河系", "category": "Concept"},
        ]

    def set_progress_callback(self, callback):
        """设置进度回调函数 callback(current, total, message)"""
        self.progress_callback = callback

    def _report(self, msg):
        if self.progress_callback:
            self.progress_callback(0, 0, msg)

    def _report_progress(self, current, total, msg):
        if self.progress_callback:
            self.progress_callback(current, total, msg)

    @staticmethod
    def sanitize_filename(name):
        """清洗文件名：去除半角+全角非法字符"""
        name = re.sub(r'[\\/:*?"<>|？！：；，。、【】「」『』《》（）→←↑↓"\'’‘̥]', '_', name)
        return name

    def _get_crawled_titles(self):
        """读取已有json/htm_json的标题（断点续爬）"""
        titles = set()
        if not os.path.exists(self.raw_dir):
            return titles
        for fname in os.listdir(self.raw_dir):
            if fname.endswith('.json'):
                # 兼容 _html.json 和 .json 两种格式
                raw_name = fname.replace('_html.json', '').replace('.json', '')
                decoded = unquote(raw_name)
                # 使用与 crawl_html_page 完全一致的 sanitize_filename
                safe_key = self.sanitize_filename(decoded)
                titles.add(safe_key)
        return titles

    @staticmethod
    def _remove_noise_tags(soup):
        """移除页面中的导航、参考、分类等噪音元素"""
        for selector in [
            {'class_': 'navbox'},
            {'class_': 'navbox-styles'},
            {'class_': 'reflist'},
            {'class_': 'references'},
            {'id_': 'catlinks'},
            {'id_': 'mw-navigation'},
            {'class_': 'portal'},
            {'class_': 'sisterlinks'},
            {'class_': 'mbox-small'},
            {'id_': 'toc'},
            {'class_': 'noprint'},
            {'class_': 'metadata'},
            {'class_': 'mw-jump-link'},
        ]:
            for tag in soup.find_all('div', **selector):
                tag.decompose()
        # 移除 <ol class="references">
        for tag in soup.find_all('ol', class_='references'):
            tag.decompose()
        return soup

    @staticmethod
    def _truncate_at_references(text):
        """在"参考资料"/"参考文献"处截断"""
        markers = ['参考资料', '参考文献', '外部链接', '參見', '参见']
        lines = text.split('\n')
        cut = len(lines)
        for i, line in enumerate(lines):
            for m in markers:
                if line.strip().startswith('=== ' + m) or line.strip().startswith('== ' + m):
                    cut = i
                    break
            if cut < len(lines):
                break
        return '\n'.join(lines[:cut])

    @staticmethod
    def _extract_raw_text_from_dom(content_div):
        """
        从正文 DOM 中提取兼容用 raw_text。

        注意：结构化处理不依赖该字段，真实语义输入是 html。
        这里刻意不调用 content_div.get_text()，避免把 DOM 结构误当作
        后续 NLP 的唯一输入。
        """
        lines = []
        for text in content_div.stripped_strings:
            line = re.sub(r'\s+', ' ', str(text)).strip()
            if line:
                lines.append(line)
        return '\n'.join(lines)

    def _postprocess_html_fragment(self, html_fragment):
        soup = BeautifulSoup(html_fragment, 'lxml')
        content_div = soup.find('div') or soup
        self._remove_noise_tags(content_div)
        html_content = content_div.prettify()
        raw_text = self._extract_raw_text_from_dom(content_div)
        raw_text = self._truncate_at_references(raw_text)
        lines = [l.strip() for l in raw_text.split('\n') if l.strip() and len(l.strip()) > 3]
        lines = [l for l in lines if not (len(l) > 120 and l.count('、') > 5)]
        raw_text = '\n\n'.join(lines)
        cn_chars = len(re.findall(r'[\u4e00-\u9fff]', raw_text))
        if cn_chars < 100:
            return None
        return {
            'html': html_content,
            'raw_text': raw_text,
            'word_count_cn': cn_chars,
        }

    def get_api_content(self, title):
        """优先通过 MediaWiki API 获取正文 HTML。"""
        self.last_attempted_api = True
        self.last_fetch_attempt_errors["api"] = None
        try:
            resp = self.session.get(
                self.api_url,
                params={
                    'action': 'parse',
                    'page': title,
                    'prop': 'text',
                    'redirects': 1,
                    'format': 'json',
                    'formatversion': 2,
                },
                timeout=CRAWLER_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
            html_fragment = ((data.get('parse') or {}).get('text') or '').strip()
            if not html_fragment:
                return None
            parsed = self._postprocess_html_fragment(html_fragment)
            if not parsed:
                self.last_fetch_attempt_errors["api"] = "MediaWiki API returned content, but postprocess rejected it"
                return None
            parsed['fetch_source'] = 'mediawiki_api'
            parsed['origin'] = normalize_origin('mediawiki_api')
            return parsed
        except requests.exceptions.RequestException as e:
            self.last_fetch_attempt_errors["api"] = f"MediaWiki API request failed: {e}"
            self._report(f"  [API失败] '{title}': {e}")
            return None
        except (ValueError, TypeError) as e:
            self.last_fetch_attempt_errors["api"] = f"MediaWiki API parse failed: {e}"
            self._report(f"  [API解析失败] '{title}': {e}")
            return None

    def get_html_content(self, title):
        """
        HTML 抓取 fallback：爬取维基百科正文区域，保留 HTML DOM 结构。

        Returns:
            dict: {html, raw_text} 或 None
        """
        url = f"{self.base_url}/wiki/{title}"
        self.last_attempted_html_fallback = True
        self.last_fetch_attempt_errors["html"] = None

        try:
            resp = self.session.get(url, timeout=CRAWLER_TIMEOUT)
            resp.raise_for_status()
            resp.encoding = 'utf-8'

            soup = BeautifulSoup(resp.text, 'lxml')
            content_div = soup.find('div', {'id': 'mw-content-text'})
            if not content_div:
                content_div = soup.find('div', {'class': 'mw-parser-output'})
            if not content_div:
                self._report(f"  [错误] '{title}' 无法找到正文区域")
                self.last_fetch_attempt_errors["html"] = "HTML fallback could not locate article content"
                return None

            parsed = self._postprocess_html_fragment(content_div.prettify())
            if not parsed:
                self.last_fetch_attempt_errors["html"] = "HTML fallback returned content, but postprocess rejected it"
                self._report(f"  [跳过] '{title}' 中文内容不足")
                return None
            parsed['fetch_source'] = 'html_dom'
            parsed['origin'] = normalize_origin('html_dom')
            return parsed

        except requests.exceptions.RequestException as e:
            self.last_fetch_attempt_errors["html"] = f"HTML fallback request failed: {e}"
            self._report(f"  [错误] '{title}': {e}")
            return None

    def _compose_final_fetch_error(self):
        parts = []
        if self.last_fetch_attempt_errors.get("api"):
            parts.append(self.last_fetch_attempt_errors["api"])
        if self.last_fetch_attempt_errors.get("html"):
            parts.append(self.last_fetch_attempt_errors["html"])
        return " | ".join(parts) if parts else None

    def get_page_content(self, title):
        """active path: 先走 MediaWiki API，失败后回退 HTML。"""
        self.last_fetch_source = None
        self.last_fetch_error = None
        self.last_attempted_api = False
        self.last_attempted_html_fallback = False
        self.last_fetch_status = None
        self.last_fetch_attempt_errors = {"api": None, "html": None}
        api_content = self.get_api_content(title)
        if api_content:
            self.last_fetch_source = 'mediawiki_api'
            self.last_fetch_status = 'success'
            return api_content
        html_content = self.get_html_content(title)
        if html_content:
            self.last_fetch_source = 'html_dom'
            self.last_fetch_status = 'success'
            self.last_fetch_error = None
            return html_content
        self.last_fetch_status = 'failed'
        self.last_fetch_error = self._compose_final_fetch_error()
        return None

    def crawl_html_page(self, title, category="Auto"):
        """爬取单页HTML全文并保存"""
        # 生成safe_key用于断点续爬
        safe_key = self.sanitize_filename(title)
        if safe_key in self.crawled_titles:
            self._report(f"  [跳过] '{title}' 已爬取过")
            self.skipped_count += 1
            return None

        content = self.get_page_content(title)
        if not content:
            self.error_count += 1
            return None

        html_content = content['html']
        raw_text = content['raw_text']
        cn_chars = content.get('word_count_cn', len(re.findall(r'[\u4e00-\u9fff]', raw_text)))
        fetch_source = content.get("fetch_source", "html_dom")
        fetch_origin = normalize_origin(content.get("origin") or fetch_source)
        discovery_origin = ORIGIN_INTERNAL_LINK if category == "Auto" else "seed"
        result = {
            "title": title,
            "category": category,
            "url": f"{self.base_url}/wiki/{title}",
            "html": html_content,
            "raw_text": raw_text,
            "content_length": len(raw_text),
            "word_count_cn": cn_chars,
            "char_count": len(raw_text),
            "text": raw_text,
            "source": ACTIVE_SOURCE,
            "source_role": SOURCE_ROLE,
            "origin": fetch_origin,
            "fetch_source": fetch_source,
            "discovery_origin": discovery_origin,
            "crawl_time": time.strftime("%Y-%m-%d %H:%M:%S")
        }

        safe_title = self.sanitize_filename(title)
        filepath = os.path.join(self.raw_dir, f"{safe_title}_html.json")
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        self.crawled_titles.add(safe_key)
        self.new_count += 1
        self._report(
            f"  [成功] '{title}' {cn_chars}中文字，"
            f"source={result['source']}，origin={result['origin']}"
        )
        return result

    def _filter_discovered_title(self, clean_title, href=""):
        if any(re.match(p, clean_title) for p in self.exclude_patterns):
            return False
        if len(clean_title) < 2 or len(clean_title) > 50:
            return False
        if '%' in clean_title:
            return False
        if any(kw in clean_title for kw in self.astronomy_keywords):
            return True
        return any(kw in href.lower() for kw in ['solar_system', 'planet', 'moon', 'asteroid', 'comet', 'orbit'])

    def _extract_links_via_api(self):
        try:
            resp = self.session.get(
                self.api_url,
                params={
                    'action': 'parse',
                    'page': '太阳系',
                    'prop': 'links',
                    'redirects': 1,
                    'format': 'json',
                    'formatversion': 2,
                },
                timeout=CRAWLER_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
            links = set()
            for item in (data.get('parse') or {}).get('links', []) or []:
                clean_title = item.get('*', '')
                if self._filter_discovered_title(clean_title):
                    links.add(clean_title)
            return sorted(links)
        except Exception as e:
            self._report(f"[API链接失败] {e}")
            return []

    def extract_links_from_entry(self):
        """从"太阳系"入口页面提取所有天文相关链接。"""
        api_links = self._extract_links_via_api()
        if api_links:
            self._report(f"[链接发现] 通过 MediaWiki API 提取到 {len(api_links)} 个链接")
            return api_links

        entry_url = f"{self.base_url}/wiki/太阳系"
        self._report(f"[链接发现] 正在解析入口页面: 太阳系")

        try:
            resp = self.session.get(entry_url, timeout=CRAWLER_TIMEOUT)
            resp.raise_for_status()
            resp.encoding = 'utf-8'
        except Exception as e:
            self._report(f"[错误] 无法访问入口页面: {e}")
            return []

        soup = BeautifulSoup(resp.text, 'lxml')
        content_div = soup.find('div', {'id': 'mw-content-text'})
        if not content_div:
            content_div = soup.find('div', {'class': 'mw-parser-output'})
        if not content_div:
            self._report("[错误] 无法找到入口页面的正文区域")
            return []

        links = set()
        for a_tag in content_div.find_all('a', href=True):
            href = a_tag['href']
            title = a_tag.get('title', '')

            if not href.startswith('/wiki/'):
                continue

            clean_title = href.replace('/wiki/', '')
            clean_title = unquote(clean_title)

            if self._filter_discovered_title(clean_title, href):
                links.add(clean_title)

        result = sorted(links)
        self._report(f"[链接发现] 提取到 {len(result)} 个天文相关链接")
        return result

    def crawl_seed_pages(self):
        """阶段一：爬取所有种子页面的HTML全文"""
        total = len(self.seed_pages)
        self._report(f"\n{'='*50}")
        self._report(f"[阶段一] 爬取 {total} 个种子页面的HTML全文")
        self._report(f"{'='*50}")

        success = 0
        for i, page in enumerate(self.seed_pages):
            self._report_progress(i + 1, total, f"[{i+1}/{total}] {page['title']}")
            result = self.crawl_html_page(page['title'], page['category'])
            if result:
                success += 1
                time.sleep(CRAWLER_DELAY * 3)  # 新爬取才等待，防429
            # 已跳过或失败的页面不等，直接继续

        self._report(f"[阶段一完成] 种子页面: 新增{success}个, 跳过{self.skipped_count}个")
        return success

    def crawl_discovered_links(self, delay=20):
        """阶段二：自动发现链接并爬取"""
        self._report(f"\n{'='*50}")
        self._report(f"[阶段二] 自动发现链接并爬取HTML全文")
        self._report(f"{'='*50}")

        all_links = self.extract_links_from_entry()
        if not all_links:
            self._report("[阶段二] 未发现新链接")
            return 0

        # 只保留未爬取的
        to_crawl = []
        for link in all_links:
            safe_key = self.sanitize_filename(link)
            if safe_key not in self.crawled_titles:
                to_crawl.append(link)

        total = len(to_crawl)
        self._report(f"[阶段二] 待爬取: {total} 个新链接（共{len(all_links)}个发现）")

        success = 0
        for i, title in enumerate(to_crawl):
            self._report_progress(i + 1, total, f"[{i+1}/{total}] {title}")
            result = self.crawl_html_page(title, "Auto")

            if result:
                success += 1
                time.sleep(delay)  # 新爬取等20秒，防429
            # 失败的页面不等，直接继续

        self._report(f"[阶段二完成] 新增{success}个, 失败{self.error_count}个")
        return success

    def crawl_all(self):
        """完整爬取流程：种子页面 + 链接发现"""
        self.new_count = 0
        self.skipped_count = 0
        self.error_count = 0

        self._report(f"[爬虫启动] data/raw_json/ 已有 {len(self.crawled_titles)} 个HTML页面")

        # 阶段一：种子页面
        s1 = self.crawl_seed_pages()

        # 阶段二：链接发现
        s2 = self.crawl_discovered_links(delay=20)

        total_new = s1 + s2
        self._report(f"\n{'='*50}")
        self._report(f"[爬虫完成] 新增{total_new}个, 跳过{self.skipped_count}个, 失败{self.error_count}个")
        self._report(f"[爬虫完成] 总计 {len(self.crawled_titles)} 个HTML全文页面")
        self._report(f"{'='*50}")
        return total_new, len(self.crawled_titles)
