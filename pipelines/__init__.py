"""Pipeline 注册器 + 基类

每个 pipeline 代表一个独立业务逻辑流程：
  - content_creation  → 内容创作 + 发布（内置）
  - 更多可扩展...

使用方式：新建 pipelines/{类型名}.py，@register("类型名") 装饰器即可。
"""
from abc import ABC, abstractmethod
from typing import Optional

from models.tenant import TenantConfig

# Pipeline 注册表
PIPELINE_MAP = {}


def register(pipeline_type: str):
    """装饰器：注册 pipeline 类型"""
    def decorator(cls):
        PIPELINE_MAP[pipeline_type] = cls
        return cls
    return decorator


class BasePipeline(ABC):
    """所有 pipeline 的基类"""

    def __init__(self, tenant: TenantConfig):
        self.tenant = tenant

    @abstractmethod
    def run(self) -> dict:
        """执行整个 pipeline，返回结果"""
        ...


def get_pipeline(pipeline_type: str, tenant: TenantConfig):
    """工厂方法：根据类型返回对应的 pipeline 实例"""
    if pipeline_type not in PIPELINE_MAP:
        _lazy_import(pipeline_type)
    cls = PIPELINE_MAP.get(pipeline_type)
    if not cls:
        raise ValueError(
            f"未知的 pipeline 类型: '{pipeline_type}'。"
            f"已注册: {list(PIPELINE_MAP.keys())}"
        )
    return cls(tenant)


def _lazy_import(pipeline_type: str):
    """按需导入 pipeline 模块"""
    import importlib
    try:
        importlib.import_module(f"pipelines.{pipeline_type}")
    except ImportError:
        pass


# 内置 pipeline：启动时自动注册
import pipelines.content_creation  # noqa: F401, E402
