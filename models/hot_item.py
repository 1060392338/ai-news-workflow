"""热点条目数据模型"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class SearchResult(BaseModel):
    """搜索器返回的原始结果"""
    title: str
    url: str
    summary: str = ""
    source: str = ""            # github | hackernews | arxiv | zhihu | toutiao
    source_domain: str = ""
    hot_score: int = 0
    published_at: Optional[datetime] = None
    language: str = "en"        # en | zh
    tags: list[str] = Field(default_factory=list)


class HotItem(BaseModel):
    """聚合后的热点条目 (Top N 候选)"""
    rank: int = 0
    title: str
    summary: str
    url: str
    source: str
    source_domain: str = ""
    hot_score: int = 0
    language: str = "en"
    tags: list[str] = Field(default_factory=list)
    needs_translation: bool = False
    is_ai_relevant: bool = True
