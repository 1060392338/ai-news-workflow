"""飞书消息格式化 — 表现层"""
from datetime import datetime
from models.hot_item import HotItem


class FeishuMessages:
    """飞书消息模板"""

    def top10_message(self, top10: list[HotItem], display_name: str = "") -> str:
        """Top 10 热点推送"""
        header = f"🤖 **{display_name} · AI 热点日报**" if display_name else "🤖 **AI 热点日报**"
        lines = [
            header,
            f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "",
            "━━━━━━━━━━━━━━━━━━━━",
            "🔥 **今日热点 Top 10**",
            "━━━━━━━━━━━━━━━━━━━━",
            "",
        ]

        icons = {"github": "🐙", "hackernews": "📰", "arxiv": "📄",
                 "zhihu": "💬", "toutiao": "🔥"}

        for item in top10:
            icon = icons.get(item.source, "📌")
            lang = "🌐" if item.needs_translation else "🇨🇳"
            summary = item.summary[:100] + "…" if len(item.summary) > 100 else item.summary
            lines.append(f"**{item.rank}. {icon} {item.title}**")
            lines.append(f"   {lang} {summary}")
            lines.append(f"   📎 {item.source} · {item.url}")
            lines.append("")

        lines.extend([
            "━━━━━━━━━━━━━━━━━━━━",
            "",
            "💡 **回复数字选择要发布的选题**",
            "   格式: `1,3,7` 或 `1-5`",
            "",
            "⚡ 选中后我会自动生成文章给你预览",
        ])
        return "\n".join(lines)

    def preview_message(self, articles: list[dict]) -> str:
        """文章预览推送"""
        lines = [
            "📝 **文章已生成，请确认是否发布**",
            "━━━━━━━━━━━━━━━━━━━━",
            "",
        ]
        for i, art in enumerate(articles, 1):
            title = art.get("title", "（无标题）")
            content = art.get("content", "")
            preview = content[:200].replace("\n", " ") + "…" if len(content) > 200 else content
            lines.append(f"**#{i}: {title}**")
            lines.append(f"  {preview}")
            lines.append("")

        lines.extend([
            "━━━━━━━━━━━━━━━━━━━━",
            "",
            "✅ 回复 `发布全部` 全部发布",
            "✅ 回复 `发布 1,2` 发布指定序号",
            "✏️ 回复 `重写 N` 重新生成第 N 篇",
            "❌ 回复 `跳过全部` 全部放弃",
        ])
        return "\n".join(lines)
