"""图片搜索服务 — 为文章配真实图片"""
import os
import json
import re
from typing import Optional

IMAGE_CACHE: dict[str, list[str]] = {}


class ImageSearchService:
    """
    图片搜索服务：根据关键词搜索真实图片 URL

    支持源：
    1. Unsplash (推荐) — 免费，高质量，需注册获取 API Key
    2. 备用：内置 AI 相关图片
    """

    def __init__(self):
        self._unsplash_key = os.environ.get("UNSPLASH_ACCESS_KEY", "")

    def _extract_keywords(self, description: str) -> str:
        """从中文描述中提取核心关键词（去除修饰词、只留名词）返回搜索用的短字符串"""
        import re
        # 去掉 "一张" "展示" "的" "左边" "右边" 等修饰
        cleaned = re.sub(r'[一-两]张|展示|的|左边|右边|上方|下方|背景|面对|突出|标注|写着|配文字', '', description)
        # 去掉标点
        cleaned = re.sub(r'[，。！？、；：""（）【】】\n\r]', ' ', cleaned)
        # 切成词
        words = [w.strip() for w in cleaned.split() if len(w.strip()) > 1]
        # 取前 4 个最有意义的词（去除方位/介词/量词）
        stop = {'一个','这个','那个','这些','一些','一张','一位','一种','之间','之后','所在'}
        keywords = [w for w in words if w not in stop]
        if not keywords:
            keywords = words
        # 限制长度，避免中文长句搜不到
        result = ' '.join(keywords[:4])
        return result

    def search(self, keyword: str, count: int = 3) -> list[str]:
        """根据关键词搜索图片，返回图片 URL 列表"""
        keyword = keyword.strip()
        if not keyword:
            return []

        # 提取核心关键词
        search_term = self._extract_keywords(keyword)
        if not search_term:
            search_term = keyword

        cache_key = f"{search_term}:{count}"
        if cache_key in IMAGE_CACHE:
            return IMAGE_CACHE[cache_key]

        urls = []

        # 1. 尝试 Unsplash（用英文翻或核心词）
        if self._unsplash_key:
            try:
                urls = self._search_unsplash(search_term, count)
            except Exception as e:
                print(f"  [ImageSearch] Unsplash 失败: {e}")

        # 2. 备用：picsum
        if not urls:
            urls = self._fallback_images(search_term, count)

        if urls:
            IMAGE_CACHE[cache_key] = urls

        return urls

    def _search_unsplash(self, keyword: str, count: int) -> list[str]:
        """通过 Unsplash API 搜索图片"""
        import requests
        resp = requests.get(
            "https://api.unsplash.com/search/photos",
            params={"query": keyword, "per_page": min(count, 10)},
            headers={"Authorization": f"Client-ID {self._unsplash_key}"},
            timeout=10,
        )
        data = resp.json()
        return [r["urls"]["regular"] for r in data.get("results", [])[:count]]

    def _fallback_images(self, keyword: str, count: int) -> list[str]:
        """内置备用图片 — 使用 picsum.photos 生成占位图"""
        # 用关键词的哈希值决定图片 ID，保证一致
        seed = abs(hash(keyword)) % 1000
        return [
            f"https://picsum.photos/seed/{keyword.replace(' ','')}{i}/800/450"
            for i in range(count)
        ]

    def resolve_article_images(self, content: str, title: str,
                               image_hints: list[str]) -> str:
        """
        解析文章中的图片占位符，替换为真实图片 URL

        ![图片说明: xxx] → <img src="https://..." alt="xxx">
        """
        if not image_hints and "![" not in content:
            return content

        # 如果写作 Agent 给了 images 列表，先搜索
        resolved_urls = []
        for hint in image_hints:
            urls = self.search(hint, count=1)
            if urls:
                resolved_urls.append(urls[0])
            else:
                resolved_urls.append("")

        # 替换占位符
        def _replace_placeholder(match):
            nonlocal resolved_urls
            alt = match.group(1) or "AI配图"
            if resolved_urls:
                url = resolved_urls.pop(0)
                if url:
                    return f'<img src="{url}" alt="{alt}">'
            return ""

        result = re.sub(r'!\[图片说明:\s*(.*?)\]', _replace_placeholder, content)

        # 如果还有剩余的 URL 但文章里没有占位符了，追加到文章末尾
        if resolved_urls:
            remaining = [u for u in resolved_urls if u]
            if remaining:
                imgs = "".join(
                    f'<img src="{u}" alt="配图">' for u in remaining
                )
                result += f"\n{imgs}"

        return result
