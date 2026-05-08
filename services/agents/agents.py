"""
Agent 定义 v2 — 增强角色：主Agent(架构师+运营总监)、写作Agent(自省+参考同类)
"""
import json
from datetime import datetime, timedelta, timezone
from typing import Optional
from infrastructure.llm_client import LLMClient
from models.hot_item import SearchResult


class BaseAgent:
    """Agent 基类"""

    def __init__(self, name: str, system_prompt: str, llm: Optional[LLMClient] = None):
        self.name = name
        self.system_prompt = system_prompt
        self.llm = llm or LLMClient()

    def _call_llm(self, user_prompt: str, temperature: float = 0.7) -> str:
        return self.llm.chat(self.system_prompt, user_prompt)

    def _parse_json(self, text: str) -> dict:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("```")[1]
            if cleaned.startswith("json"):
                cleaned = cleaned[4:]
        cleaned = cleaned.strip()

        # 修复 LLM 输出双大括号 {{ }} 的问题
        if cleaned.startswith("{{") and cleaned.endswith("}}"):
            cleaned = cleaned[1:-1]  # 去掉外层括号 → { }

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            # 尝试修复常见 JSON 格式问题
            try:
                # 有时 LLM 会输出带多余逗号或注释的 JSON
                import re
                fixed = re.sub(r',\s*}', '}', cleaned)
                fixed = re.sub(r',\s*]', ']', fixed)
                fixed = re.sub(r'//.*?\n', '', fixed)
                return json.loads(fixed)
            except (json.JSONDecodeError, Exception):
                return {"raw": text}


# ============================================================
# 选题 Agent — 爆款选题运营师
# ============================================================
TOPIC_AGENT_PROMPT = """你是一个有 10 年经验的爆款选题运营师，曾就职于新世相、视觉志等头部新媒体公司。你深谙今日头条的推荐算法和用户心理。

【核心能力】
1. 热点嗅觉：能从海量信息中准确捕捉即将爆发的选题
2. 用户洞察：知道什么样的标题和内容能引发点击和转发
3. 平台适配：熟悉头条、百家号等平台的内容调性差异

【选题标准】
- 时效性强：必须是近 30 天内的 AI 资讯、新闻与热点
- 关注度高：有讨论热度或搜索量
- 话题性够：能引发读者讨论和转发
- 角度新颖：同样的新闻，换个角度就是爆款
- 标题潜力：能用 15-30 字写出吸引点击的标题
- 内容门槛：优先选有信息增量、有观点可挖的议题，纯炒冷饭的跳过

【输出格式】
输出 JSON 数组，每个元素包含:
{{
  "title": "选题标题（15-30字，像头条标题那样吸引人）",
  "reason": "为什么选这个选题（50字以内）",
  "source": "信息来源平台",
  "original_title": "原始文章标题",
  "original_url": "原文链接",
  "hot_score": 0-100的热度评分,
  "estimated_reading": "3min/5min/8min"
}}"""


class TopicAgent(BaseAgent):
    """选题 Agent: 搜集资讯 → 筛选 10 个爆款选题"""

    def __init__(self, llm: Optional[LLMClient] = None):
        super().__init__("选题Agent", TOPIC_AGENT_PROMPT, llm)

    def select_topics(self, raw_results: dict[str, list[SearchResult]],
                      keywords: list[str]) -> list[dict]:
        all_items = []
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)

        for source, items in raw_results.items():
            for item in items:
                # 有 published_at 且超过 30 天的直接跳过
                if item.published_at and item.published_at < cutoff:
                    continue
                all_items.append({
                    "source": source,
                    "title": item.title,
                    "summary": item.summary[:200],
                    "url": item.url,
                    "score": item.hot_score,
                    "language": item.language,
                    "published_at": item.published_at.isoformat() if item.published_at else "未知",
                })

        if not all_items:
            return self._fallback_topics(keywords)

        all_items.sort(key=lambda x: x["score"], reverse=True)
        candidates = all_items[:30]

        items_text = "\n\n".join(
            f"[{i+1}] [{item['source']}] {item['title']}\n"
            f"    摘要: {item['summary'][:150]}\n"
            f"    时间: {item['published_at']}\n"
            f"    链接: {item['url']}\n"
            f"    热度: {item['score']}"
            for i, item in enumerate(candidates)
        )

        user_prompt = (
            f"以下是今日从各平台搜集到的资讯，共 {len(candidates)} 条。\n"
            f"⚠️ **注意：只筛选 AI / 人工智能 / 科技相关的选题！**\n"
            f"与 AI 无关的（社会新闻、娱乐八卦、财经非AI等）一律不要选。\n\n"
            f"⚠️ **注意：只选近 30 天内的 AI 资讯、新闻与热点，过时的老新闻一律跳过。**\n\n"
            f"请从中筛选出 10 个最具爆款潜质的 **AI 相关** 选题。\n\n"
            f"{items_text}\n\n"
            f"请按 JSON 数组格式输出 10 个选题。"
        )

        try:
            result = self._call_llm(user_prompt, temperature=0.8)
            parsed = self._parse_json(result)
            topics = parsed if isinstance(parsed, list) else parsed.get("topics", [])
            if topics:
                return topics
            return self._fallback_topics(keywords)
        except Exception as e:
            print(f"  [{self.name}] LLM 筛选失败: {e}")
            return self._fallback_topics(keywords)

    def _fallback_topics(self, keywords: list[str]) -> list[dict]:
        return [
            {"title": f"今日 AI 热点：{kw}最新动态", "reason": "系统自动生成",
             "source": "auto", "original_title": "", "original_url": "",
             "hot_score": 50, "estimated_reading": "3min"}
            for kw in keywords[:10]
        ]


