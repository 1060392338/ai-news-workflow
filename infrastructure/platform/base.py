"""平台发布适配器接口"""
from typing import Protocol, runtime_checkable
from models.article import Article, PublishResult


@runtime_checkable
class PublisherAdapter(Protocol):
    """所有平台发布器必须实现的接口"""

    def publish(self, article: Article, tenant_id: str) -> PublishResult:
        ...
