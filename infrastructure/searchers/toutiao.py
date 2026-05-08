"""头条热点搜索器 — 抓取头条热搜榜 + 科技频道"""
import json
from typing import Optional
from infrastructure.http_client import HttpClient
from models.hot_item import SearchResult


class TouTiaoSearcher:
    name = "toutiao"

    def __init__(self, http: Optional[HttpClient] = None):
        self.http = http or HttpClient()

    def search(self, keywords: list[str], max_results: int = 20) -> list[SearchResult]:
        results = []

        for method in ["_fetch_hotboard", "_fetch_tech"]:
            try:
                results.extend(getattr(self, method)())
            except Exception as e:
                print(f"  [头条] {method} 失败: {e}")

        seen = set()
        unique = []
        for r in results:
            if r.url not in seen:
                seen.add(r.url)
                unique.append(r)
        unique.sort(key=lambda r: r.hot_score, reverse=True)
        return unique[:max_results]

    def _fetch_hotboard(self) -> list[SearchResult]:
        url = ("https://www.toutiao.com/hot-event/hot-board/"
               "?origin=toutiao_pc")
        resp = self.http.get(url)
        data = resp.json()
        items = data.get("data", []) if isinstance(data, dict) else data

        results = []
        for item in items:
            title = item.get("Title", "") or item.get("title", "") or ""
            url_val = item.get("Url", "") or ""
            hot = int(item.get("HotValue", 0) or item.get("hot_value", 0) or 0)

            if not title:
                continue

            ai_kw = ["ai", "人工智能", "大模型", "llm", "gpt", "chatgpt",
                     "claude", "openai", "deepseek", "机器学习", "编程",
                     "算法", "科技", "数码", "芯片", "互联网"]
            is_ai = any(k in title.lower() for k in ai_kw)

            results.append(SearchResult(
                title=title,
                url=url_val or f"https://www.toutiao.com/search/{title}",
                summary=title,
                source="toutiao",
                source_domain="toutiao.com",
                hot_score=hot if is_ai else hot // 10,
                language="zh",
                tags=["头条热搜", "AI" if is_ai else "其他"],
            ))
        return results

    def _fetch_tech(self) -> list[SearchResult]:
        url = ("https://www.toutiao.com/api/pc/feed/"
               "?category=科技&widen=1&count=15")
        try:
            resp = self.http.get(url)
            data = resp.json()
        except Exception:
            return []

        results = []
        for item in data.get("data", []):
            title = item.get("title", "") or item.get("abstract", "") or ""
            src_url = item.get("source_url", "") or item.get("article_url", "") or ""
            if src_url and not src_url.startswith("http"):
                src_url = f"https://www.toutiao.com{src_url}"
            abstract = item.get("abstract", "") or ""

            ai_kw = ["ai", "人工智能", "大模型", "llm"]
            is_ai = any(k in title.lower() for k in ai_kw)

            if title:
                results.append(SearchResult(
                    title=title, url=src_url,
                    summary=abstract[:200],
                    source="toutiao", source_domain="toutiao.com",
                    hot_score=30 if is_ai else 5,
                    language="zh",
                    tags=["头条科技"],
                ))
        return results
