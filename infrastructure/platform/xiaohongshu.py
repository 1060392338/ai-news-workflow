"""
小红书发布器 — 暂未实现，预留桩代码

待实现内容：
  1. 小红书创作者平台登录（扫码或 Cookie）
  2. 笔记发布 API（图片 + 文字）
  3. 标签/话题添加

数据隔离：data/小红书/{category}/{account}/
Chrome 用户数据：data/小红书/{category}/{account}/chrome_data/
"""
from models.article import Article, PublishResult
from models.tenant import TenantConfig
from infrastructure.platform import register


@register("xiaohongshu")
class XiaoHongShuPublisher:
    """小红书发布器（未实现）"""

    def __init__(self, tenant: TenantConfig):
        self.tenant = tenant
        raise NotImplementedError(
            "小红书发布器尚未实现。如需使用，请实现以下功能：\n"
            "  1. 小红书创作者平台登录\n"
            "  2. 笔记发布 API 调用\n"
            "  3. 图片上传处理"
        )

    def publish(self, article: Article, tenant_id: str) -> PublishResult:
        raise NotImplementedError("小红书发布器尚未实现")
