"""
今日头条发布器 — Chrome DevTools Protocol (CDP) 直连
完全替代 DrissionPage，使用 Chrome CDP WebSocket 协议

核心流程：
  1. 连接已有 Chrome（port 9222）
  2. 通过 CDP 创建新标签页、导航到发布页
  3. 检查登录状态（用户数据目录持久化）
  4. 通过页内 XHR 直调 publish API（save=1, status=2 = 提交审核）
  5. 校验 API 返回的 message 是否为"提交成功"
"""
import json
import os
import re
import time
from pathlib import Path

import requests
import websocket

from models.article import Article, PublishResult
from models.tenant import TenantConfig
from infrastructure.platform import register


class CDPClient:
    """Chrome DevTools Protocol 客户端 — 比 DrissionPage 更轻量稳定"""

    def __init__(self, port=9222):
        self.port = port
        self._browser_ws_url = None
        self._tab_id = None
        self._tab_ws_url = None
        self._tab_ws = None
        self._msg_id = 0

    def connect(self):
        """连接到 Chrome 浏览器"""
        # 获取浏览器 WebSocket URL
        version = requests.get(
            f"http://localhost:{self.port}/json/version", timeout=5
        ).json()
        self._browser_ws_url = version["webSocketDebuggerUrl"]

        # 创建新标签页
        bws = websocket.create_connection(self._browser_ws_url, timeout=10)
        bws.send(
            json.dumps(
                {
                    "id": 1,
                    "method": "Target.createTarget",
                    "params": {"url": "about:blank", "newWindow": False},
                }
            )
        )
        while True:
            resp = json.loads(bws.recv())
            if resp.get("id") == 1:
                self._tab_id = resp["result"]["targetId"]
                break
        bws.close()

        # 获取标签页 WebSocket URL
        tabs = requests.get(f"http://localhost:{self.port}/json", timeout=5).json()
        for t in tabs:
            if t["id"] == self._tab_id:
                self._tab_ws_url = t["webSocketDebuggerUrl"]
                break

        # 连接标签页
        self._tab_ws = websocket.create_connection(self._tab_ws_url, timeout=15)
        # 启用 Page 域
        self._send("Page.enable")
        return self

    def _send(self, method, params=None):
        """发送 CDP 命令并等待响应"""
        self._msg_id += 1
        msg = {"id": self._msg_id, "method": method}
        if params:
            msg["params"] = params
        self._tab_ws.send(json.dumps(msg))
        while True:
            resp = json.loads(self._tab_ws.recv())
            if resp.get("id") == self._msg_id:
                return resp.get("result")

    def navigate(self, url: str):
        """导航到指定 URL"""
        result = self._send("Page.navigate", {"url": url})
        return result

    def get_url(self) -> str:
        """获取当前页面 URL"""
        result = self._send(
            "Runtime.evaluate",
            {
                "expression": "window.location.href",
                "returnByValue": True,
            },
        )
        return result["result"]["value"]

    def evaluate(self, js_code: str) -> str:
        """在页面中执行 JavaScript，返回结果字符串"""
        result = self._send(
            "Runtime.evaluate",
            {
                "expression": js_code,
                "returnByValue": True,
                "awaitPromise": True,
            },
        )
        if "exceptionDetails" in result:
            exc = result["exceptionDetails"]
            desc = exc.get("text", "") or exc.get("exception", {}).get("description", "")
            raise RuntimeError(f"JS 执行异常: {desc}")
        val = result["result"].get("value", "")
        return val

    def wait_for_page(self, seconds=3):
        """等待页面加载"""
        time.sleep(seconds)

    def close(self):
        """关闭连接"""
        if self._tab_ws:
            try:
                self._tab_ws.close()
            except Exception:
                pass


