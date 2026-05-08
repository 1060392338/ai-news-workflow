"""知乎搜索器 — RSSHub 抓取热搜 + 搜索"""
import re
import xml.etree.ElementTree as ET
import urllib.parse
from typing import Optional
from infrastructure.http_client import HttpClient
from models.hot_item import SearchResult


class ZhiHuSearcher:
    name = "zhihu"
    RSSHUB = "https://rsshub.app"

    def __init__(self, http: Optional[HttpClient] = None):
        self.http = http or HttpClient()

    def search(self, keywords: list[str], max_results: int = 20) -> list[SearchResult]:
        results = []

        for method in ["_fetch_hotlist", "_fetch_daily"]:
            try:
                items = getattr(self, method)()
                results.extend(items)
            except Exception as e:
                print(f"  [知乎] {method} 失败: {e}")

        for kw in keywords:
            try:
                items = self._search_keyword(kw)
                results.extend(items)
            except Exception as e:
                print(f"  [知乎] 关键词 '{kw}' 失败: {e}")

        # 去重 + 排序
        seen = set()
        unique = []
        for r in results:
            if r.url not in seen:
                seen.add(r.url)
                unique.append(r)
        unique.sort(key=lambda r: r.hot_score, reverse=True)
        return unique[:max_results]

    def _fetch_hotlist(self) -> list[SearchResult]:
        items = self._parse_rss(f"{self.RSSHUB}/zhihu/hotlist")
        for i, item in enumerate(items):
            item.hot_score = max(item.hot_score, 100 - i)
        return items

    def _fetch_daily(self) -> list[SearchResult]:
        return self._parse_rss(f"{self.RSSHUB}/zhihu/daily")

    def _search_keyword(self, kw: str) -> list[SearchResult]:
        encoded = urllib.parse.quote(kw)
        return self._parse_rss(f"{self.RSSHUB}/zhihu/search/{encoded}")

    def _parse_rss(self, url: str) -> list[SearchResult]:
        result = []
        try:
            resp = self.http.get(url)
            root = ET.fromstring(resp.text)
            entries = root.findall(".//{http://www.w3.org/2005/Atom}entry")
            if not entries:
                entries = root.findall(".//item")

            for entry in entries:
                title = entry.findtext("{http://www.w3.org/2005/Atom}title", "") or ""
                link_el = entry.find("{http://www.w3.org/2005/Atom}link")
                href = link_el.get("href", "") if link_el is not None else ""
                summary_el = entry.find("{http://www.w3.org/2005/Atom}summary")
                summary = ""
                if summary_el is not None:
                    summary = re.sub(r"<[^>]+>", "", summary_el.text or "").strip()[:200]

                if title:
                    has_cn = bool(re.search(r"[\u4e00-\u9fff]", title))
                    ai_kw = ["ai", "人工智能", "llm", "大模型", "gpt"]
                    is_ai = any(k in title.lower() for k in ai_kw)
                    result.append(SearchResult(
                        title=title.strip(), url=href, summary=summary,
                        source="zhihu", source_domain="zhihu.com",
                        hot_score=50 if is_ai else 10,
                        language="zh" if has_cn else "en",
                        tags=["zhihu"],
                    ))
        except Exception as e:
            print(f"  [知乎 RSS] 解析失败: {e}")
        return result
