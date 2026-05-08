"""平台发布器工厂 — 根据 publisher 类型自动分发到对应实现

每增加一个新平台，只需：
  1. 在 infrastructure/platform/ 下新建 {平台名}.py
  2. 实现 PublisherAdapter 接口
  3. 在 PUBLISHER_MAP 中注册
"""
from models.article import Article, PublishResult
from models.tenant import TenantConfig

# Publisher 注册表
PUBLISHER_MAP = {}


def register(publisher_type: str):
    """装饰器：注册发布器类型"""
    def decorator(cls):
        PUBLISHER_MAP[publisher_type] = cls
        return cls
    return decorator


def get_publisher(tenant: TenantConfig):
    """工厂方法：根据租户配置返回对应的发布器实例"""
    publisher_type = tenant.platform_config.publisher
    cls = PUBLISHER_MAP.get(publisher_type)
    if not cls:
        raise ValueError(
            f"未知的发布器类型: '{publisher_type}'。"
            f"已注册: {list(PUBLISHER_MAP.keys())}"
        )
    return cls(tenant)


def list_supported_platforms() -> list[str]:
    """列出所有已注册的平台"""
    return list(PUBLISHER_MAP.keys())
