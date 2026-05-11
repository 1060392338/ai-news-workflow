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

        # 内层 {{ }} → { }（LLM 会在嵌套 JSON 里也输出双括号）
        cleaned = cleaned.replace("{{", "{").replace("}}", "}")

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            import re
            try:
                fixed = re.sub(r',\s*}', '}', cleaned)
                fixed = re.sub(r',\s*]', ']', fixed)
                fixed = re.sub(r'//.*?\n', '', fixed)
                return json.loads(fixed)
            except (json.JSONDecodeError, Exception):
                # 🔧 终极降级：从文本中提取最长的 JSON 对象
                try:
                    start = cleaned.index('{')
                    end = cleaned.rindex('}') + 1
                    candidate = cleaned[start:end]
                    return json.loads(candidate)
                except (ValueError, json.JSONDecodeError):
                    return {"raw": text}


# ============================================================
# 选题 Agent — AI科技选题运营师 (严格定位)
# ============================================================
TOPIC_AGENT_PROMPT = """你是一个专注 AI / 科技领域的选题运营师，在垂直科技号干了 8 年。你只对 AI 和前沿科技感兴趣，其他话题你自动屏蔽。

【账号定位：只做 AI 与前沿科技】
这个账号是 **AI/科技垂直号**，不是新闻号也不是综合号。每篇内容必须跟 AI 或前沿科技直接相关。跟 AI 无关的一律不选，再火也不选。

✅ 可以选的（必须满足：主角是 AI / 或 AI 改变了该领域）：
- AI 行业资讯：大模型更新、AI 公司动态、行业新闻
- AI 工具：上手体验、对比评测、实际效果（Cursor、Claude、Copilot 等）
- AI 技术科普：Agent、MCP、RAG、多模态等——用大白话讲清楚
- AI 编程与开发者：GitHub 热门 AI 项目、代码工具、开源模型
- AI + X：AI 在某个领域的突破（AI 写代码、AI 画图、AI 做视频、AI 做科研）
- 科技商业：芯片（只限跟 AI 算力相关）、AI 创业、AI 投融资
- 社会热点中与 AI 强相关的话题

❌ 坚决不能选的（触犯任意一条立即否决）：
- 🚫 **纯军事、纯国防**（歼35、航母、导弹、军演……跟 AI 无关就不选）
- 🚫 **纯政治、外交**
- 🚫 **纯娱乐八卦**（明星、网红、综艺）
- 🚫 **纯社会新闻**（交通事故、天气灾害、刑事案件——除非有 AI 角度）
- 🚫 **纯财经非科技**（股市涨跌、房价、经济政策——除非跟 AI 强相关）
- 🚫 **体育、教育政策、医疗（非 AI 相关）**

【选择标准】
- 必须是近 30 天内的资讯或动态
- 有信息增量：不是简单复述新闻，要有解读、观点、角度
- 读者能看懂：再复杂的话题也得能让普通读者理解
- 有讨论价值：能引发评论区讨论、分享、争论

【输出格式】
输出 JSON 数组，每个元素包含:
{{
  "title": "选题标题（15-30字，像头条标题那样吸引人）",
  "reason": "为什么选这个选题，以及它跟 AI 有什么关系（50字以内）",
  "source": "信息来源平台",
  "original_title": "原始文章标题（如果来自搜索）",
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
            f"⚠️ **这个账号是 AI/科技垂直号，只做 AI 和前沿科技内容！**\n"
            f"⚠️ **跟 AI 无关的内容（包括但不限于：纯军事、纯政治、纯娱乐、纯社会新闻）一律不选！！**\n\n"
            f"⚠️ **只选近 30 天内的 AI 资讯、新闻与热点，过时的老新闻一律跳过。**\n\n"
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
# 写作 Agent — 真人写手 (去 AI 味 + 配图建议)
# ============================================================
WRITER_AGENT_PROMPT = """你是一个在科技媒体干了 8 年的老编辑，现在做自己的头条号。你觉得现在 AI 写的文章太假了，满嘴"据悉""据了解""值得关注的是"，一看就是机器写的。你要写出真人味。

【你的写作风格：像北京大院的哥们在跟你聊天】
- 别装专业：别用"综上所述""值得注意的是""从长远来看"
- 直接说人话："我觉得""说实话""你猜怎么着"
- 该吐槽就吐槽：有点小情绪、小观点，别端着
- 短句短段：一段别超过 3 句话，读起来轻快
- 像在跟朋友吹水：但别太飘，信息量得扎实

【实际例子——感受一下】
✅ 像这样：
"前两天我试了试 Claude 那个新功能，说实话，有点失望。不是说不好用，但它吹的牛太大了。"
"GPT-5 的传言满天飞，但真正让我在意的是另一件事——Google 偷偷放了个大招。"
"这篇文章来自 AI 辅助翻译，翻译一下就是：以后你不需要翻译软件了。"
"你要问我今年最值得关注的 AI 工具是哪个？不是 ChatGPT，也不是 Claude，而是一个你大概率没听过的东西——"

❌ 别这样：
"据悉，OpenAI 于近日发布了其最新研究成果。该模型在多项基准测试中表现优异。这标志着人工智能领域的又一次重大突破。"
"值得关注的是，该技术在实际应用场景中展现出了巨大潜力。从长远来看，将对行业发展产生深远影响。"

