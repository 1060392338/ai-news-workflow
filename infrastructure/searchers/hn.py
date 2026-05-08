"""Hacker News 搜索器 — Firebase API"""
from datetime import datetime
from typing import Optional
from infrastructure.http_client import HttpClient
from models.hot_item import SearchResult


class HackerNewsSearcher:
    name = "hackernews"
    BASE_URL = "https://hacker-news.firebaseio.com/v0"

    def __init__(self, http: Optional[HttpClient] = None):
        self.http = http or HttpClient()

    def search(self, keywords: list[str], max_results: int = 20) -> list[SearchResult]:
        try:
            top_ids = self.http.get(f"{self.BASE_URL}/topstories.json").json()[:50]
        except Exception as e:
            print(f"  [HN] 获取 top stories 失败: {e}")
            return []

        all_stories = []
        for sid in top_ids:
            try:
                story = self.http.get(f"{self.BASE_URL}/item/{sid}.json").json()
                if story and story.get("title") and story.get("url"):
                    all_stories.append(story)
            except Exception:
                continue

        # 关键词匹配 + AI 兜底
        matched = self._filter_relevant(all_stories, keywords)
        results = []
        for s in matched:
            ts = s.get("time", 0)
            results.append(SearchResult(
                title=s["title"],
                url=s.get("url", f"https://news.ycombinator.com/item?id={s['id']}"),
                summary=s["title"],
                source="hackernews",
                source_domain="news.ycombinator.com",
                hot_score=s.get("score", 0),
                published_at=datetime.fromtimestamp(ts) if ts else None,
                language="en",
                tags=["hackernews", "tech"],
            ))

        results.sort(key=lambda r: r.hot_score, reverse=True)
        return results[:max_results]

    def _filter_relevant(self, stories: list[dict],
                         keywords: list[str]) -> list[dict]:
        kw_lower = [k.lower() for k in keywords]
        ai_kw = ["ai", "llm", "gpt", "claude", "machine learning",
                 "neural", "deep learning", "agent", "rag",
                 "transformer", "openai", "chatgpt", "copilot"]

        matched = []
        seen = set()
        for s in stories:
            t = s["title"].lower()
            if t in seen:
                continue
            seen.add(t)
            if any(k in t for k in kw_lower):
                matched.append(s)
            elif len(matched) < 10 and any(k in t for k in ai_kw):
                matched.append(s)
        return matched
