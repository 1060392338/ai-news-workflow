"""ArXiv 论文搜索器 — Atom API"""
import xml.etree.ElementTree as ET
import urllib.parse
from datetime import datetime
from typing import Optional
from infrastructure.http_client import HttpClient
from models.hot_item import SearchResult


class ArXivSearcher:
    name = "arxiv"
    BASE_URL = "http://export.arxiv.org/api/query"

    def __init__(self, http: Optional[HttpClient] = None):
        self.http = http or HttpClient()

    def search(self, keywords: list[str], max_results: int = 20) -> list[SearchResult]:
        categories = ["cs.AI", "cs.LG", "cs.CL", "cs.MA"]
        kw_parts = []
        for kw in keywords:
            if len(kw.split()) <= 3:
                kw_parts.append(f'ti:"{kw}" OR abs:"{kw}"')

        kw_query = "(%s)" % " OR ".join(kw_parts) if kw_parts else ""
        cat_query = "(%s)" % " OR ".join(categories)
        query = f"({cat_query}) AND {kw_query}" if kw_query else cat_query

        params = urllib.parse.urlencode({
            "search_query": query,
            "start": 0,
            "max_results": max_results,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        })

        try:
            resp = self.http.get(f"{self.BASE_URL}?{params}")
            return self._parse(resp.text)
        except Exception as e:
            print(f"  [ArXiv] 搜索失败: {e}")
            return []

    def _parse(self, xml: str) -> list[SearchResult]:
        ns = {
            "a": "http://www.w3.org/2005/Atom",
            "arxiv": "http://arxiv.org/schemas/atom",
        }
        root = ET.fromstring(xml)
        results = []

        for entry in root.findall("a:entry", ns):
            title = entry.findtext("a:title", "", ns).strip()
            title = " ".join(title.split())
            summary = " ".join((entry.findtext("a:summary", "", ns) or "").strip().split())[:300]
            url = entry.findtext("a:id", "", ns).strip()
            pub_text = entry.findtext("a:published", "", ns).strip()
            cats = [c.get("term", "") for c in entry.findall("a:category", ns)]

            pub_at = None
            if pub_text:
                try:
                    pub_at = datetime.fromisoformat(pub_text.replace("Z", "+00:00"))
                except ValueError:
                    pass

            if title:
                results.append(SearchResult(
                    title=title, url=url, summary=summary,
                    source="arxiv", source_domain="arxiv.org",
                    hot_score=0, published_at=pub_at,
                    language="en",
                    tags=["arxiv"] + [c for c in cats if c][:3],
                ))

        return results
