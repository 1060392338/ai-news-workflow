"""测试工作流核心逻辑 — 路由、重试、解析回退"""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.workflow_graph import AgentWorkflow, retryable
from models.tenant import TenantConfig
from models.article import Article


class TestRetryable:
    """测试重试装饰器"""

    def test_success_first_try(self):
        call_count = 0

        @retryable(max_retries=3)
        def func():
            nonlocal call_count
            call_count += 1
            return "ok"

        result = func()
        assert result == "ok"
        assert call_count == 1

    def test_retry_then_success(self):
        call_count = 0

        @retryable(max_retries=3, delay=0.01)
        def func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("not yet")
            return "finally ok"

        result = func()
        assert result == "finally ok"
        assert call_count == 3

    def test_all_retries_fail_without_fallback(self):
        call_count = 0

        @retryable(max_retries=2, delay=0.01)
        def func():
            nonlocal call_count
            call_count += 1
            raise RuntimeError("always fail")

        import pytest
        with pytest.raises(RuntimeError, match="always fail"):
            func()
        assert call_count == 3

    def test_fallback_on_all_failures(self):
        @retryable(max_retries=2, delay=0.01, fallback="fallback_value")
        def func():
            raise ValueError("fail")

        result = func()
        assert result == "fallback_value"


class TestWorkflowRouting:
    """测试工作流路由逻辑"""

    @patch('services.workflow_graph.get_publisher')
    @patch('services.workflow_graph.Repository')
    @patch('services.workflow_graph.LLMClient')
    def _make_wf(self, mock_llm, mock_repo, mock_pub, stage=None):
        config = TenantConfig(
            id="test", platform="测试", category="测试", account="测试",
        )
        wf = AgentWorkflow(config)
        # 注入 mock LLM
        wf._llm = MagicMock()
        return wf

    def test_route_after_topic_review_to_writer(self):
        wf = self._make_wf()
        result = wf._route_after_topic_review({"stage": "writer_draft"})
        assert result == "writer_draft"

    def test_route_after_topic_review_to_end(self):
        wf = self._make_wf()
        result = wf._route_after_topic_review({"stage": "publish"})
        assert result == "__end__"

    def test_route_after_final_review_to_publish(self):
        wf = self._make_wf()
        result = wf._route_after_final_review({"stage": "publish"})
        assert result == "publish"

    def test_route_after_final_review_to_rewrite(self):
        wf = self._make_wf()
        result = wf._route_after_final_review({"stage": "writer_draft"})
        assert result == "writer_draft"

    def test_route_after_final_review_to_end(self):
        wf = self._make_wf()
        result = wf._route_after_final_review({"stage": "__end__"})
        assert result == "__end__"


class TestWorkflowDefaultState:
    """测试默认状态初始化"""

    @patch('services.workflow_graph.get_publisher')
    @patch('services.workflow_graph.Repository')
    @patch('services.workflow_graph.LLMClient')
    def test_default_state_isolated_lists(self, mock_llm, mock_repo, mock_pub):
        config = TenantConfig(
            id="test", platform="测试", category="测试", account="测试",
        )
        wf = AgentWorkflow(config)
        state = wf._default_state()

        assert state["raw_github"] is not state["raw_hn"]
        assert state["raw_arxiv"] is not state["raw_toutiao"]
        assert state["topic_list"] is not state["articles"]
        assert state["errors"] is not state["publish_results"]

    @patch('services.workflow_graph.get_publisher')
    @patch('services.workflow_graph.Repository')
    @patch('services.workflow_graph.LLMClient')
    def test_default_state_initial_stage(self, mock_llm, mock_repo, mock_pub):
        config = TenantConfig(
            id="test", platform="测试", category="测试", account="测试",
        )
        wf = AgentWorkflow(config)
        state = wf._default_state()
        assert state["stage"] == "search"


class TestWorkflowNodeConnections:
    """测试图节点完整性"""

    @patch('services.workflow_graph.get_publisher')
    @patch('services.workflow_graph.Repository')
    @patch('services.workflow_graph.LLMClient')
    def test_graph_has_all_nodes(self, mock_llm, mock_repo, mock_pub):
        config = TenantConfig(
            id="test", platform="测试", category="测试", account="测试",
        )
        wf = AgentWorkflow(config)
        nodes = list(wf.graph.nodes.keys())
        expected = {"__start__", "search", "topic_collect",
                   "main_review_topics", "writer_draft",
                   "compliance_check", "main_final_review", "publish"}
        for n in expected:
            assert n in nodes, f"缺少节点: {n}"