@register("toutiao")
class TouTiaoPublisher:
    """CDP + API 直调发布到今日头条"""

    def __init__(self, tenant: TenantConfig):
        self.tenant = tenant
        self._cdp = None

    # ── 公开入口 ──────────────────────────────────────────────

    def publish(self, article: Article, tenant_id: str) -> PublishResult:
        title = article.title
        content = article.content

        # 头条标题限制 2-30 字，自动截断
        if len(title) > 30:
            print(f"  ⚠️ [头条发布] 标题过长({len(title)}字)，截断到30字")
            title = title[:30]
        if len(title) < 2:
            print(f"  ⚠️ [头条发布] 标题过短，使用默认标题")
            title = "AI前沿速递"

        print(f"\n  [头条发布] 《{title}》({self.tenant.account})")
        print(f"  [头条发布] 正文 {len(content)} 字")

        try:
            self._launch()
            self._ensure_logged_in()
            result = self._api_publish(title, content)
            self._cleanup()
            return result
        except Exception as e:
            err = f"{type(e).__name__}: {e}"
            print(f"  ❌ [头条发布] 失败: {err}")
            self._cleanup()
            return PublishResult(
                article_title=title, success=False,
                error=err, tenant_id=tenant_id,
            )

    # ── 浏览器管理 ──────────────────────────────────────────

    def _launch(self):
        """连接已有 Chrome（port 9222）"""
        print("  [头条发布] 连接 Chrome (CDP port 9222)...")
        self._cdp = CDPClient(port=9222).connect()
        print("  ✅ [头条发布] Chrome 已连接")

    def _ensure_logged_in(self):
        """确保已登录：用户数据持久化 + 扫码兜底"""
        cdp = self._cdp

        # 导航到发布页
        print("  [头条] 检查登录状态...")
        cdp.navigate("https://mp.toutiao.com/profile_v4/graphic/publish")
        cdp.wait_for_page(4)

        current_url = cdp.get_url()
        if "passport" not in current_url and "login" not in current_url:
            print("  ✅ [头条] 登录态有效（用户数据持久化）")
            return

        # 未登录 → 弹出登录页，等待扫码
        print("  ⚠️ [头条] 登录态已过期，请扫码登录...")
        cdp.navigate("https://mp.toutiao.com/auth/page/login")
        cdp.wait_for_page(2)

        print("  ┌─────────────────────────────────────────────┐")
        print("  │  请在打开的浏览器窗口中扫码登录             │")
        print("  │  登录后会自动继续                            │")
        print("  └─────────────────────────────────────────────┘")

        for i in range(120, 0, -1):
            time.sleep(1)
            current_url = cdp.get_url()
            if "passport" not in current_url and "login" not in current_url:
                print(f"  ✅ [头条] 扫码登录成功! ({120-i}s)")
                # 回到发布页
                cdp.navigate("https://mp.toutiao.com/profile_v4/graphic/publish")
                cdp.wait_for_page(3)
                return
            if i % 15 == 0:
                print(f"  ⏳ 等待扫码中 ({i}s)...")

        raise RuntimeError("扫码登录超时（120s），请手动扫码后重试")

    # ── API 发布 ──────────────────────────────────────────

    def _api_publish(self, title: str, content: str) -> PublishResult:
        """通过页面 JavaScript XHR 调 publish API (save=1,status=2)"""
        cdp = self._cdp

        # 将正文转为 HTML 段落
        paras = [p.strip() for p in content.strip().split("\n\n") if p.strip()]
        html_content = "".join(f"<p>{p}</p>" for p in paras)

        print("  [头条发布] 通过 API 提交发布...")

        # 用 JS 注入的方式传到浏览器
        js_code = f"""
        (() => {{
            try {{
                var fd = new URLSearchParams();
                fd.append('title', {json.dumps(title)});
                fd.append('content', {json.dumps(html_content)});
                fd.append('source', '29');
                fd.append('save', '1');
                fd.append('status', '2');
                fd.append('is_refute_rumor', '0');
                fd.append('article_ad_type', '3');
                fd.append('pgc_feed_covers', '[]');
                fd.append('draft_form_data', JSON.stringify({{coverType: 2}}));
                fd.append('extra', JSON.stringify({{
                    content_source: 100000000402,
                    content_word_cnt: {len(content)},
                    is_multi_title: 0,
                    sub_titles: [],
                    gd_ext: {{
                        entrance: '',
                        from_page: 'publisher_mp',
                        enter_from: 'PC',
                        device_platform: 'mp',
                        is_message: 0,
                        tuwen_wtt_transfer_switch: '1'
                    }}
                }}));

                var xhr = new XMLHttpRequest();
                xhr.open('POST',
                    '/mp/agw/article/publish?source=mp&type=article&aid=1231&mp_publish_ab_val=0',
                    false
                );
                xhr.setRequestHeader('Content-Type',
                    'application/x-www-form-urlencoded; charset=UTF-8'
                );
                xhr.send(fd.toString());
                return xhr.responseText;
            }} catch(e) {{
                return JSON.stringify({{error: e.message}});
            }}
        }})()
        """

        result_json = cdp.evaluate(js_code)
        print(f"  [头条发布] API 返回: {result_json[:200]}")

        try:
            resp = json.loads(result_json)
        except json.JSONDecodeError:
            return PublishResult(
                article_title=title, success=False,
                error=f"API 返回非 JSON: {result_json[:100]}",
                tenant_id=self.tenant.id,
            )

        if resp.get("code") == 0:
            msg = resp.get("message", "")
            pgc_id = resp.get("data", {}).get("pgc_id", "")
            if "提交成功" in msg or msg in ("提交成功",):
                print(f"  ✅ [头条发布] 提交成功! pgc_id={pgc_id}")
                return PublishResult(
                    article_title=title, success=True,
                    url=f"https://www.toutiao.com/article/{pgc_id}/",
                    tenant_id=self.tenant.id,
                )
            elif "保存成功" in msg:
                print(f"  ⚠️ [头条发布] 被存为草稿 (pgc_id={pgc_id})")
                return PublishResult(
                    article_title=title, success=True,
                    error="已存草稿，未发布",
                    tenant_id=self.tenant.id,
                )
            else:
                print(f"  ⚠️ [头条发布] 未知状态: {msg}")
                return PublishResult(
                    article_title=title, success=True,
                    error=f"API 返回: {msg}",
                    tenant_id=self.tenant.id,
                )
        else:
            err = resp.get("message", "未知错误")
            print(f"  ❌ [头条发布] API 错误: code={resp.get('code')}, {err}")
            return PublishResult(
                article_title=title, success=False,
                error=f"API error {resp.get('code')}: {err}",
                tenant_id=self.tenant.id,
            )

    # ── 清理 ──────────────────────────────────────────

    def _cleanup(self):
        """清理：关闭 CDP 连接，保留 Chrome 进程"""
        if self._cdp:
            try:
                self._cdp.close()
            except Exception:
                pass
