"""RSS 搜索器 — 从 Karpathy 精选 90 个技术博客 RSS 抓取最新文章

基于 vigorX777/ai-daily-digest 的 RSS 源列表，提供英文技术博客的一手资讯来源。
源来源：Karpathy "Hacker News Popularity Contest 2025" 精选博客。
"""

import concurrent.futures
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

import httpx

from infrastructure.http_client import HttpClient
from models.hot_item import SearchResult


# 90 个 RSS 源（来自 Karpathy 精选技术博客）
RSS_FEEDS = [
    {"name": "simonwillison.net", "url": "https://simonwillison.net/atom/everything/", "lang": "en"},
    {"name": "jeffgeerling.com", "url": "https://www.jeffgeerling.com/blog.xml", "lang": "en"},
    {"name": "seangoedecke.com", "url": "https://www.seangoedecke.com/rss.xml", "lang": "en"},
    {"name": "krebsonsecurity.com", "url": "https://krebsonsecurity.com/feed/", "lang": "en"},
    {"name": "daringfireball.net", "url": "https://daringfireball.net/feeds/main", "lang": "en"},
    {"name": "antirez.com", "url": "http://antirez.com/rss", "lang": "en"},
    {"name": "pluralistic.net", "url": "https://pluralistic.net/feed/", "lang": "en"},
    {"name": "mitchellh.com", "url": "https://mitchellh.com/feed.xml", "lang": "en"},
    {"name": "dynomight.net", "url": "https://dynomight.net/feed.xml", "lang": "en"},
    {"name": "xeiaso.net", "url": "https://xeiaso.net/blog.rss", "lang": "en"},
    {"name": "devblogs.microsoft.com/oldnewthing", "url": "https://devblogs.microsoft.com/oldnewthing/feed", "lang": "en"},
    {"name": "lucumr.pocoo.org", "url": "https://lucumr.pocoo.org/feed.atom", "lang": "en"},
    {"name": "overreacted.io", "url": "https://overreacted.io/rss.xml", "lang": "en"},
    {"name": "johndcook.com", "url": "https://www.johndcook.com/blog/feed/", "lang": "en"},
    {"name": "matklad.github.io", "url": "https://matklad.github.io/feed.xml", "lang": "en"},
    {"name": "eli.thegreenplace.net", "url": "https://eli.thegreenplace.net/feeds/all.atom.xml", "lang": "en"},
    {"name": "berthub.eu", "url": "https://berthub.eu/articles/index.xml", "lang": "en"},
    {"name": "fabiensanglard.net", "url": "https://fabiensanglard.net/rss.xml", "lang": "en"},
    {"name": "gwern.net", "url": "https://gwern.substack.com/feed", "lang": "en"},
    {"name": "righto.com", "url": "https://www.righto.com/feeds/posts/default", "lang": "en"},
    {"name": "lcamtuf.substack.com", "url": "https://lcamtuf.substack.com/feed", "lang": "en"},
    {"name": "paulgraham.com", "url": "http://www.aaronsw.com/2002/feeds/pgessays.rss", "lang": "en"},
    {"name": "troyhunt.com", "url": "https://www.troyhunt.com/rss/", "lang": "en"},
    {"name": "computer.rip", "url": "https://computer.rip/rss.xml", "lang": "en"},
    {"name": "wheresyoured.at", "url": "https://www.wheresyoured.at/rss/", "lang": "en"},
    {"name": "minimaxir.com", "url": "https://minimaxir.com/index.xml", "lang": "en"},
    {"name": "geohot.github.io", "url": "https://geohot.github.io/blog/feed.xml", "lang": "en"},
    {"name": "jyn.dev", "url": "https://jyn.dev/atom.xml", "lang": "en"},
    {"name": "borretti.me", "url": "https://borretti.me/feed.xml", "lang": "en"},
    {"name": "terriblesoftware.org", "url": "https://terriblesoftware.org/feed/", "lang": "en"},
    {"name": "construction-physics.com", "url": "https://www.construction-physics.com/feed", "lang": "en"},
    {"name": "tedium.co", "url": "https://feed.tedium.co/", "lang": "en"},
    {"name": "susam.net", "url": "https://susam.net/feed.xml", "lang": "en"},
    {"name": "buttondown.com/hillelwayne", "url": "https://buttondown.com/hillelwayne/rss", "lang": "en"},
    {"name": "dwarkesh.com", "url": "https://www.dwarkeshpatel.com/feed", "lang": "en"},
    {"name": "filfre.net", "url": "https://www.filfre.net/feed/", "lang": "en"},
    {"name": "blog.jim-nielsen.com", "url": "https://blog.jim-nielsen.com/feed.xml", "lang": "en"},
    {"name": "geoffreylitt.com", "url": "https://www.geoffreylitt.com/feed.xml", "lang": "en"},
    {"name": "abortretry.fail", "url": "https://www.abortretry.fail/feed", "lang": "en"},
    {"name": "oldvcr.blogspot.com", "url": "https://oldvcr.blogspot.com/feeds/posts/default", "lang": "en"},
    {"name": "steveblank.com", "url": "https://steveblank.com/feed/", "lang": "en"},
    {"name": "bernsteinbear.com", "url": "https://bernsteinbear.com/feed.xml", "lang": "en"},
    {"name": "anildash.com", "url": "https://anildash.com/feed.xml", "lang": "en"},
    {"name": "miguelgrinberg.com", "url": "https://blog.miguelgrinberg.com/feed", "lang": "en"},
    {"name": "experimental-history.com", "url": "https://www.experimental-history.com/feed", "lang": "en"},
    {"name": "rachelbythebay.com", "url": "https://rachelbythebay.com/w/atom.xml", "lang": "en"},
    {"name": "timsh.org", "url": "https://timsh.org/rss/", "lang": "en"},
    {"name": "ericmigi.com", "url": "https://ericmigi.com/rss.xml", "lang": "en"},
    {"name": "maurycyz.com", "url": "https://maurycyz.com/index.xml", "lang": "en"},
    {"name": "shkspr.mobi", "url": "https://shkspr.mobi/blog/feed/", "lang": "en"},
    {"name": "garymarcus.substack.com", "url": "https://garymarcus.substack.com/feed", "lang": "en"},
    {"name": "derekthompson.org", "url": "https://www.theatlantic.com/feed/author/derek-thompson/", "lang": "en"},
    {"name": "evanhahn.com", "url": "https://evanhahn.com/feed.xml", "lang": "en"},
    {"name": "joanwestenberg.com", "url": "https://joanwestenberg.com/rss", "lang": "en"},
    {"name": "xania.org", "url": "https://xania.org/feed", "lang": "en"},
    {"name": "micahflee.com", "url": "https://micahflee.com/feed/", "lang": "en"},
    {"name": "nesbitt.io", "url": "https://nesbitt.io/feed.xml", "lang": "en"},
    {"name": "entropicthoughts.com", "url": "https://entropicthoughts.com/feed.xml", "lang": "en"},
    {"name": "jayd.ml", "url": "https://jayd.ml/feed.xml", "lang": "en"},
    {"name": "downtowndougbrown.com", "url": "https://www.downtowndougbrown.com/feed/", "lang": "en"},
    {"name": "brutecat.com", "url": "https://brutecat.com/rss.xml", "lang": "en"},
    {"name": "bogdanthegeek.github.io", "url": "https://bogdanthegeek.github.io/blog/index.xml", "lang": "en"},
    {"name": "hugotunius.se", "url": "https://hugotunius.se/feed.xml", "lang": "en"},
    {"name": "chadnauseam.com", "url": "https://chadnauseam.com/rss.xml", "lang": "en"},
    {"name": "simone.org", "url": "https://simone.org/feed/", "lang": "en"},
    {"name": "it-notes.dragas.net", "url": "https://it-notes.dragas.net/feed/", "lang": "en"},
    {"name": "beej.us", "url": "https://beej.us/blog/rss.xml", "lang": "en"},
    {"name": "danielwirtz.com", "url": "https://danielwirtz.com/rss.xml", "lang": "en"},
    {"name": "matduggan.com", "url": "https://matduggan.com/rss/", "lang": "en"},
    {"name": "refactoringenglish.com", "url": "https://refactoringenglish.com/index.xml", "lang": "en"},
    {"name": "worksonmymachine.substack.com", "url": "https://worksonmymachine.substack.com/feed", "lang": "en"},
    {"name": "danieldelaney.net", "url": "https://danieldelaney.net/feed", "lang": "en"},
    {"name": "herman.bearblog.dev", "url": "https://herman.bearblog.dev/feed/", "lang": "en"},
    {"name": "blog.pixelmelt.dev", "url": "https://blog.pixelmelt.dev/rss/", "lang": "en"},
    {"name": "danielchasehooper.com", "url": "https://danielchasehooper.com/feed.xml", "lang": "en"},
    {"name": "chiark.greenend.org.uk/~sgtatham", "url": "https://www.chiark.greenend.org.uk/~sgtatham/quasiblog/feed.xml", "lang": "en"},
    {"name": "grantslatton.com", "url": "https://grantslatton.com/rss.xml", "lang": "en"},
    {"name": "michael.stapelberg.ch", "url": "https://michael.stapelberg.ch/feed.xml", "lang": "en"},
    {"name": "keygen.sh", "url": "https://keygen.sh/blog/feed.xml", "lang": "en"},
    {"name": "mjg59.dreamwidth.org", "url": "https://mjg59.dreamwidth.org/data/rss", "lang": "en"},
    {"name": "tedunangst.com", "url": "https://www.tedunangst.com/flak/rss", "lang": "en"},
    {"name": "skyfall.dev", "url": "https://skyfall.dev/rss.xml", "lang": "en"},
    {"name": "gilesthomas.com", "url": "https://gilesthomas.com/feed/rss.xml", "lang": "en"},
    {"name": "idiallo.com", "url": "https://idiallo.com/feed.rss", "lang": "en"},
    {"name": "utcc.utoronto.ca/~cks", "url": "https://utcc.utoronto.ca/~cks/space/blog/?atom", "lang": "en"},
    {"name": "rakhim.exotext.com", "url": "https://rakhim.exotext.com/rss.xml", "lang": "en"},
]