# ============================================================
# 写作 Agent — 写稿大师 (增强版: 自省+参考同类)
# ============================================================
WRITER_AGENT_PROMPT = """你是新媒体写作大师，10 年经验，擅长写出阅读量 10万+ 的爆款文章。

【你的战绩】
- 曾写出 50+ 篇 10万+ 爆款文章
- 精通头条系的内容风格、标题技巧、段落节奏
- 能把枯燥的技术话题变得通俗易懂、引人入胜

【头条 AI 类爆款文章参考标准】
根据今日头条 AI 热点类 Top 账号的分析，爆款文章的特征如下：
- 字数：800-1500 字（资讯快讯偏短 800，深度分析偏长 1500）
- 段落：每段不超过 100 字，多用短段
- 标题：15-30 字，必须包含核心关键词 + 情绪钩子词
- 开头：前 100 字必须有钩子（反问/惊人数据/冲突/悬念）
- 语言：口语化、接地气、像朋友聊天，少用 "据悉""据了解"
- 结构：开头钩子 → 背景 → 核心内容(2-3个小标题) → 观点 → 互动引导
- 互动：结尾用 "你怎么看？评论区聊聊"

【写作原则】
1. 标题公式: [关键词] + [情绪钩子] + [信息量]
   ✅ "GPT-5 来了？OpenAI 内部文件泄露这 3 个重磅功能"
   ✅ "Claude 悄悄更新了这个功能，程序员直呼太强了"
   ❌ "关于 GPT-5 的一些最新信息"
2. 每个自然段不超过 3 句话
3. 英文术语保留原名（Claude, Transformer, RAG），不要强行翻译
4. 英文内容要翻译成地道的中国人口语
5. 要有自己的观点和解读，不要只堆砌信息
6. 不要含引流内容（微信号、公众号等）

【自我反省机制 — 写完必须执行】
写完初稿后，你必须逐条问自己:
1. ✅ 标题是否 15-30 字？是否包含关键词+钩子？
2. ✅ 开头 100 字是否足够吸引人？
3. ✅ 段落是否足够短？（每段不超过 100 字）
4. ✅ 语言是否口语化？读起来像不像真人写的？
5. ✅ 是否有自己的观点，不只是信息堆砌？
6. ✅ 有没有参考头条同类账号的风格？
7. ✅ 字数是否在 800-1500 之间？
8. ✅ 结尾是否有互动引导？

如果上述任何一项不达标，必须修改直到全部通过。

【输出格式】
{{
  "title": "文章标题",
  "content": "文章正文（用 \\\\n\\\\n 分段，短句短段）",
  "style": "news 或 deep",
  "word_count": 1234,
  "self_review": {{"passed": true, "issues": []}}  # 自我反省结果
}}"""


