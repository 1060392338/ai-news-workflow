"""测试 Agent 核心逻辑 — 不依赖 LLM 的纯函数"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.agents.agents import (
    BaseAgent, WriterAgent, TopicAgent, ComplianceAgent, MainAgent,
    TOPIC_AGENT_PROMPT, WRITER_AGENT_PROMPT,
)
from tests.conftest import MOCK_LLM


class TestBaseAgentParseJson:
    """测试 _parse_json 的各种边缘情况"""

    def setup_method(self):
        self.agent = BaseAgent("test", "你是个测试助手", llm=MOCK_LLM)

    def test_normal_json(self):
        result = self.agent._parse_json('{"key": "value", "num": 42}')
        assert result == {"key": "value", "num": 42}

    def test_double_braces(self):
        """LLM 偶尔输出 {{ }} 双大括号"""
        result = self.agent._parse_json('{{"title": "AI 新闻", "score": 90}}')
        assert result == {"title": "AI 新闻", "score": 90}

    def test_code_block_json(self):
        result = self.agent._parse_json('```json\n{"title": "test", "count": 3}\n```')
        assert result == {"title": "test", "count": 3}

    def test_code_block_no_lang(self):
        result = self.agent._parse_json('```\n{"title": "test"}\n```')
        assert result == {"title": "test"}

    def test_trailing_comma(self):
        result = self.agent._parse_json('{"items": [1, 2, 3,], "name": "test",}')
        assert result == {"items": [1, 2, 3], "name": "test"}

    def test_not_json_fallback(self):
        """完全不能解析时返回 raw 字段"""
        result = self.agent._parse_json("抱歉，无法生成JSON")
        assert "raw" in result

    def test_empty_string(self):
        result = self.agent._parse_json("")
        assert "raw" in result

    def test_whitespace_only(self):
        result = self.agent._parse_json("   ")
        assert "raw" in result


class TestWriterAgentSelfReview:
    """测试写作 Agent 的规则自省"""

    GOOD_ARTICLE = {
        "title": "GPT-5 来了？OpenAI 内部文件泄露这 3 个重磅功能",
        "content": "你相信吗？GPT-5 真的要来了！\n\n"
        "最近，有内部消息透露了 OpenAI 下一代模型的几个重磅功能。"
        "第一，多模态能力大幅提升。不仅能看懂图片，还能理解视频。"
        "第二，推理能力接近人类水平。在多个基准测试上表现优异。"
        "第三，成本大幅降低。API 调用价格可能只有 GPT-4 的一半。"
        "你怎么看？评论区聊聊你的想法吧。"
        "GPT-5 如果真的发布，将会再次引发行业震动。这不仅仅是一次简单的版本迭代，"
        "而是代表了 AI 技术的一次质的飞跃。每次升级都带来了令人惊叹的能力提升。"
        "而 GPT-5 据说将在推理能力上实现重大突破。这意味着 AI 将能够处理更复杂的"
        "逻辑任务，甚至在某些领域超越人类专家。对普通用户来说，最直接的好处就是"
        "能获得更智能的助手服务。无论是写代码、写文章还是做数据分析，AI 都将变得"
        "更加可靠和高效。当然，这也带来了一些担忧，比如工作被取代、信息安全等问题。"
        "但总的来说，技术进步是不可阻挡的。我们与其担心，不如主动学习和适应。"
        "毕竟，每一次技术革命都带来了新的机遇。我们需要拥抱变化，积极学习新技能，"
        "找到人机协作的最佳方式。未来的工作岗位可能会有很大不同，但只要保持学习的"
        "心态，就一定能找到自己的位置。你怎么看？在评论区和我聊一聊吧。",
        "word_count": 630,
    }
    SHORT_TITLE = {
        "title": "AI",
        "content": "这是一篇关于AI的文章。" * 50,
        "word_count": 200,
    }
    NO_HOOK = {
        "title": "关于人工智能发展的几点思考",
        "content": "本文旨在探讨人工智能技术在2026年的发展趋势。" * 50,
        "word_count": 700,
    }
    NO_INTERACTION = {
        "title": "AI 模型性能提升报告",
        "content": "根据最新数据显示。" * 100,
        "word_count": 600,
    }

    def setup_method(self):
        self.agent = WriterAgent(llm=MOCK_LLM)

    def test_good_article_passes(self):
        result = self.agent._self_review(self.GOOD_ARTICLE.copy())
        assert result["self_review"]["passed"] is True
        assert len(result["self_review"]["issues"]) == 0

    def test_short_title_flagged(self):
        result = self.agent._self_review(self.SHORT_TITLE.copy())
        issues = result["self_review"]["issues"]
        assert any("标题过短" in i for i in issues)

    def test_no_hook_flagged(self):
        result = self.agent._self_review(self.NO_HOOK.copy())
        issues = result["self_review"]["issues"]
        assert any("缺少钩子" in i for i in issues)

    def test_no_interaction_flagged(self):
        result = self.agent._self_review(self.NO_INTERACTION.copy())
        issues = result["self_review"]["issues"]
        assert any("缺少互动引导" in i for i in issues)

    def test_title_under_40_chars_ok(self):
        """30-40 字的标题不算长"""
        article = {
            "title": "A" * 35,
            "content": self.GOOD_ARTICLE["content"],
            "word_count": 630,
        }
        result = self.agent._self_review(article)
        title_issues = [i for i in result["self_review"]["issues"] if "标题" in i]
        assert len(title_issues) == 0
