"""统一 HTTP 客户端 — 基于 httpx，支持超时/重试"""
import httpx
from typing import Optional


class HttpClient:
    """统一 HTTP 请求封装，所有外部 HTTP 调用走这里"""

    def __init__(self, timeout: int = 15, max_retries: int = 2,
                 user_agent: Optional[str] = None):
        self.timeout = timeout
        self.max_retries = max_retries
        self._user_agent = user_agent or (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
        self._client = httpx.Client(
            timeout=timeout,
            follow_redirects=True,
        )

    def get(self, url: str, headers: Optional[dict] = None,
            params: Optional[dict] = None) -> httpx.Response:
        """GET 请求，自动重试"""
        merged_headers = self._build_headers(headers)
        last_error = None

        for attempt in range(self.max_retries + 1):
            try:
                resp = self._client.get(url, headers=merged_headers, params=params)
                resp.raise_for_status()
                return resp
            except (httpx.TimeoutException, httpx.HTTPStatusError) as e:
                last_error = e
                if attempt < self.max_retries:
                    import time
                    time.sleep(1 * (attempt + 1))
                continue

        raise last_error or RuntimeError(f"HTTP GET 失败: {url}")

    def post(self, url: str, json_data: dict,
             headers: Optional[dict] = None) -> httpx.Response:
        """POST JSON 请求"""
        merged_headers = self._build_headers(headers)
        merged_headers["Content-Type"] = "application/json"
        resp = self._client.post(url, json=json_data, headers=merged_headers)
        resp.raise_for_status()
        return resp

    def _build_headers(self, extra: Optional[dict]) -> dict:
        headers = {"User-Agent": self._user_agent}
        if extra:
            headers.update(extra)
        return headers

    def close(self):
        self._client.close()