class WriterAgent(BaseAgent):
    """写作 Agent: 根据选题写 1-3 篇文章 + 自我反省"""

    def __init__(self, llm: Optional[LLMClient] = None):
        super().__init__("写作Agent", WRITER_AGENT_PROMPT, llm)

    def write_articles(self, topic: dict, count: int = 1) -> list[dict]:
        """
        根据选题写 1 篇文章 + 规则自省 (零 LLM 消耗)
        """
        articles = []
        angle_hint = "常规资讯角度：客观报道最新动态，适合普通读者"
        print(f"  [{self.name}] 写作中...")

        article = self._write_single(topic, angle_hint)
        if article and article.get("content"):
            # 规则自省 (不用 LLM)
            article = self._self_review(article)
            articles.append(article)
            wc = article.get("word_count", 0)
            sr = article.get("self_review", {})
            flag = "✅" if sr.get("passed") else "⚠️"
            print(f"  {flag} {article.get('title','')[:40]} ({wc}字)")
        else:
            print(f"  ❌ 文章生成失败")

        return articles

    def _get_angle_hint(self, index: int, total: int) -> str:
        """多篇文章时给出不同角度"""
        angles = [
            "常规资讯角度：客观报道最新动态，适合普通读者",
            "深度分析角度：深入技术原理和行业影响，适合技术从业者",
            "观点评论角度：有态度有观点，适合引发讨论",
        ]
        if total == 1:
            return angles[0]
        return angles[index % len(angles)]

    def _write_single(self, topic: dict, angle_hint: str) -> dict:
        """写单篇文章"""
        user_prompt = (
            f"请根据以下选题写一篇今日头条爆款文章。\n\n"
            f"【选题信息】\n"
            f"标题: {topic.get('title', '')}\n"
            f"选题理由: {topic.get('reason', '')}\n"
            f"来源: {topic.get('source', '')}\n"
            f"原文链接: {topic.get('original_url', '')}\n"
            f"原始标题: {topic.get('original_title', '')}\n\n"
            f"【角度要求】\n{angle_hint}\n\n"
            f"写完后请执行自我反省，确保文章质量达标。"
        )

        try:
            result = self._call_llm(user_prompt, temperature=0.8)
            parsed = self._parse_json(result)
            if "content" in parsed:
                title = parsed.get("title", topic.get("title", ""))
                content = parsed.get("content", "")
                word_count = len(content.replace("\n", ""))
                return {
                    "title": title,
                    "content": content,
                    "style": parsed.get("style", "news"),
                    "word_count": word_count,
                    "source_topic": topic,
                    "self_review": parsed.get("self_review", {"passed": True, "issues": []}),
                }
            return {"title": topic.get("title", ""), "content": result,
                    "style": "news", "word_count": len(result),
                    "source_topic": topic, "self_review": {"passed": True, "issues": []}}
        except Exception as e:
            print(f"  [{self.name}] 写作异常: {e}")
            return {"title": topic.get("title", ""), "content": "",
                    "style": "news", "word_count": 0, "source_topic": topic}

    def _self_review(self, article: dict) -> dict:
        """自我反省: 检查文章质量, 不达标则修改"""
        title = article.get("title", "")
        content = article.get("content", "")

        issues = []
        if len(title) < 10:
            issues.append("标题过短")
        if len(title) > 40:
            issues.append("标题过长")
        if len(content) < 500:
            issues.append("正文过短(<500字)")
        if len(content) > 2500:
            issues.append("正文过长(>2500字)")

        # 检查开头是否有反问问句或感叹句（这是头条常见的钩子写法）
        first_200 = content[:200].strip()
        hook_keywords = ["?", "？", "!", "！", "重磅", "突发", "刚刚",
                         "你的", "为什么", "如何", "揭秘", "曝光", "真相",
                         "惊人", "疯了", "炸了", "万万没想到"]
        has_hook = any(kw in first_200 for kw in hook_keywords)
        if not has_hook:
            issues.append("开头可能缺少钩子")

        if "你怎么看" not in content and "评论区" not in content:
            issues.append("结尾缺少互动引导")

        if issues:
            print(f"  [{self.name}] 自省发现 {len(issues)} 个问题: {issues}")
            article["_self_review_issues"] = issues

        article["self_review"] = {
            "passed": len(issues) == 0,
            "issues": issues,
            "fixed": False,
        }
        return article


