"""pytest 全局配置 — mock LLMClient 避免依赖真实 API"""
from unittest.mock import MagicMock
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# 创建一个全局 mock LLM 实例
MOCK_LLM = MagicMock()
MOCK_LLM.chat.return_value = '{"result": "ok"}'
