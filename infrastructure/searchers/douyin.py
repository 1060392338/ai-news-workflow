"""抖音热点搜索器 — 抓取抖音热搜榜"""
import json
import re
from typing import Optional

from infrastructure.http_client import HttpClient
from models.hot_item import SearchResult


class DouyinSearcher:
    name = "douyin"

    def __init__(self, http: Optional[HttpClient] = None):
        self.http = http or HttpClient()

    def search(self, keywords: list[str], max_results: int = 20) -> list[SearchResult]:
        results = []
        for method in ["_fetch_hotboard"]:
            try:
                results.extend(getattr(self, method)())
            except Exception as e:
                print(f"  [抖音] {method} 失败: {e}")

        seen = set()
        unique = []
        for r in results:
            if r.url not in seen:
                seen.add(r.url)
                unique.append(r)
        unique.sort(key=lambda r: r.hot_score, reverse=True)
        return unique[:max_results]

    def _fetch_hotboard(self) -> list[SearchResult]:
        """抖音热搜榜"""
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://www.douyin.com/",
        }

        results = []

        # 方法1: 通过抖音热搜API
        api_urls = [
            "https://www.douyin.com/aweme/v1/web/hot/search/list/",
            "https://www.douyin.com/hot",
        ]

        # 尝试API
        try:
            resp = self.http.get(
                api_urls[0],
                headers=headers,
                params={"device_platform": "webapp", "aid": "6383"},
            )
            data = resp.json()
            if "data" in data:
                word_list = (
                    data.get("data", {})
                    .get("word_list", [])
                )
                for item in word_list:
                    word = item.get("word", "")
                    hot_value = item.get("hot_value", 0)
                    if word:
                        results.append(SearchResult(
                            title=word,
                            summary=item.get("word", ""),
                            url=f"https://www.douyin.com/search/{word}",
                            source="douyin_hot",
                            hot_score=min(100, hot_value // 10000),
                            language="zh",
                        ))
            if results:
                return results
        except Exception:
            pass

        # 方法2: 解析HTML页面
        try:
            resp = self.http.get(api_urls[1], headers=headers)
            html = resp.text

            # 尝试从页面中的script数据提取
            match = re.search(
                r'<script[^>]*id="RENDER_DATA"[^>]*>(.*?)</script>',
                html, re.DOTALL
            )
            if match:
                raw = match.group(1)
                # RENDER_DATA 是 URL encoded JSON
                try:
                    import urllib.parse
                    decoded = urllib.parse.unquote(raw)
                    data = json.loads(decoded)
                    # 遍历找到热搜列表
                    def find_hot_words(obj, depth=0):
                        if depth > 5:
                            return
                        if isinstance(obj, dict):
                            for k, v in obj.items():
                                if k == "hot_words" and isinstance(v, list):
                                    for item in v:
                                        word = ""
                                        hot_val = 0
                                        if isinstance(item, dict):
                                            word = item.get("word", "")
                                            hot_val = item.get("hot_value", 0)
                                        elif isinstance(item, str):
                                            word = item
                                        if word:
                                            results.append(SearchResult(
                                                title=word,
                                                summary="",
                                                url=f"https://www.douyin.com/search/{word}",
                                                source="douyin_hot",
                                                hot_score=min(100, hot_val // 10000),
                                                language="zh",
                                            ))
                                    return
                                find_hot_words(v, depth + 1)
                        elif isinstance(obj, list):
                            for item in obj:
                                find_hot_words(item, depth + 1)

                    find_hot_words(decoded)
                except Exception:
                    pass

            if results:
                return results
        except Exception:
            pass

        # 方法3: 简单正则提取
        titles = re.findall(
            r'hot-title[^>]*>([^<]+)<', html
        ) if 'html' in dir() and html else []
        for i, title in enumerate(titles[:max_results]):
            title = title.strip()
            if title:
                results.append(SearchResult(
                    title=title,
                    summary="",
                    url=f"https://www.douyin.com/search/{title}",
                    source="douyin_hot",
                    hot_score=max(0, 100 - i * 5),
                    language="zh",
                ))

        return results