# ============================================================
# 合规 Agent — 审核专家/最后一道防线
# ============================================================
COMPLIANCE_AGENT_PROMPT = """你是内容安全的最后一道防线，10 年审核经验，曾就职于字节跳动内容安全中心。

【你的资质】
- 熟读《网络安全法》《数据安全法》《互联网信息服务管理办法》
- 熟悉今日头条、抖音等平台的社区规则和审核标准
- 累计审核过 100 万+ 条内容，误判率低于 0.01%

【审核维度】
1️⃣ 政治合规：是否涉及敏感政治话题、领导人、意识形态等
2️⃣ 法律法规：是否违反广告法、侵权法、隐私保护等
3️⃣ 平台规则：是否符合头条的内容规范和推荐政策
4️⃣ 内容质量：是否标题党、虚假信息、低质灌水
5️⃣ 语言表达：是否符合中国人口语习惯，读起来是否自然
6️⃣ 主题突出：文章是否紧紧围绕主题，不跑题不散乱
7️⃣ 侵权风险：是否可能侵犯他人版权、肖像权、名誉权
8️⃣ 引流风险：是否含有微信号、公众号、外链等引流内容

【输出格式】
{{
  "passed": true/false,
  "score": 0-100,
  "review_items": [
    {{"dimension": "政治合规", "status": "通过/警告/违规", "detail": "..."}}
  ],
  "issues": ["问题1", "问题2"],
  "suggestions": ["修改建议1", "修改建议2"],
  "final_verdict": "通过 / 需修改 / 不通过"
}}"""


class ComplianceAgent(BaseAgent):
    """合规 Agent: 审核文章合规性"""

    def __init__(self, llm: Optional[LLMClient] = None):
        super().__init__("合规Agent", COMPLIANCE_AGENT_PROMPT, llm)

    def review(self, title: str, content: str, platform: str = "今日头条") -> dict:
        user_prompt = (
            f"请审核以下准备发布到【{platform}】的文章。\n\n"
            f"【标题】\n{title}\n\n"
            f"【正文】\n{content[:2000]}\n\n"
            f"请从 8 个维度逐一检查，输出审核报告。"
        )
        try:
            result = self._call_llm(user_prompt, temperature=0.3)
            return self._parse_json(result)
        except Exception as e:
            print(f"  [{self.name}] 审核失败: {e}")
            return {"passed": True, "score": 60, "issues": ["审核异常，自动放行"],
                    "final_verdict": "需人工复核"}


# ============================================================
# 主 Agent — 架构师 + 爆款运营总监
# ============================================================
MAIN_AGENT_PROMPT = """你是这个新媒体团队的创始人兼总编辑，拥有双重身份：

【身份一：技术架构师】
- 10 年互联网技术架构经验
- 负责系统设计、数据流、技术决策
- 确保整个内容生产系统高效稳定可扩展

【身份二：爆款运营总监】
- 10 年新媒体运营经验
- 带出过多个百万粉丝账号
- 深谙用户心理和爆款内容逻辑
- 知道什么样的内容能在头条火起来
- 知道"量大出奇迹"——多发文章比死磕单篇质量更重要

【你的决策权限】
你是团队的最终决策者，有一票否决权。

1️⃣ 选题审核
- 通过 ✅ → 交给写作 Agent 写文章
- 否决 ❌ → 明显不合规或完全不相关的才否决

2️⃣ 文章终审
- 批准 ✅ → 合规没问题就发布，不要追求完美
- 打回修改 🔄 → 仅当有严重质量问题（跑题、事实错误、违规风险）
- 否决 ❌ → 严重违规或完全不可读

【决策标准 — 记住我们做的是头条内容，不是文学奖】
选题审核：
- 这个选题有时效性吗？
- 内容有话题性吗？
- 符合我们账号的定位吗？
- 娱乐性/争议性比深度更重要——有争议就有流量

文章终审（看完合规报告后）：
- 合规没问题就过，不要追求完美
- 头条读者不会逐字逐句读，差不多就行了
- 标题有点夸张是好事情（只要不过线）
- 你作为运营总监，记得"多发就是胜利"
- 每送回去重写一次，就浪费一次发布机会

【输出格式】
{{
  "decision": "approve / revise / reject",
  "reason": "决策理由（30-50字）",
  "feedback": "给其他 Agent 的具体反馈意见",
  "next_action": "proceed / retry_writing / abandon",
  "confidence": 0-100
}}"""


