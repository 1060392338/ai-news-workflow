"""LLM 客户端 — 基于 LangChain ChatOpenAI，带指数退避重试"""
import os
import time
import random
from typing import Optional
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage


class LLMClient:
    """统一 LLM 调用封装，支持重试 + 指数退避"""

    def __init__(self, model: str = "deepseek-chat",
                 temperature: float = 0.8,
                 max_tokens: int = 3000,
                 max_retries: int = 5):
        api_key = self._load_api_key()
        self._llm = ChatOpenAI(
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            api_key=api_key,
            base_url="https://api.deepseek.com/v1",
            max_retries=0,  # 我们自己控制重试
            timeout=120,  # 请求超时 120s
        )
        self.max_retries = max_retries

    def chat(self, system_prompt: str, user_prompt: str) -> str:
        """调用 LLM，带指数退避重试 (应对 503)"""
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]

        last_error = None
        for attempt in range(self.max_retries + 1):
            try:
                result = self._llm.invoke(messages)
                return result.content.strip()
            except Exception as e:
                last_error = e
                err_str = str(e)
                is_503 = "503" in err_str or "too busy" in err_str.lower() or "overloaded" in err_str.lower()
                if attempt < self.max_retries:
                    if is_503:
                        # 503: 指数退避 2→4→8→16→32s + 抖动
                        wait = (2 ** attempt) * random.uniform(0.8, 1.2)
                        print(f"  [LLM] API 繁忙, 等待{wait:.0f}s后重试 ({attempt+1}/{self.max_retries})")
                    else:
                        wait = 2 * random.uniform(0.8, 1.2)
                        print(f"  [LLM] 错误 {type(e).__name__}, 等待{wait:.0f}s后重试 ({attempt+1}/{self.max_retries})")
                    time.sleep(wait)
                else:
                    print(f"  [LLM] 重试{self.max_retries}次均失败: {e}")

        raise last_error or RuntimeError("LLM 调用失败")

    def _load_api_key(self) -> str:
        """从 Hermes 配置读取 API key"""
        config_path = os.path.expanduser("~/.hermes/config.yaml")
        try:
            import yaml
            with open(config_path, "r") as f:
                cfg = yaml.safe_load(f)

            # custom_providers 是一个列表：[{name, api_key, ...}]
            for provider in cfg.get("custom_providers", []):
                key = provider.get("api_key", "")
                if key and key.startswith("sk-"):
                    return key
            # fallback: providers 字典
            for provider in cfg.get("providers", {}).values():
                key = provider.get("api_key", "")
                if key and key.startswith("sk-"):
                    return key
            # fallback: 扫所有字段找 sk-
            import json as _json
            dump = _json.dumps(cfg)
            idx = dump.find("sk-")
            if idx >= 0:
                return dump[idx:idx+40].split('"')[0]
        except Exception:
            pass
        raise RuntimeError("未找到 DeepSeek API key（检查 ~/.hermes/config.yaml）")
