"""搜索器接口定义"""
from typing import Protocol, runtime_checkable
from models.hot_item import SearchResult


@runtime_checkable
class Searcher(Protocol):
    """所有搜索器必须实现的接口"""
    name: str

    def search(self, keywords: list[str], max_results: int = 20) -> list[SearchResult]:
        ...
