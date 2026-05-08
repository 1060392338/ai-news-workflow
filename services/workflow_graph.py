"""
LangGraph 多 Agent 工作流 — 主Agent+选题Agent+写作Agent+合规Agent

工作流:
  search → topic_collect → main_review_topics
      ├─ approve → writer_draft → compliance_check → main_final_review
      │    ├─ approve → publish → END
      │    └─ revise  → writer_draft (打回重写)
      └─ revise → topic_collect (打回重选)
"""
import json
import time
import concurrent.futures
from functools import wraps
from typing import TypedDict, Optional

from langgraph.graph import StateGraph, START, END

from models.tenant import TenantConfig
from models.hot_item import SearchResult
from models.article import Article, PublishResult

from infrastructure.http_client import HttpClient
from infrastructure.llm_client import LLMClient
from infrastructure.repository import Repository
from infrastructure.searchers.github import GitHubSearcher
from infrastructure.searchers.hn import HackerNewsSearcher
from infrastructure.searchers.arxiv import ArXivSearcher
from infrastructure.searchers.zhihu import ZhiHuSearcher
from infrastructure.searchers.toutiao import TouTiaoSearcher
from infrastructure.searchers.baidu import BaiduSearcher
from infrastructure.searchers.douyin import DouyinSearcher
from infrastructure.searchers.tools import ToolsSearcher
from infrastructure.platform import get_publisher
from services.aggregator import Aggregator
from presentation.feishu_messages import FeishuMessages
from services.agents.agents import (
    TopicAgent, WriterAgent, ComplianceAgent, MainAgent
)


