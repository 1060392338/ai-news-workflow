"""文章与发布结果数据模型"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class Article(BaseModel):
    """AI 生成的文章"""
    title: str
    content: str
    style: str = "news"                # news | deep
    source_item: Optional[dict] = None  # 来源热点 (原始数据)
    created_at: datetime = Field(default_factory=datetime.now)
    tags: list[str] = Field(default_factory=list)  # 话题标签


class PublishResult(BaseModel):
    """发布结果"""
    article_title: str
    success: bool = False
    url: str = ""
    error: str = ""
    published_at: datetime = Field(default_factory=datetime.now)
    tenant_id: str = ""


class PublishLog(BaseModel):
    """持久化的发布日志"""
    id: int = 0
    tenant_id: str
    platform: str
    category: str
    account: str = ""
    article_title: str
    article_content: str = ""
    success: bool
    url: str = ""
    error: str = ""
    created_at: str = ""
