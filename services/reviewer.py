"""合规审核服务 — 敏感词 + 平台规则 + 质量检查 + 内容主题检查"""
import re


class Reviewer:
    """
    合规审核:
    - 敏感词过滤
    - 平台规则 (头条禁止引流等)
    - 内容质量检查
    - 内容主题检查 (非 AI/科技内容拦截)
    """

    SENSITIVE_WORDS = [
        "赌博", "色情", "毒品",
    ]

    BANNED_PATTERNS = [
        (r"(?i)微信\s*号", "禁止引流(微信号)"),
        (r"(?i)关注.*公众号", "禁止引流(公众号)"),
        (r"(?i)加\s*我.*微", "禁止引流(微信)"),
        (r"(?i)私信.*领取", "禁止诱导"),
        (r"(?i)点击.*领取", "禁止诱导"),
    ]

    # 文章主题分类 — 检测是否为 AI/科技相关内容
    # 如果命中过多军事/政治/娱乐关键词且缺乏 AI 关键词，则标记为非 AI 内容
    AI_KEYWORDS = [
        "AI", "人工智能", "大模型", "GPT", "Claude", "ChatGPT", "OpenAI",
        "机器学习", "深度学习", "神经网络", "LLM", "Agent", "MCP", "RAG",
        "Copilot", "Cursor", "Stable Diffusion", "Diffusion", "Transformer",
        "算法", "训练", "推理", "算力", "GPU", "芯片", "自动驾驶",
        "NLP", "计算机视觉", "多模态", "AIGC", "生成式",
        "GitHub", "开源", "编程", "代码", "程序员", "开发",
        "机器人", "智能", "自动化",
    ]

    NON_AI_TOPICS = [
        "歼35", "歼-35", "歼 35", "航母", "军舰", "导弹", "军演",
        "军队", "军事", "国防", "军备", "战机", "战斗机",
        "选举", "总统", "首相", "外交部", "外交部发言人",
        "天气", "台风", "地震", "灾害", "事故",
        "明星", "网红", "综艺", "选秀", "演唱会",
    ]

    def check(self, title: str, content: str, platform: str = "toutiao") -> dict:
        """
        返回检查结果
        {"passed": bool, "issues": list[str], "score": int}
        """
        issues = []
        text = title + "\n" + content

        # 0. 内容主题检查 — 非 AI/科技内容拦截
        ai_score = self._calc_ai_relevance(title, content)
        if ai_score < 10:
            issues.append(f"内容主题: 非 AI/科技相关 (相关性评分 {ai_score}/100)")
        elif ai_score < 30:
            issues.append(f"内容主题: AI 相关性偏低 ({ai_score}/100)")

        # 1. 敏感词
        for w in self.SENSITIVE_WORDS:
            if w in text:
                issues.append(f"敏感词: {w}")

        # 2. 平台规则
        for pat, desc in self.BANNED_PATTERNS:
            if re.search(pat, text):
                issues.append(desc)

        # 3. 质量
        if len(title) < 5:
            issues.append("标题过短 <5字")
        if len(title) > 60:
            issues.append("标题过长 >60字")
        if len(content) < 200:
            issues.append("正文过短 <200字")
        cn_count = len(re.findall(r"[\u4e00-\u9fff]", content))
        if cn_count < 50:
            issues.append("中文内容不足")

        score = max(0, 100 - len(issues) * 20)
        return {"passed": len(issues) == 0, "issues": issues, "score": score,
                "ai_relevance": min(100, max(0, ai_score))}

    def _calc_ai_relevance(self, title: str, content: str) -> int:
        """计算内容的 AI 相关性 (0-100)"""
        combined = title + " " + content[:2000]

        # 命中 AI 关键词
        ai_matches = sum(1 for kw in self.AI_KEYWORDS if kw.lower() in combined.lower())
        # 命中非 AI 话题
        non_ai_matches = sum(1 for kw in self.NON_AI_TOPICS if kw in combined)

        # 如果标题直接命中非 AI 话题且 AI 关键词很少，极可能是跑题了
        title_lower = title.lower()
        title_non_ai = sum(1 for kw in self.NON_AI_TOPICS if kw.lower() in title_lower)
        title_ai = sum(1 for kw in self.AI_KEYWORDS if kw.lower() in title_lower)

        if title_non_ai > 0 and title_ai == 0:
            return 0  # 标题明显是非 AI 内容
        if title_non_ai > title_ai:
            return 10  # 标题偏向非 AI

        score = min(100, ai_matches * 15)
        score -= non_ai_matches * 10
        return max(0, score)
