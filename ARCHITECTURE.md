# AI 热点新闻工作流 - LangGraph + 多租户架构

## 多租户数据模型

```
Tenant = { platform, category, account_id }  三元组唯一标识
```

| 租户 ID | 平台 | 领域 | 账号 | 状态 |
|---------|------|------|------|------|
| `toutiao_ai_a` | 今日头条 | AI 热点 | A 号 | ✅ 开发中 |
| `xiaohongshu_baby_b` | 小红书 | 母婴 | B 号 | 🔮 未来 |

## 数据隔离

```
data/
├── tenants/
│   └── {tenant_id}/               ← 按租户隔离
│       ├── config.yaml            租户专属配置覆盖
│       ├── cookies.json           账号凭证
│       ├── chrome_data/           浏览器数据
│       ├── articles.db            文章 + 发布记录
│       └── state.json             工作流检查点
│
└── shared/                        跨租户共享
    └── search_cache.db            搜索缓存 (节约 API 配额)
```

## 平台适配器模式

```
infrastructure/
└── platform/
    ├── base.py                    [Protocol] 平台发布接口
    ├── toutiao.py                 DrissionPage → 头条
    └── xiaohongshu.py             DrissionPage → 小红书 (未来)
```

不同平台实现同一个 `PublisherAdapter` Protocol，业务层不感知平台差异。

## LangGraph 单图多租户

**一张工作流图，所有租户共用**，运行时注入 tenant_id 区分：

```
          START
            │
            ▼
        [collect]      ← 按 tenant.category 的关键词搜索
            │
            ▼
       [aggregate]     ← 按 tenant.category 的聚合策略
            │
            ▼
      [push_top10]     ← 通过飞书推送给对应的运营者
            │
     ┌──────┴──────┐
     │  用户回复选择  │
     └──────┬──────┘
            ▼
       [generate]     ← 按 tenant.category 的内容风格生成
            │
            ▼
        [review]      ← 按 tenant.platform 的规则审核
            │
            ▼
     [push_preview]   ← 推送预览，等待确认
            │
     ┌──────┴──────┐
     │  用户回复发布  │
     └──────┬──────┘
            ▼
       [publish]      ← 调用 tenant.platform 的适配器
            │
            ▼
          END
```

## 核心目录结构

```
~/.hermes/ai-news-workflow/
├── config.yaml                         # 全局配置 + 多租户定义
├── main.py                             # 入口
│
├── models/                             # 数据模型
│   ├── hot_item.py                     # 热点条目
│   ├── article.py                      # 文章
│   └── tenant.py                       # 租户配置
│
├── infrastructure/                     # 基础设施
│   ├── http_client.py                  # 统一 HTTP
│   ├── llm_client.py                   # LLM 调用
│   ├── repository.py                   # 租户感知数据库
│   ├── searchers/                      # 搜索器
│   │   ├── base.py
│   │   ├── github.py
│   │   ├── hn.py
│   │   ├── arxiv.py
│   │   ├── zhihu.py
│   │   └── toutiao.py
│   └── platform/                       # 平台适配器
│       ├── base.py                     # Protocol
│       ├── toutiao.py                  # 头条发布
│       └── xiaohongshu.py              # 小红书 (占位)
│
├── services/                           # 业务层
│   ├── workflow_graph.py               # LangGraph 工作流
│   ├── aggregator.py                   # 聚合 + TopN
│   └── reviewer.py                     # 合规审核
│
├── presentation/                       # 表现层
│   └── feishu_messages.py              # 飞书消息
│
└── data/
    ├── tenants/
    │   └── toutiao_ai_a/               # 当前租户数据
    │       ├── cookies.json
    │       ├── chrome_data/
    │       ├── articles.db
    │       └── state.json
    └── shared/