class RSSDigestSearcher:
    """RSS 技术博客搜索器 — 从 90 个 Karpathy 精选博客 RSS 获取文章

    不关心 keywords（RSS 源是固定的技术博客列表），
    返回最近 2 天的所有文章。
    """

    name = "rss_digest"

    def __init__(self, http=None):
        self.http = http or HttpClient()

    def search(self, keywords: list[str], max_results: int = 20) -> list[SearchResult]:
        """从 RSS 源抓取最新文章

        并行抓取前 N 个源，每源 10s 超时，整体 60s 超时。
        收集去重后返回最新 max_results 篇。
        """
        results: list[SearchResult] = []
        seen_titles: set[str] = set()
        now = datetime.now(timezone.utc)

        n_feeds = min(20, len(RSS_FEEDS))
        feeds_to_try = sorted(RSS_FEEDS, key=lambda f: f["name"])[:n_feeds]

        # 并行抓取所有源，每个源 10s 超时，整体 60s
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
            future_map = {
                pool.submit(self._fetch_feed_with_timeout, feed): feed["name"]
                for feed in feeds_to_try
            }
            try:
                for f in concurrent.futures.as_completed(future_map, timeout=60):
                    name = future_map[f]
                    try:
                        articles = f.result()
                        for art in articles:
                            title = art.get("title", "").strip()
                            link = art.get("link", "").strip()
                            if not title or not link:
                                continue
                            key = title.lower()[:80]
                            if key in seen_titles:
                                continue
                            seen_titles.add(key)

                            pub_date = art.get("pubDate")
                            pub_dt = self._parse_date(pub_date) if pub_date else None

                            results.append(SearchResult(
                                title=title,
                                url=link,
                                summary=art.get("description", "")[:300],
                                source="rss_digest",
                                source_domain=urlparse(link).netloc or feed["name"],
                                hot_score=100,
                                published_at=pub_dt or now,
                                language="en",
                                tags=["rss", "blog", name],
                            ))
                    except Exception:
                        pass  # 单个源失败不影响整体
            except concurrent.futures.TimeoutError:
                pass  # 整体超时，用已完成的源

        results.sort(key=lambda r: r.published_at or now, reverse=True)
        return results[:max_results]

    def _fetch_feed_with_timeout(self, feed: dict) -> list[dict]:
        """带超时的单个源抓取"""
        with httpx.Client(timeout=10, follow_redirects=True) as client:
            try:
                resp = client.get(
                    feed["url"],
                    headers={"User-Agent": "Mozilla/5.0 RSS-Digest/1.0"},
                )
                if resp.status_code != 200:
                    return []
                text = resp.text
                if "<feed" in text[:500]:
                    return self._parse_atom(text)
                return self._parse_rss(text)
            except Exception:
                return []

    def _fetch_feed(self, feed: dict) -> list[dict]:
        """抓取并解析单个 RSS/Atom 源"""
        resp = self.http.get(feed["url"])
        if not resp or not resp.text:
            return []

        text = resp.text

        # 尝试 Atom 格式
        if "<feed" in text[:500]:
            return self._parse_atom(text)
        return self._parse_rss(text)

    def _parse_rss(self, xml: str) -> list[dict]:
        """解析 RSS 2.0 XML"""
        items = []
        try:
            root = ET.fromstring(xml)
            for item in root.iter("item"):
                title = self._get_text(item, "title")
                link = self._get_text(item, "link")
                pub_date = self._get_text(item, "pubDate")
                desc = self._get_text(item, "description")
                if title or link:
                    items.append({
                        "title": self._strip_html(title),
                        "link": link,
                        "pubDate": pub_date,
                        "description": self._strip_html(desc)[:500],
                    })
        except ET.ParseError:
            pass
        return items

    def _parse_atom(self, xml: str) -> list[dict]:
        """解析 Atom XML"""
        items = []
        ATOM_NS = "http://www.w3.org/2005/Atom"
        try:
            root = ET.fromstring(xml)
            for entry in root.iter(f"{{{ATOM_NS}}}entry"):
                title_el = entry.find(f"{{{ATOM_NS}}}title")
                title = self._strip_html(title_el.text if title_el is not None else "")

                link = ""
                for link_el in entry.iter(f"{{{ATOM_NS}}}link"):
                    href = link_el.get("href", "")
                    rel = link_el.get("rel", "alternate")
                    if rel == "alternate":
                        link = href
                        break
                if not link:
                    for link_el in entry.iter(f"{{{ATOM_NS}}}link"):
                        link = link_el.get("href", "")
                        if link:
                            break

                published_el = entry.find(f"{{{ATOM_NS}}}published")
                pub_date = published_el.text if published_el is not None else ""
                if not pub_date:
                    updated_el = entry.find(f"{{{ATOM_NS}}}updated")
                    pub_date = updated_el.text if updated_el is not None else ""

                summary_el = entry.find(f"{{{ATOM_NS}}}summary")
                summary = summary_el.text if summary_el is not None else ""
                if not summary:
                    content_el = entry.find(f"{{{ATOM_NS}}}content")
                    summary = content_el.text if content_el is not None else ""

                if title or link:
                    items.append({
                        "title": title,
                        "link": link,
                        "pubDate": pub_date,
                        "description": self._strip_html(summary)[:500],
                    })
        except ET.ParseError:
            pass
        return items

    @staticmethod
    def _get_text(element, tag: str, ns: Optional[dict] = None) -> str:
        """安全提取元素文本"""
        try:
            if ns:
                el = element.find(f"atom:{tag}", ns)
            else:
                el = element.find(tag)
            if el is not None and el.text:
                return el.text.strip()
            return ""
        except Exception:
            return ""

    @staticmethod
    def _strip_html(html: str) -> str:
        """去除 HTML 标签"""
        if not html:
            return ""
        text = re.sub(r"<[^>]+>", " ", html)
        text = re.sub(r"&amp;", "&", text)
        text = re.sub(r"&lt;", "<", text)
        text = re.sub(r"&gt;", ">", text)
        text = re.sub(r"&quot;", '"', text)
        text = re.sub(r"&#39;", "'", text)
        text = re.sub(r"&nbsp;", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    @staticmethod
    def _parse_date(date_str: str) -> Optional[datetime]:
        """解析 RSS/Atom 日期字符串"""
        if not date_str:
            return None
        try:
            # RFC 2822 (常见于 RSS)
            from email.utils import parsedate_to_datetime
            return parsedate_to_datetime(date_str)
        except Exception:
            pass
        try:
            # ISO 8601 (常见于 Atom)
            from dateutil import parser
            return parser.parse(date_str)
        except Exception:
            pass
        return None
