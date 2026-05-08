"""聚合服务 — 去重、排序、Top N"""
import re
from datetime import datetime
from models.hot_item import SearchResult, HotItem


class Aggregator:
    """
    聚合所有搜索源结果:
    1. 过滤无关内容
    2. URL + 标题双重去重
    3. 综合排序 (热度 + 时效 + 源权重)
    4. 输出 Top N
    """

    def aggregate(self, all_results: dict[str, list[SearchResult]],
                  top_n: int = 10, category: str = "ai") -> list[HotItem]:
        flat = []
        for source, items in all_results.items():
            for item in items:
                if not item.title or not item.title.strip():
                    continue
                if self._is_noise(item, category):
                    continue
                flat.append(item)

        source_counts = {k: len(v) for k, v in all_results.items()}
        print(f"  [聚合] 原始: {sum(source_counts.values())}条"
              f" | 过滤后: {len(flat)}条")

        unique = self._dedup(flat)
        print(f"  [聚合] 去重后: {len(unique)}条")

        ranked = self._rank(unique)

        top = ranked[:top_n]
        result = []
        for i, item in enumerate(top, 1):
            result.append(HotItem(
                rank=i,
                title=item.title,
                summary=item.summary,
                url=item.url,
                source=item.source,
                source_domain=item.source_domain,
                hot_score=item.hot_score,
                language=item.language,
                tags=item.tags,
                needs_translation=(item.language == "en"),
            ))

        self._print_top(result)
        return result

    def _is_noise(self, item: SearchResult, category: str) -> bool:
        """判断是否噪音 (非 AI 相关)"""
        if category == "ai":
            ai_kw = [
                "ai", "人工智能", "llm", "大模型", "gpt", "claude", "openai",
                "chatgpt", "deepseek", "机器学习", "深度学习", "神经网络",
                "agent", "rag", "transformer", "diffusion", "copilot",
                "编程", "代码", "算法", "科技", "芯片",
                "gemini", "mistral", "llama", "fine-tun", "token",
                "github", "开源", "python", "docker",
            ]
            text = (item.title + " " + item.summary + " " + " ".join(item.tags)).lower()
            if not any(k in text for k in ai_kw):
                if item.source in ("zhihu", "toutiao") and item.hot_score < 30:
                    return True
        return False

    def _dedup(self, items: list[SearchResult]) -> list[SearchResult]:
        seen_urls, seen_titles = set(), set()
        unique = []
        for item in items:
            uk = item.url.strip().rstrip("/")
            tk = item.title.strip()[:20].lower()
            if uk and uk in seen_urls:
                continue
            if tk and tk in seen_titles:
                continue
            seen_urls.add(uk)
            seen_titles.add(tk)
            unique.append(item)
        return unique

    def _rank(self, items: list[SearchResult]) -> list[SearchResult]:
        now = datetime.now()
        weights = {"github": 80, "hackernews": 70, "arxiv": 60,
                    "zhihu": 50, "toutiao": 40}

        for item in items:
            score = min(item.hot_score, 1000)

            if item.published_at:
                h = (now - item.published_at).total_seconds() / 3600
                score += 200 if h < 6 else 100 if h < 24 else 50
            else:
                score += 30

            score += weights.get(item.source, 30)
            if item.language == "zh":
                score += 50

            item.hot_score = score

        items.sort(key=lambda r: r.hot_score, reverse=True)
        return items

    def _print_top(self, top: list[HotItem]):
        print(f"  ✅ Top {len(top)}:")
        for item in top:
            src_icon = {"github": "🐙", "hackernews": "📰", "arxiv": "📄",
                        "zhihu": "💬", "toutiao": "🔥"}.get(item.source, "📌")
            lang = "🌐" if item.needs_translation else "🇨🇳"
            print(f"    #{item.rank} {src_icon} [{item.source}] {item.title}")
            print(f"        {lang} 热度:{item.hot_score}")
