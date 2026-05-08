"""合规审核服务 — 敏感词 + 平台规则 + 质量检查"""
import re


class Reviewer:
    """
    合规审核:
    - 敏感词过滤
    - 平台规则 (头条禁止引流等)
    - 内容质量检查
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

    def check(self, title: str, content: str, platform: str = "toutiao") -> dict:
        """
        返回检查结果
        {"passed": bool, "issues": list[str], "score": int}
        """
        issues = []
        text = title + "\n" + content

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
        return {"passed": len(issues) == 0, "issues": issues, "score": score}
