"""租户配置数据模型"""
from typing import Optional
from pydantic import BaseModel, Field


class PlatformConfig(BaseModel):
    """平台相关配置"""
    publisher: str = "toutiao"
    publish_url: str = ""
    cookie_file: str = ""
    chrome_data: str = ""
    max_daily: int = 3
    phone: str = ""
    password: str = ""


class CategoryConfig(BaseModel):
    """领域相关配置"""
    keywords: list[str] = Field(default_factory=list)
    search_sources: list[str] = Field(default_factory=list)
    content_style: str = "news"
    top_n: int = 10


class AccountConfig(BaseModel):
    """账号相关配置"""
    name: str = ""


class TenantConfig(BaseModel):
    """租户完整配置
    三层结构: platform → category → account
    """
    id: str                          # 唯一标识，如 toutiao_ai_a
    enabled: bool = True
    platform: str = "今日头条"        # 平台中文名
    category: str = "AI热点"          # 类别中文名
    account: str = "A账号"            # 账号中文名
    display_name: str = ""           # 展示名
    schedule: str = "0 8 * * *"
    platform_config: PlatformConfig = Field(default_factory=PlatformConfig)
    category_config: CategoryConfig = Field(default_factory=CategoryConfig)
    account_config: AccountConfig = Field(default_factory=AccountConfig)

    @property
    def data_dir(self) -> str:
        """数据目录: 平台/类别/账号"""
        return f"data/{self.platform}/{self.category}/{self.account}"


class AppConfig(BaseModel):
    """应用全局配置"""
    tenants: list[TenantConfig] = Field(default_factory=list)

    def get_tenant(self, tenant_id: str) -> Optional[TenantConfig]:
        for t in self.tenants:
            if t.id == tenant_id:
                return t
        return None

    def get_enabled_tenants(self) -> list[TenantConfig]:
        return [t for t in self.tenants if t.enabled]