# ============================================================
# 重试工具
# ============================================================
def retryable(max_retries=5, delay=2, backoff=2, fallback=None):
    """重试装饰器: 指数退避 + 自动降级
    - max_retries: 最大重试次数
    - delay: 初始延迟(秒)
    - backoff: 退避因子 (每次*backoff)
    - fallback: 全部失败时的降级返回值
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_error = None
            fn_name = func.__name__
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_error = e
                    if attempt < max_retries:
                        wait = delay * (backoff ** attempt)
                        import random
                        jitter = random.uniform(0.8, 1.2)  # 抖动 ±20%
                        wait *= jitter
                        print(f"  [{fn_name}] 重试 {attempt+1}/{max_retries}"
                              f" (等待{wait:.0f}s): {type(e).__name__}")
                        time.sleep(wait)
            if fallback is not None:
                print(f"  [{fn_name}] ⚠️ 已降级: {last_error}")
                return fallback
            raise last_error
        return wrapper
    return decorator


# ============================================================
# 工作流状态
# ============================================================
class WorkflowState(TypedDict):
    # 元信息
    tenant_id: str
    platform: str
    category: str
    account: str
    stage: str

    # 搜索阶段
    raw_github: list[dict]
    raw_hn: list[dict]
    raw_arxiv: list[dict]
    raw_zhihu: list[dict]
    raw_toutiao: list[dict]

    # 选题阶段
    topic_list: list[dict]         # 选题 Agent 给出的 10 个选题
    selected_topics: list[dict]    # 主 Agent 精选后的选题
    topic_review_result: dict      # 主 Agent 的选题审核结果

    # 写作阶段
    articles: list[dict]           # 写作 Agent 产出的文章
    current_article_index: int     # 当前正在处理第几篇

    # 合规阶段
    compliance_reports: list[dict] # 合规 Agent 的审核报告

    # 终审阶段
    final_reviews: list[dict]      # 主 Agent 的终审结果

    # 发布阶段
    publish_results: list[dict]

    # 交互
    user_input: dict
    errors: list[str]
    _message: str


# ============================================================
# 多 Agent 工作流图
# ============================================================
class AgentWorkflow:
    """多 Agent 协作工作流"""

    def __init__(self, tenant: TenantConfig):
        self.tenant = tenant
        self.http = HttpClient()
        self.repo = Repository(tenant)
        self.aggregator = Aggregator()
        self.messages = FeishuMessages()

        # 搜索器
        self._searchers = {
            "github": GitHubSearcher(self.http),
            "hn": HackerNewsSearcher(self.http),
            "arxiv": ArXivSearcher(self.http),
            "zhihu": ZhiHuSearcher(self.http),
            "toutiao": TouTiaoSearcher(self.http),
            "baidu": BaiduSearcher(self.http),
            "douyin": DouyinSearcher(self.http),
            "tools": ToolsSearcher(self.http),
        }

        # 发布器（通过工厂创建，支持多平台）
        self._publisher = get_publisher(tenant)

        # 各 Agent (共享同一个 LLMClient)
        self._llm = LLMClient()
        self.main_agent = MainAgent(self._llm)
        self.topic_agent = TopicAgent(self._llm)
        self.writer_agent = WriterAgent(self._llm)
        self.compliance_agent = ComplianceAgent(self._llm)

        # 构建图
        self.graph = self._build()

    # ==================== 节点 ====================

    def _node_search(self, state: WorkflowState) -> WorkflowState:
        """并行搜索各平台"""
        print(f"\n{'='*50}")
        print(f"📡 搜索 [{self.tenant.platform} > {self.tenant.category} > {self.tenant.account}]")
        print(f"{'='*50}")

        sources = self.tenant.category_config.search_sources
        kw = self.tenant.category_config.keywords
        errors = []

        with concurrent.futures.ThreadPoolExecutor(max_workers=len(sources)) as pool:
            future_map = {}
            for name in sources:
                s = self._searchers.get(name)
                if s:
                    future_map[pool.submit(self._search_retry, name, s, kw)] = name

            try:
                for f in concurrent.futures.as_completed(future_map, timeout=60):
                    name = future_map[f]
                    try:
                        results = f.result()
                        print(f"  ✅ [{name}] {len(results)} 条")
                        state[f"raw_{name}"] = [r.model_dump() for r in results]
                    except Exception as e:
                        print(f"  ❌ [{name}] {e}")
                        state[f"raw_{name}"] = []
                        errors.append(f"[{name}] {e}")
            except concurrent.futures.TimeoutError:
                print("  ⚠️ 搜索部分超时, 使用已完成的源")
                # 已完成的源的结果已经写入 state, 未完成的标记空
                for f_name in future_map.values():
                    if f"raw_{f_name}" not in state or not state[f"raw_{f_name}"]:
                        state[f"raw_{f_name}"] = state.get(f"raw_{f_name}", [])
                        errors.append(f"[{f_name}] 超时未完成")

        if errors:
            state["errors"] = state.get("errors", []) + errors

        state["stage"] = "topic_collect"
        return state

    @retryable(max_retries=1, delay=1, fallback=[])
    def _search_retry(self, name, searcher, kw) -> list[SearchResult]:
        return searcher.search(kw)

    def _node_topic_collect(self, state: WorkflowState) -> WorkflowState:
        """选题 Agent: 搜集结果 → 筛选 10 个爆款选题"""
        print(f"\n{'='*50}")
        print("📊 选题Agent: 筛选爆款选题")
        print(f"{'='*50}")

        # 从 state 恢复搜索结果
        sources = self.tenant.category_config.search_sources
        all_results = {}
        for s in sources:
            raw = state.get(f"raw_{s}", [])
            all_results[s] = [SearchResult(**d) for d in raw]

        topics = self.topic_agent.select_topics(
            all_results, self.tenant.category_config.keywords
        )

        state["topic_list"] = topics
        print(f"  ✅ 产出 {len(topics)} 个选题")
        for t in topics[:5]:
            print(f"    · {t.get('title','')[:50]}")
        if len(topics) > 5:
            print(f"    · ...还有 {len(topics)-5} 个")

        state["stage"] = "main_review_topics"
        return state

    def _node_main_review_topics(self, state: WorkflowState) -> WorkflowState:
        """主 Agent: 审核选题"""
        print(f"\n{'='*50}")
        print("🧠 主Agent(运营总监): 审核选题")
        print(f"{'='*50}")

        topics = state.get("topic_list", [])
        review = self.main_agent.review_topics(topics)

        state["topic_review_result"] = review
        decision = review.get("decision", "approve")

        if decision == "approve":
            # 选取前 3 个选题（10个太慢，选3个快速发布）
            selected = topics[:min(3, len(topics))]
            state["selected_topics"] = selected
            state["stage"] = "writer_draft"
            print(f"  ✅ 通过! 选定 {len(selected)} 个选题")
            for t in selected:
                print(f"    · {t.get('title','')[:50]}")
        elif decision == "revise":
            state["stage"] = "topic_collect"  # 打回重选
            print(f"  🔄 打回: {review.get('reason','')}")
        else:
            state["stage"] = END
            print(f"  ❌ 否决: {review.get('reason','')}")

        return state

    def _node_writer_draft(self, state: WorkflowState) -> WorkflowState:
        """写作 Agent: 写 1-3 篇文章 + 自我反省"""
        print(f"\n{'='*50}")
        print("✍️ 写作Agent(写稿大师): 写文章+自省")
        print(f"{'='*50}")

        selected = state.get("selected_topics", [])
        if not selected:
            print("  ⚠️ 没有选中的选题，取前 1 个")
            topics = state.get("topic_list", [])
            if topics:
                selected = [topics[0]]
            else:
                return state

        # 被终审打回时可能有反馈
        feedback = ""
        final_reviews = state.get("final_reviews", [])
        if final_reviews:
            last = final_reviews[-1] if isinstance(final_reviews, list) else final_reviews
            if isinstance(last, dict) and last.get("decision") == "revise":
                feedback = f"\n主Agent反馈: {last.get('feedback', '请修改')}\n"

        all_articles = []
        for i, topic in enumerate(selected):
            # 每个选题写 1-2 篇
            count = 2 if i == 0 else 1  # 第一个选题写 2 篇, 其余写 1 篇
            print(f"\n  [选题 #{i+1}] {topic.get('title','')[:40]}")
            articles = self.writer_agent.write_articles(topic, count=count)
            all_articles.extend(articles)

        state["articles"] = all_articles
        state["current_article_index"] = 0
        print(f"\n  ✅ 共完成 {len(all_articles)} 篇文章")
        for i, a in enumerate(all_articles):
            wc = a.get("word_count", 0)
            sr = a.get("self_review", {})
            flag = "✅" if sr.get("passed") else "⚠️"
            print(f"    {flag} #{i+1} {a.get('title','')[:40]} ({wc}字)")

        state["stage"] = "compliance_check"
        return state

    def _node_compliance_check(self, state: WorkflowState) -> WorkflowState:
        """合规 Agent: 审核所有文章"""
        print(f"\n{'='*50}")
        print("🛡️ 合规Agent(审核专家): 审核内容")
        print(f"{'='*50}")

        articles = state.get("articles", [])
        reports = []

        for i, art in enumerate(articles):
            print(f"\n  [{i+1}/{len(articles)}] {art.get('title','')[:40]}")
            report = self.compliance_agent.review(
                art.get("title", ""),
                art.get("content", ""),
                self.tenant.platform,
            )
            reports.append(report)
            verdict = report.get("final_verdict", "通过")
            score = report.get("score", 0)
            flag = "✅" if report.get("passed") else "⚠️"
            print(f"    {flag} {verdict} ({score}分)")
            for issue in report.get("issues", []):
                print(f"      · {issue}")

        state["compliance_reports"] = reports
        state["stage"] = "main_final_review"
        return state

    def _node_main_final_review(self, state: WorkflowState) -> WorkflowState:
        """主 Agent: 终审 — 看完合规报告后做最终决定"""
        print(f"\n{'='*50}")
        print("🧠 主Agent(总监): 终审")
        print(f"{'='*50}")

        articles = state.get("articles", [])
        reports = state.get("compliance_reports", [])

        decisions = self.main_agent.final_review(articles, reports)

        state["final_reviews"] = decisions

        # 提取每个 decision 的字段（兼容 {"raw":...} 情况）
        import re as _re
        def _get_decision(d):
            if "decision" in d and d["decision"]:
                return d["decision"]
            if "raw" in d:
                m = _re.search(r'"decision"\s*:\s*"(approve|revise|reject)"', d["raw"])
                if m:
                    return m.group(1)
                return "reject"
            return d.get("decision", "reject")

        def _get_reason(d):
            if "reason" in d:
                return d.get("reason", "")
            if "raw" in d:
                m = _re.search(r'"reason"\s*:\s*"([^"]+)"', d["raw"])
                if m:
                    return m.group(1)
            return ""

        actual_decisions = [_get_decision(d) for d in decisions]
        approved_count = sum(1 for d in actual_decisions if d == "approve")
        any_revise = any(d == "revise" for d in actual_decisions)

        if approved_count > 0:
            state["stage"] = "publish"
            print(f"  ✅ 通过 {approved_count} 篇，准备发布最优的 1 篇")
        elif any_revise:
            state["stage"] = "writer_draft"  # 打回重写
            print(f"  🔄 部分打回修改")
            for i, d in enumerate(decisions):
                actual = actual_decisions[i]
                if actual == "revise":
                    reason = _get_reason(d)
                    print(f"    #{i+1}: {reason}")
                elif actual == "approve":
                    print(f"    #{i+1}: ✅ 通过")
        else:
            state["stage"] = END
            print(f"  ❌ 全部否决")
            for i, d in enumerate(decisions):
                actual = actual_decisions[i]
                reason = _get_reason(d)
                print(f"    #{i+1}: [{actual}] {reason}")

        return state

    def _node_publish(self, state: WorkflowState) -> WorkflowState:
        """发布到头条"""
        print(f"\n{'='*50}")
        print(f"🚀 发布 [{self.tenant.platform}]")
        print(f"{'='*50}")

        articles = state.get("articles", [])
        decisions = state.get("final_reviews", [])
        if decisions:
            # 有终审记录：只发通过的
            to_publish = []
            for i, art in enumerate(articles):
                if i < len(decisions) and decisions[i].get("decision") == "approve":
                    to_publish.append(art)
        else:
            # 跳过终审：全部发布
            to_publish = articles[:]

        results = []
        for i, art_data in enumerate(to_publish):
            title = art_data.get("title", "")
            print(f"\n  [{i+1}/{len(to_publish)}] 发布: {title[:40]}")
            try:
                article_obj = Article(**art_data)
                result = self._publish_retry(article_obj)
                results.append(result.model_dump())
                status = "✅" if result.success else "❌"
                print(f"  {status} {result.url or result.error}")

                # 写数据库
                from models.article import PublishLog
                log = PublishLog(
                    article_title=article_obj.title,
                    article_content=article_obj.content[:500],
                    success=result.success,
                    url=result.url,
                    error=result.error or "",
                    tenant_id=self.tenant.id,
                    platform=self.tenant.platform,
                    category=self.tenant.category,
                    account=self.tenant.account,
                )
                self.repo.save_publish_log(log)
            except Exception as e:
                print(f"  ❌ 发布失败: {e}")
                results.append({
                    "article_title": title, "success": False, "error": str(e),
                })

        state["publish_results"] = results
        state["stage"] = "__end__"
        return state

    @retryable(max_retries=3, delay=2, fallback=None)
    def _publish_retry(self, article: Article) -> PublishResult:
        result = self._publisher.publish(article, self.tenant.id)
        if not result.success and result.error:
            raise RuntimeError(result.error)
        return result

    # ==================== 构建 ====================

    def _build(self):
        builder = StateGraph(WorkflowState)

        builder.add_node("search", self._node_search)
        builder.add_node("topic_collect", self._node_topic_collect)
        builder.add_node("main_review_topics", self._node_main_review_topics)
        builder.add_node("writer_draft", self._node_writer_draft)
        builder.add_node("compliance_check", self._node_compliance_check)
        builder.add_node("main_final_review", self._node_main_final_review)
        builder.add_node("publish", self._node_publish)

        builder.set_entry_point("search")
        builder.add_edge("search", "topic_collect")
        builder.add_edge("topic_collect", "main_review_topics")
        builder.add_edge("compliance_check", "main_final_review")
        builder.add_edge("publish", END)

        # 主 Agent 审核选题后: approve→writer, revise→topic_collect
        builder.add_conditional_edges(
            "main_review_topics",
            self._route_after_topic_review,
        )

        # 主 Agent 终审后: approve→publish, revise→writer_draft
        builder.add_conditional_edges(
            "main_final_review",
            self._route_after_final_review,
        )

        # 写作完成后→合规审核
        builder.add_edge("writer_draft", "compliance_check")

        return builder.compile()

    def _route_after_topic_review(self, state: WorkflowState):
        stage = state.get("stage", "")
        if stage == "writer_draft":
            return "writer_draft"
        return END

    def _route_after_final_review(self, state: WorkflowState):
        stage = state.get("stage", "")
        if stage == "publish":
            return "publish"
        if stage == "writer_draft":
            return "writer_draft"
        return END

    # ==================== 公开接口 ====================

    def run(self, user_input: Optional[dict] = None) -> dict:
        state = self.repo.load_state() or self._default_state()
        if user_input:
            state["user_input"] = user_input

        try:
            result = self.graph.invoke(state)
        except Exception as e:
            print(f"  ❌ 工作流异常: {e}")
            state["errors"] = state.get("errors", []) + [str(e)]
            self.repo.save_state(state)
            raise

        self.repo.save_state(result)
        return result

    def _default_state(self) -> WorkflowState:
        return {
            "tenant_id": self.tenant.id,
            "platform": self.tenant.platform,
            "category": self.tenant.category,
            "account": self.tenant.account,
            "stage": "search",
            "raw_github": [], "raw_hn": [], "raw_arxiv": [],
            "raw_zhihu": [], "raw_toutiao": [],
            "topic_list": [], "selected_topics": [],
            "topic_review_result": {},
            "articles": [], "current_article_index": 0,
            "compliance_reports": [],
            "final_reviews": [],
            "publish_results": [],
            "user_input": {},
            "errors": [],
            "_message": "",
        }
