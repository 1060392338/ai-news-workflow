"""GitHub 搜索器 — Trending + Search API"""
import os
from datetime import datetime, timedelta
from typing import Optional
from infrastructure.http_client import HttpClient
from models.hot_item import SearchResult


class GitHubSearcher:
    name = "github"

    def __init__(self, http=None):
        self.http = http or HttpClient()
        self._headers = {"Accept": "application/vnd.github+json"}
        # 支持 GITHUB_TOKEN 环境变量（避免未认证的 60 req/h 速率限制）
        gh_token = os.environ.get("GITHUB_TOKEN", "")
        if gh_token:
            self._headers["Authorization"] = f"Bearer {gh_token}"

    def search(self, keywords: list[str], max_results: int = 20) -> list[SearchResult]:
        results: list[SearchResult] = []
        seen: set[str] = set()

        # 1. Trending (搜索近期高星项目)
        try:
            items = self._fetch_trending()
            for item in items:
                key = item["url"]
                if key in seen:
                    continue
                seen.add(key)
                results.append(SearchResult(
                    title=item["title"],
                    url=item["url"],
                    summary=item.get("description", ""),
                    source="github",
                    source_domain="github.com",
                    hot_score=item.get("stars", 0),
                    language="en",
                    tags=["github", "trending"],
                ))
        except Exception as e:
            print(f"  [GitHub] Trending 失败: {e}")

        # 2. 关键词搜索
        for kw in keywords:
            try:
                items = self._search_api(kw)
                for item in items:
                    key = item["url"]
                    if key in seen:
                        continue
                    seen.add(key)
                    results.append(SearchResult(
                        title=item["title"],
                        url=item["url"],
                        summary=item.get("description", ""),
                        source="github",
                        source_domain="github.com",
                        hot_score=item.get("stars", 0),
                        published_at=item.get("created_at"),
                        language="en",
                        tags=["github", kw.lower().replace(" ", "-")],
                    ))
            except Exception as e:
                print(f"  [GitHub] API '{kw}' 失败: {e}")

        results.sort(key=lambda r: r.hot_score, reverse=True)
        return results[:max_results]

    def _fetch_trending(self) -> list[dict]:
        since = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d")
        url = f"https://api.github.com/search/repositories?q=created:>{since}+stars:>100&sort=stars&order=desc&per_page=15"
        resp = self.http.get(url, headers=self._headers)
        data = resp.json()
        return [{
            "title": r.get("full_name", ""),
            "url": r.get("html_url", ""),
            "description": r.get("description", "") or "",
            "stars": r.get("stargazers_count", 0),
            "created_at": r.get("created_at"),
        } for r in data.get("items", [])]

    def _search_api(self, keyword: str) -> list[dict]:
        import urllib.parse
        query = urllib.parse.quote(f"{keyword} stars:>50")
        url = f"https://api.github.com/search/repositories?q={query}&sort=stars&order=desc&per_page=10"
        resp = self.http.get(url, headers=self._headers)
        data = resp.json()
        return [{
            "title": r.get("full_name", ""),
            "url": r.get("html_url", ""),
            "description": r.get("description", "") or "",
            "stars": r.get("stargazers_count", 0),
            "created_at": r.get("created_at"),
        } for r in data.get("items", [])]