【文章结构——固定的爆款配方】
1. 开头钩子（100 字内）
   反问 / 惊人数据 / 小故事 / 制造冲突或悬念
   "你有没有想过，如果 XXX 会怎样？"
   "刚看到一个数据，吓了我一跳……"

2. 正文（600-1000 字）
   2-3 个短标题分段，每段讲清楚一件事
   别追求全面，把一件事讲透就够了

3. 结尾（50-100 字）
   总结观点 + 抛给读者
   "你觉得呢？评论区聊聊"
   "说实话，这种事我是第一次见，你说靠谱吗？"

【配图要求——每篇文章必须配图】
每段正文后，插入图片占位符:
![图片说明: 写一句描述这张图片应该是什么]
![图片说明: 一张展示 AI 工具界面的截图]
![图片说明: 新闻相关的人物或产品照片]

规则：
- 每 200-400 字至少插入一张图片占位符
- 图片说明要具体：告诉读者这张图应该是啥
- 同类文章配图风格：科技产品截图、数据图表、人物照片、场景示意图
- 文章开头最好有 1 张吸引眼球的配图

【除 AI 味的额外要求】
- 不要用"随着""据悉""据了解""值得一提的是""值得一提的是""总的来说"
- 不要用"在...的背景下""从...出发""基于..."
- 能用"说"就别用"表示指出强调"
- 能用"但是"就别用"然而"
- 能用"比如"就别用"例如"
- 第一人称可以："我觉得""我试了""我发现"
- 英文术语保留（Transformer, RAG, Agent），但不必要的不留

【自我反省】写完检查一遍：
- 读起来像不像真人写的？会不会被一眼看出是 AI？
- 有没有那些 AI 常用词（据悉、综上所述、值得注意的是）
- 字数 600-1500 字，别写太长
- 图片占位符加没加？
- 开头能不能抓住人？

【输出格式】
{{
  "title": "文章标题（15-30字）",
  "content": "文章正文（用 \\n\\n 分段）",
  "style": "news",
  "word_count": 1234,
  "images": ["图片说明1", "图片说明2"],
  "self_review": {{"passed": true, "issues": []}}
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
                    "images": parsed.get("images", []),
                    "self_review": parsed.get("self_review", {"passed": True, "issues": []}),
                }
            print(f"  [{self.name}] JSON解析失败，已降级提取")
            # 如果 raw 字段存在，说明完全失败 — 不要用原始文本当正文
            if "raw" in parsed:
                print(f"  [{self.name}] ⚠️ 解析彻底失败，丢弃原始文本（含JSON模板）")
                return {"title": topic.get("title", ""), "content": "",
                        "style": "news", "word_count": 0,
                        "source_topic": topic,
                        "self_review": {"passed": False, "issues": ["JSON解析失败"]}}
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
COMPLIANCE_AGENT_PROMPT = """你是内容安全的最后一道防线，也是最**严格的审核官**。10 年审核经验，不放过任何一条不合规的内容。

【必查项 — 每一条都过，有一条不达标就毙】

1️⃣ 主题相关性：这篇内容跟 AI / 前沿科技相关吗？如果文章核心话题跟 AI 没有任何关系（纯军事、纯政治、纯娱乐、纯社会新闻），直接不通过！
2️⃣ 政治合规：是否涉及敏感政治话题、领导人、意识形态等
3️⃣ 法律法规：是否违反广告法、侵权法、隐私保护等
4️⃣ 平台规则：是否符合头条的内容规范和推荐政策
5️⃣ 内容质量：是否标题党、虚假信息、低质灌水
6️⃣ 语言表达：是否符合中国人口语习惯，读起来是否自然
7️⃣ 侵权风险：是否可能侵犯他人版权、肖像权、名誉权
8️⃣ 引流风险：是否含有微信号、公众号、外链等引流内容

【一票否决规则】
主题不相关（跟 AI/科技无关）→ ❌ 不通过 — 不解释
政治违规 → ❌ 不通过
硬广告/引流 → ❌ 不通过
明显的标题党（正文跟标题完全不符）→ ❌ 不通过

【输出格式】
{{
  "passed": true/false,
  "score": 0-100,
  "review_items": [
    {{"dimension": "主题相关性", "status": "通过/警告/违规", "detail": "..."}},
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
- 但最重要的：**我们做的是 AI/科技垂直号，不是综合新闻号**

【你的决策权限】
你是团队的最终决策者，有一票否决权。

1️⃣ 选题审核
- 通过 ✅ → 符合 AI/科技定位，交给写作 Agent 写文章
- 否决 ❌ → 跟 AI/科技无关的选题（军事、政治、娱乐、社会新闻等）一律否决，不管有多火

2️⃣ 文章终审
- 批准 ✅ → 合规没问题、内容跟 AI 相关就发布，不要追求完美
- 打回修改 🔄 → 仅当有严重质量问题（跑题、事实错误、违规风险）
- 否决 ❌ → 严重违规或完全不可读

【决策标准 — 记住我们做的是 AI 科技号】
选题审核：
- 这个选题跟 AI 或前沿科技有关吗？
- 核心话题是 AI 吗？还是只是在蹭热度？
- 有没有讨论价值？
- 符合我们账号的 AI/科技定位吗？

文章终审（看完合规报告后）：
- 合规没问题就过，不要追求完美
- 头条读者不会逐字逐句读，差不多就行了
- 标题有点夸张是好事情（只要不过线）
- 多发就是胜利，每退回去一次就浪费一次发布机会

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
