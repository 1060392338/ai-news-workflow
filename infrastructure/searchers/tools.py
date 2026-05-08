"""AI 工具 / MCP / 开发者生态 搜索器

搜索范围：
- GitHub Trending (AI 工具类仓库)
- MCP Server 发现
- AI 工具发布 / Product Hunt 精选
- 开发者生态热点
"""
import json
import re
from datetime import datetime, timezone, timedelta
from typing import Optional

from infrastructure.http_client import HttpClient
from models.hot_item import SearchResult


class ToolsSearcher:
    name = "tools"

    def __init__(self, http: Optional[HttpClient] = None):
        self.http = http or HttpClient()

    def search(self, keywords: list[str], max_results: int = 20) -> list[SearchResult]:
        results = []
        for method in ["_fetch_github_trending", "_fetch_mcp_discovery",
                        "_fetch_ai_tools"]:
            try:
                results.extend(getattr(self, method)())
            except Exception as e:
                print(f"  [工具] {method} 失败: {e}")

        seen = set()
        unique = []
        for r in results:
            if r.url not in seen:
                seen.add(r.url)
                unique.append(r)
        unique.sort(key=lambda r: r.hot_score, reverse=True)
        return unique[:max_results]

    def _fetch_github_trending(self) -> list[SearchResult]:
        """GitHub Trending - 按 AI 相关主题搜索"""
        headers = {
            "Accept": "text/html,application/xhtml+xml",
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        }
        results = []

        # GitHub Trending 页面
        languages = ["python", "typescript", "rust", "go"]
        for lang in languages:
            try:
                url = f"https://github.com/trending/{lang}?since=weekly"
                resp = self.http.get(url, headers=headers, timeout=10)
                html = resp.text

                # 提取仓库信息
                repos = re.findall(
                    r'<h2[^>]*>\s*<a[^>]*href="/([^"]+)"[^>]*>', html
                )
                descs = re.findall(
                    r'<p class="col-9[^"]*"[^>]*>(.*?)</p>', html,
                    re.DOTALL
                )
                stars = re.findall(
                    r'<span[^>]*>\s*<svg[^>]*>.*?</svg>\s*([\d,]+)\s*</span>',
                    html, re.DOTALL
                )

                for i, repo_path in enumerate(repos[:5]):
                    full_name = repo_path.strip()
                    desc = ""
                    if i < len(descs):
                        desc = re.sub(r'<[^>]+>', '', descs[i]).strip()
                    star_count = 0
                    if i < len(stars):
                        star_count = int(stars[i].replace(",", ""))

                    results.append(SearchResult(
                        title=full_name.split("/")[-1],
                        summary=f"[{full_name}] {desc[:200]}" if desc else f"[{full_name}]",
                        url=f"https://github.com/{full_name}",
                        source=f"github_trending_{lang}",
                        hot_score=min(100, star_count // 50),
                        language="en" if desc and self._is_english(desc) else "zh",
                        published_at=datetime.now(timezone.utc) - timedelta(days=7),
                    ))
            except Exception:
                continue

        return results

    def _fetch_mcp_discovery(self) -> list[SearchResult]:
        """MCP Server 发现"""
        headers = {
            "Accept": "text/html,application/xhtml+xml",
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36"
            ),
        }
        results = []

        # 搜索 MCP 相关资源
        mcp_sources = [
            "https://github.com/topics/mcp-server",
            "https://github.com/topics/model-context-protocol",
            "https://github.com/punkpeye/awesome-mcp-servers",
            "https://github.com/modelcontextprotocol/servers",
        ]

        for url in mcp_sources:
            try:
                resp = self.http.get(url, headers=headers, timeout=10)
                html = resp.text

                # 提取仓库信息
                repos = re.findall(
                    r'<a[^>]*href="/[^"]+"[^>]*data-hovercard-type="repository"[^>]*>'
                    r'([^<]+)</a>', html
                )
                if not repos:
                    repos = re.findall(
                        r'<a[^>]*href="/([^/]+/[^/]+)"[^>]*>([^<]+)</a>', html
                    )
                    repos = [r[0] for r in repos if "mcp" in r[0].lower()
                             and len(r[0].split("/")) == 2]

                for repo in repos[:3]:
                    repo_name = repo.strip()
                    if "/" not in repo_name:
                        continue
                    results.append(SearchResult(
                        title=repo_name.split("/")[-1],
                        summary=f"[MCP Server] {repo_name}",
                        url=f"https://github.com/{repo_name}",
                        source="mcp_discovery",
                        hot_score=80,
                        language="en",
                        published_at=datetime.now(timezone.utc) - timedelta(days=30),
                    ))
            except Exception:
                continue

        return results

    def _fetch_ai_tools(self) -> list[SearchResult]:
        """AI 工具发现"""
        headers = {
            "Accept": "text/html,application/xhtml+xml",
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36"
            ),
        }
        results = []

        # 热门的 AI 工具发现站点
        tool_sources = [
            ("https://www.producthunt.com/topics/artificial-intelligence", "producthunt"),
            ("https://github.com/topics/ai-tools", "github_ai_tools"),
        ]

        for url, source in tool_sources:
            try:
                resp = self.http.get(url, headers=headers, timeout=10)
                html = resp.text

                # ProductHunt 提取
                if "producthunt" in source:
                    titles = re.findall(
                        r'<a[^>]*class="[^"]*text-gray-900[^"]*"[^>]*>(.*?)</a>',
                        html
                    )
                    for title in titles[:5]:
                        title = re.sub(r'<[^>]+>', '', title).strip()
                        if title:
                            results.append(SearchResult(
                                title=title,
                                summary="",
                                url=url,
                                source=source,
                                hot_score=70,
                                language="en",
                            ))

                # GitHub 提取
                elif "github" in source:
                    repos = re.findall(
                        r'<a[^>]*href="/([^/]+/[^/]+)"[^>]*class="[^"]*text-bold[^"]*"',
                        html
                    )
                    for repo in repos[:5]:
                        repo_name = repo.strip()
                        if "/" not in repo_name:
                            continue
                        results.append(SearchResult(
                            title=repo_name.split("/")[-1],
                            summary=f"[AI Tool] {repo_name}",
                            url=f"https://github.com/{repo_name}",
                            source=source,
                            hot_score=75,
                            language="en",
                        ))
            except Exception:
                continue

        return results

    def _is_english(self, text: str) -> bool:
        """检查文本是否为英文"""
        if not text:
            return True
        en_chars = sum(1 for c in text if c.isascii() and c.isalpha())
        total = sum(1 for c in text if c.isalpha())
        return en_chars / total > 0.5 if total > 0 else True
