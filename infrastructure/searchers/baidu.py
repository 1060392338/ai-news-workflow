"""百度热搜搜索器 — 抓取百度热搜榜 + 新闻"""
import json
import re
from typing import Optional

from infrastructure.http_client import HttpClient
from models.hot_item import SearchResult


class BaiduSearcher:
    name = "baidu"

    def __init__(self, http: Optional[HttpClient] = None):
        self.http = http or HttpClient()

    def search(self, keywords: list[str], max_results: int = 20) -> list[SearchResult]:
        results = []
        for method in ["_fetch_hotboard", "_fetch_news"]:
            try:
                results.extend(getattr(self, method)())
            except Exception as e:
                print(f"  [百度] {method} 失败: {e}")

        seen = set()
        unique = []
        for r in results:
            if r.url not in seen:
                seen.add(r.url)
                unique.append(r)
        unique.sort(key=lambda r: r.hot_score, reverse=True)
        return unique[:max_results]

    def _fetch_hotboard(self) -> list[SearchResult]:
        """百度热搜榜"""
        url = "https://top.baidu.com/board?tab=realtime"
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml",
        }
        resp = self.http.get(url, headers=headers)
        html = resp.text

        # 从 HTML 中提取热搜数据 (JSON 内嵌在 script 标签)
        results = []
        # 尝试从 window.__NUXT__ 提取
        match = re.search(r"window\.__NUXT__\s*=\s*({.*?});", html, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(1))
                cards = (
                    data.get("state", {})
                    .get("topData", {})
                    .get("data", {})
                    .get("cards", [])
                )
                for card in cards:
                    for item in card.get("content", []):
                        word = item.get("word", item.get("query", ""))
                        hot_score = item.get("hotScore", 0)
                        url_link = item.get("url", "")
                        desc = item.get("desc", word)
                        if word:
                            results.append(SearchResult(
                                title=word,
                                summary=desc[:200],
                                url=url_link or f"https://www.baidu.com/s?wd={word}",
                                source="baidu_hot",
                                hot_score=hot_score,
                                language="zh",
                            ))
            except (json.JSONDecodeError, KeyError, TypeError):
                pass

        # fallback: 直接解析页面标题列表
        if not results:
            titles = re.findall(
                r'<div class="c-single-text-ellipsis">(.*?)</div>', html
            )
            for i, title in enumerate(titles[:max_results]):
                results.append(SearchResult(
                    title=title.strip(),
                    summary="",
                    url=f"https://www.baidu.com/s?wd={title.strip()}",
                    source="baidu_hot",
                    hot_score=max(0, 100 - i * 5),
                    language="zh",
                ))
        return results

    def _fetch_news(self, limit: int = 15) -> list[SearchResult]:
        """百度新闻搜索"""
        url = "https://news.baidu.com/"
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        }
        resp = self.http.get(url, headers=headers)
        html = resp.text
        results = []

        # 提取新闻标题和链接
        links = re.findall(
            r'<a\s+href="(https?://[^"]+)"[^>]*>(.*?)</a>', html
        )
        seen_titles = set()
        for href, title in links:
            title = re.sub(r'<[^>]+>', '', title).strip()
            if len(title) < 8 or title in seen_titles:
                continue
            seen_titles.add(title)
            if len(results) >= limit:
                break
            results.append(SearchResult(
                title=title,
                summary="",
                url=href,
                source="baidu_news",
                hot_score=70,
                language="zh",
            ))
        return results
