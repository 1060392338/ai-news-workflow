"""平台发布器工厂 — 根据 publisher 类型自动分发到对应实现

每增加一个新平台，只需：
  1. 在 infrastructure/platform/ 下新建 {平台名}.py
  2. 实现 PublisherAdapter 接口
  3. 在类上使用 @register("平台名") 装饰器
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

    # 延迟导入：按需加载发布器模块（避免循环导入）
    if publisher_type not in PUBLISHER_MAP:
        _lazy_import(publisher_type)

    cls = PUBLISHER_MAP.get(publisher_type)
    if not cls:
        raise ValueError(
            f"未知的发布器类型: '{publisher_type}'。"
            f"已注册: {list(PUBLISHER_MAP.keys())}"
        )
    return cls(tenant)


def _lazy_import(publisher_type: str):
    """按需导入发布器模块"""
    import importlib
    try:
        mod = importlib.import_module(f"infrastructure.platform.{publisher_type}")
        # 模块导入后，其顶层的 @register 装饰器会自动注册到 PUBLISHER_MAP
    except ImportError:
        pass


def list_supported_platforms() -> list[str]:
    """列出所有已注册的平台"""
    return list(PUBLISHER_MAP.keys())