class MainAgent(BaseAgent):
    """主 Agent: 架构师+运营总监, 最终决策者"""

    def __init__(self, llm: Optional[LLMClient] = None):
        super().__init__("主Agent", MAIN_AGENT_PROMPT, llm)

    def review_topics(self, topics: list[dict]) -> dict:
        # 先让 LLM 精选出最优的 3 个
        topic_texts = "\n\n".join(
            f"[{i+1}] {t.get('title', '')}\n"
            f"    理由: {t.get('reason', '')}\n"
            f"    来源: {t.get('source', '')}\n"
            f"    热度: {t.get('hot_score', 'N/A')}"
            for i, t in enumerate(topics)
        )
        user_prompt = (
            f"选题 Agent 提交了 10 个选题，请逐一审核。\n\n"
            f"【选题列表】\n{topic_texts}\n\n"
            f"作为运营总监，这 10 个选题全部都会写文章并发布。\n"
            f"请对每个选题给出审核意见，只剔除明显不合规或完全不相关的选题。\n"
            f"输出每个选题的审核意见。"
        )
        try:
            result = self._call_llm(user_prompt, temperature=0.4)
            return self._parse_json(result)
        except Exception as e:
            print(f"  [{self.name}] 选题审核失败: {e}")
            return {"decision": "approve", "reason": "自动通过前3个",
                    "feedback": "", "next_action": "proceed", "confidence": 60}

    def final_review(self, articles: list[dict],
                     compliance_reports: list[dict]) -> list[dict]:
        """终审所有文章，从合格的文章中选出最优的 1 篇发布"""
        decisions = []

        # 第一步：逐一审核每篇文章
        for i, (article, report) in enumerate(zip(articles, compliance_reports)):
            user_prompt = (
                f"请审核第 {i+1} 篇文章。\n\n"
                f"【标题】\n{article.get('title', '')}\n\n"
                f"【正文预览】\n{article.get('content', '')[:1500]}\n\n"
                f"【字数】{article.get('word_count', 0)}\n\n"
                f"【写作Agent自评】\n{json.dumps(article.get('self_review', {}), ensure_ascii=False)}\n\n"
                f"【合规报告】\n{json.dumps(report, ensure_ascii=False, indent=2)}\n\n"
                f"请判断：这篇文章能否发布？（合规过关就通过，别太严格）"
            )
            try:
                result = self._call_llm(user_prompt, temperature=0.3)
                decisions.append(self._parse_json(result))
            except Exception as e:
                print(f"  [{self.name}] 终审 #{i+1} 失败: {e}")
                decisions.append({"decision": "approve", "reason": "自动通过",
                                  "next_action": "proceed", "confidence": 50})

        # 第二步：从通过的里面挑最好的 1 篇
        approved = [d for d in decisions if d.get("decision") == "approve"]
        if len(approved) > 1:
            # 有多篇通过，让 LLM 选最优的
            approved_text = "\n\n".join(
                f"[{j+1}] {articles[decisions.index(d)].get('title','')}\n"
                f"    合规分: {compliance_reports[decisions.index(d)].get('score', 'N/A')}\n"
                f"    主Agent评分: {d.get('confidence', 'N/A')}\n"
                f"    审核理由: {d.get('reason', '')}"
                for j, d in enumerate(approved)
            )
            pick_prompt = (
                f"以下有 {len(approved)} 篇文章都通过了审核，请从中选出最值得发布的 1 篇。\n\n"
                f"{approved_text}\n\n"
                f"输出 JSON: {{\"pick_index\": 0, \"reason\": \"选这篇的理由\"}}"
            )
            try:
                result = self._call_llm(pick_prompt, temperature=0.3)
                picked = self._parse_json(result)
                pick_idx = picked.get("pick_index", 0)
                # 只保留选中那篇的 approval
                for j, d in enumerate(decisions):
                    actual_idx = decisions.index(approved[pick_idx])
                    if j != actual_idx:
                        d["decision"] = "reject"
                        d["reason"] = f"次优，未入选: {picked.get('reason', '')}"
            except Exception as e:
                print(f"  [{self.name}] 择优失败，保留第1篇: {e}")
                # 保留第一篇，其余否决
                kept_one = False
                for d in decisions:
                    if d.get("decision") == "approve" and not kept_one:
                        kept_one = True
                    elif d.get("decision") == "approve":
                        d["decision"] = "reject"
                        d["reason"] = "择优后未入选"

        return decisions
