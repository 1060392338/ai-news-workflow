# 头条AI热点多Agent工作流 — Hermes → Hermes 部署手册

> **写给另一个 Hermes Agent 阅读**：本文档是一份完整的可执行指引。
> 按顺序执行每一个 Step，每步末尾有验证点，确认通过后再继续下一步。
> 如果某一步遇到错误，跳到末尾的「常见问题排查」对照解决。

---

## 项目概述

一个自动化 AI 热点内容生产系统，8个搜索源 → 4个 AI Agent → 自动发布到今日头条。

```
搜索(头条/抖音/百度/GitHub/ArXiv等8源并行)
  → 选题Agent(产出10个AI/科技选题)
  → _filter_ai_topics(硬过滤非AI内容)
  → 主Agent(精选3个最具爆款潜力的)
  → 写作Agent(写3篇真人风格文章 + 配图描述)
  → 合规Agent(8维度风险审核)
  → 主Agent终审(3篇选最优1篇)
  → ImageSearchService(Unsplash配图) 
  → Cookie上传图片到头条CDN
  → Chrome CDP直连 → API发布到今日头条
```

项目目录：`~/.hermes/ai-news-workflow/`

---

## 🧠 设计哲学（所有 Hermes 必须遵守）

本项目遵循两套核心方法论，任何修改/扩展都必须以此为红线。

### ClawCode 事件驱动架构参考

本项目的管道式架构借鉴了 **[ClawCode](https://github.com/1060392338/ClawCode)** 的事件驱动设计模式。ClawCode 的核心机制值得每个 Hermes 熟悉：

| ClawCode 模式 | 本项目对应 | 说明 |
|---------------|-----------|------|
| **AgentEmitter 事件驱动** | `pipelines/` 各管线内 `emit()` → `on()` 解耦 | 模块间不直接调用，通过事件通信。新增搜索源/平台只需注册，不用改现有流程 |
| **Content Map 按需加载** | `pipelines/__init__.py` 中 `@register` + 延迟加载 | 管线只在被选中时导入，避免加载所有依赖 |
| **FeedItem 状态机** | `models/article.py` 中发布状态流转 | 每篇文章有明确生命周期：草稿→审核→已发/驳回 |
| **三层次记忆系统** | `infrastructure/repository.py` SQLite 持久化 | 运行时状态缓存在内存，关键数据持久化到 SQLite |

> **开发本项目的 Hermes 必须加载 skill `clawcode-driven-development`**，了解完整的事件驱动编码规范。

### Karpathy 四大编码红线（AI 编程准则）

源自 Andrej Karpathy 观察的四大原则，是 LLM 修改本项目代码时的不可逾越的底线：

```
┌──────────────────────────────────────────────────────────┐
│  🔴 红线1 — Think Before Coding（编码前思考）              │
│  修改前先读相关文件的全部代码，理解上下文，不假设。          │
│  呈现至少一种替代方案的权衡，再选择实现方式。               │
├──────────────────────────────────────────────────────────┤
│  🔴 红线2 — Simplicity First（简洁优先）                   │
│  用最少的代码解决问题，不堆抽象层/设计模式/基类。           │
│  一个函数能搞定的事，不要拆成三个文件。                    │
├──────────────────────────────────────────────────────────┤
│  🔴 红线3 — Surgical Changes（精准修改）                   │
│  只碰必须碰的代码行。不改缩进/重命名/加注释这种无关改动。  │
│  每次 patch 前后 diff 确认只改了目标行。                   │
├──────────────────────────────────────────────────────────┤
│  🔴 红线4 — Goal-Driven（目标驱动）                         │
│  开始前定义「怎样算改好了」的成功标准。                     │
│  修改后逐项验证：测试通过？功能正常？没有副作用？          │
└──────────────────────────────────────────────────────────┘
```

**代码审查时**：如果修改违反了上述任意一条红线，直接驳回，要求重写。

---

## 架构速览

```
~/.hermes/ai-news-workflow/
├── main.py                    # CLI入口
├── config.yaml                # 多租户配置（填手机号/密码/关键词）
├── requirements.txt           # Python依赖列表（不存在则从README拷贝）
├── .gitignore                 # 忽略敏感文件
├── .env                       # API Key环境变量（GITHUB_TOKEN, UNSPLASH_ACCESS_KEY）
│
├── pipelines/                 # 🏗️ 业务管线（可插拔）
│   ├── __init__.py            # 工厂 + @register + 延迟加载
│   ├── content_creation.py   # 内容创作→发布（默认管线）
│   └── nurturing.py          # 养号管线（每日限发1篇+自动话题标签）
│
├── infrastructure/
│   ├── llm_client.py          # DeepSeek LLM调用（指数退避）
│   ├── http_client.py         # 统一HTTP客户端
│   ├── repository.py          # SQLite持久化
│   ├── image_search.py        # Unsplash图片搜索
│   ├── searchers/             # 8个搜索源
│   │   ├── github.py / arxiv.py / hn.py / zhihu.py / toutiao.py
│   │   ├── baidu.py / douyin.py / tools.py
│   └── platform/              # 发布器工厂
│       ├── toutiao.py         # 头条发布（CDP+Cookie图片上传，关键文件）
│       └── xiaohongshu.py     # 小红书桩代码（未实现）
│
├── services/
│   ├── agents.py              # 4个Agent（主/选题/写作/合规）+ prompt定义
│   ├── workflow_graph.py      # LangGraph工作流编排 + 话题标签匹配
│   ├── aggregator.py          # 搜索结果聚合排序
│   └── reviewer.py            # 敏感词规则预检
│
├── models/
│   ├── tenant.py              # 租户配置数据模型
│   ├── article.py             # 文章/发布结果模型
│   └── hot_item.py            # 搜索结果模型
│
├── tests/                     # 25个pytest用例
│
└── data/                      # 每个机器独立生成，不要复制
    └── {平台}/{类别}/{账号}/
        ├── chrome_data/       # Chrome用户数据（登录态持久化）
        ├── state.json         # 工作流断点
        └── publish_record.json # 养号每日发布记录
```

---

## Step 0 — 准备项目文件

从源机器复制整个项目目录（排除 data/ 和 .venv/）：

```bash
# 在源机器上
cd ~/.hermes
# 压缩项目（排除无用目录）
tar czf ai-news-workflow.tar.gz ai-news-workflow --exclude='ai-news-workflow/data' --exclude='ai-news-workflow/.venv' --exclude='ai-news-workflow/.env'

# 传到新机器（用scp/rsync/U盘/微信文件助手等方式）
# scp ai-news-workflow.tar.gz new-machine:~/.hermes/

# 在新机器上解压
cd ~/.hermes
tar xzf ai-news-workflow.tar.gz
cd ai-news-workflow
```

> ⚠️ 不要复制 `.venv/` 和 `data/` 目录，每台机器独立创建。
> ⚠️ `.env` 文件包含API Key，不要复制，手动创建。

---

## Step 1 — 安装 Python 依赖

```bash
cd ~/.hermes/ai-news-workflow

# 创建虚拟环境
python3 -m venv .venv
source .venv/bin/activate

# 安装依赖（国内用清华镜像）
pip install -i https://pypi.tuna.tsinghua.edu.cn/simple \
  langchain-openai httpx pyyaml loguru langgraph DrissionPage \
  websocket-client requests pydantic
```

**验证：**
```bash
source .venv/bin/activate
python3 -c "
import langchain_openai, httpx, yaml, loguru, langgraph, DrissionPage, websocket, requests
print('✅ 所有依赖安装成功')
"
```

---

## Step 2 — 配置 API Key

工作流使用 **DeepSeek** 作为 AI 模型。API Key 从 Hermes Agent 自身的配置文件读取。

确认 `~/.hermes/config.yaml` 中有 DeepSeek 配置（Hermes v0.10.0 格式）：

```bash
# 查看当前配置
cat ~/.hermes/config.yaml | grep -A3 custom_providers
```

如果不存在或没有 DeepSeek API Key，手动添加：
```bash
cat >> ~/.hermes/config.yaml << 'EOF'
custom_providers:
  - name: custom
    api_key: "sk-你的DeepSeekAPIKey"
    base_url: "https://api.deepseek.com/v1"
EOF
```

> DeepSeek API Key 获取：https://platform.deepseek.com → 注册 → 创建 API Key

---

## Step 3 — 创建 .env 文件

```bash
cd ~/.hermes/ai-news-workflow
cat > .env << 'EOF'
GITHUB_TOKEN="你的GitHub Personal Access Token"
UNSPLASH_ACCESS_KEY="你的Unsplash Access Key"
TOUTIAO_PHONE="头条登录手机号"
TOUTIAO_PASSWORD="头条登录密码"
EOF
```

各 Key 获取方式：
| Key | 用途 | 获取地址 |
|-----|------|----------|
| `GITHUB_TOKEN` | GitHub 搜索（防403） | https://github.com/settings/tokens → 生成 classic PAT |
| `UNSPLASH_ACCESS_KEY` | 文章配图搜索 | https://unsplash.com/oauth/applications → 注册应用 |
| `TOUTIAO_PHONE/PASSWORD` | 登录备选 | 你的头条号手机号和密码 |

> `.env` 已被 `.gitignore` 忽略，不会上传到 GitHub。

---

## Step 4 — 配置 config.yaml

编辑 `config.yaml`，修改 `toutiao_ai_a` 租户的配置：

```bash
cd ~/.hermes/ai-news-workflow
# 用 sed 或手动编辑
```

需要修改的字段：
```yaml
tenants:
  - id: toutiao_ai_a
    enabled: true
    platform: "今日头条"
    category: "AI热点"
    account: "A账号"
    schedule: "0 8 * * *"
    pipeline_type: content_creation   # 或 nurturing（养号模式）
    platform_config:
      publisher: toutiao
      phone: "你的头条手机号"          # ← 填你的
      password: "你的头条密码"          # ← 填你的
```

> 如果使用养号模式，把 `pipeline_type` 改为 `nurturing`（每天限发1篇）。

**验证：**
```bash
cd ~/.hermes/ai-news-workflow
source .venv/bin/activate
python3 main.py --list-tenants
# 应该能看到 toutiao_ai_a 及其相关信息
```

---

## Step 5 — 启动 Chrome（带远程调试端口）

工作流通过 Chrome DevTools Protocol (CDP) 连接浏览器，在页面中执行 JavaScript 调头条 API。

**Chrome 启动命令（macOS）：**

```bash
cd ~/.hermes/ai-news-workflow

# 1. 清理锁文件
CHROME_DATA="$HOME/.hermes/ai-news-workflow/data/今日头条/AI热点/A账号/chrome_data"
mkdir -p "$CHROME_DATA"
rm -f "$CHROME_DATA/SingletonLock" "$CHROME_DATA/SingletonSocket" "$CHROME_DATA/Default/LOCK" 2>/dev/null

# 2. 杀掉已存在的 Chrome 实例
pkill -f "Google Chrome.*9222" 2>/dev/null
sleep 2

# 3. 启动 Chrome（port 9222，remote-allow-origins 必须加）
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  --remote-debugging-port=9222 \
  --remote-allow-origins=* \
  --user-data-dir="$CHROME_DATA" \
  --no-first-run \
  --no-default-browser-check \
  --new-window "about:blank" &
```

**验证 Chrome 启动成功：**
```bash
sleep 3
curl -s http://localhost:9222/json/version | python3 -c "
import json,sys
d=json.load(sys.stdin)
print(f'✅ Chrome {d[\"Browser\"]}')
print(f'✅ WebSocket: {d[\"webSocketDebuggerUrl\"][:50]}...')
"
```

> ⚠️ 如果 Chrome 不在 `/Applications/Google Chrome.app/`，先确认路径。
> ⚠️ 端口冲突：改端口号需要同步修改 `infrastructure/platform/toutiao.py` 中的 `CDPClient(port=9222)`。
> ⚠️ 锁文件冲突：执行上面的 `rm -f` 清理命令。

---

## Step 6 — 首次扫码登录（只需一次）

Chrome 启动后，需要让头条登录态持久化到 Chrome 用户数据目录。

```bash
cd ~/.hermes/ai-news-workflow
source .venv/bin/activate

python3 << 'PYEOF'
from infrastructure.platform.toutiao import CDPClient
import time

cdp = CDPClient(port=9222).connect()
cdp.navigate("https://mp.toutiao.com/auth/page/login")
print("✅ 已打开头条登录页")

print("请在 Chrome 窗口中找到二维码，用手机今日头条 APP 扫码登录")
for i in range(120, 0, -1):
    time.sleep(1)
    url = cdp.get_url()
    if "passport" not in url and "login" not in url:
        print(f"✅ 扫码登录成功！({120-i}秒)")
        break
    if i % 15 == 0:
        print(f"⏳ 等待扫码中 ({i}秒)...")
else:
    print("⚠️ 等待超时，可手动完成后重试")

cdp.close()
PYEOF
```

操作步骤：
1. 看 Chrome 窗口 → 会显示头条登录页的二维码
2. 打开手机 **今日头条 APP**
3. 点「我的」→ 左上角「扫一扫」
4. 扫码后手机确认登录
5. 终端显示「✅ 扫码登录成功！」

> **为什么只需一次？** Chrome 用户数据目录（`chrome_data/`）会持久化登录态。
> 以后每次启动 Chrome 用同一个 `--user-data-dir`，登录态自动恢复。
> 只有 Cookie 过期（通常几个月）才需要重新扫码。

---

## Step 7 — 运行完整工作流

每次运行前，确保 Chrome（port 9222）已在运行（Step 5）。

### 默认模式（每日可发多篇）

```bash
cd ~/.hermes/ai-news-workflow
source .venv/bin/activate
python3 main.py --full
```

### 养号模式（新手期，每日限发1篇）

先修改 config.yaml 中的 `pipeline_type: nurturing`，然后运行：
```bash
python3 main.py --full
```

### 指定租户

```bash
python3 main.py --tenant "今日头条/AI热点/A账号" --full
```

### 辅助命令

```bash
# 查看状态
python3 main.py --status

# 查看发布历史
python3 main.py --logs

# 列出所有租户
python3 main.py --list-tenants

# 列出所有可用管线
python3 main.py --list-pipelines
```

**正常运行输出示例：**
```
🤖 头条AI号-A — Pipeline: nurturing
==================================================
📡 搜索 [今日头条 > AI热点 > A账号]
  ✅ [toutiao] 20 条  [douyin] 20 条  [baidu] 20 条  [github] 20 条
📊 选题Agent: 筛选爆款选题 → ✅ 产出10个
🧠 主Agent: 审核选题 → ✅ 选定3个
✍️ 写作Agent: 写3篇文章 → ✅ 完成
🛡️ 合规Agent: 审核 → ✅ 通过
🧠 主Agent: 终审 → ✅ 通过1篇
🚀 发布 [今日头条]
     🏷️ 话题标签: AI, ChatGPT, 大模型
     🖼️ 已解析4张配图
  [头条上传] 4/4张已上传到头条CDN
  ✅ [头条发布] 提交成功! pgc_id=76377...
  📊 今日已发布 1/1 篇
============================================================
✅ 流程完成
```

---

## 新号养号策略

新头条号有 **14天新手观察期**，前7天流量受限。

### 阶段策略

| 阶段 | 天数 | 每天发布 | Pipeline配置 | 重点 |
|------|------|----------|-------------|------|
| 初始化 | 第1-3天 | 1篇 | `nurturing` | 垂直AI内容，话题标签 |
| 稳定输出 | 第4-7天 | 1-2篇 | `nurturing` | 丰富内容类型，互动引导 |
| 拓展期 | 第8-14天 | 2-3篇 | `content_creation` | 尝试不同风格 |
| 正常运营 | 14天后 | 1-3篇 | `content_creation` | 根据数据优化选题 |

开启养号模式只需修改 `config.yaml`：
```yaml
tenants:
  - id: toutiao_ai_a
    pipeline_type: nurturing  # 养号模式
```

养号管线（`pipelines/nurturing.py`）自动：
- **每日限发1篇**（记录在 `publish_record.json`）
- **自动勾选话题标签**（`interest_tags` 字段）
- **已达上限自动跳过**

### 话题标签自动匹配

在 `services/workflow_graph.py` 的 `_auto_match_tags()` 中实现：
- 根据标题+正文前500字，匹配10个AI话题分类
- 取得分最高的前3个标签
- 通过 `interest_tags` 字段发送到 API
- 词库维护在 `_TOPIC_TAGS` 字典中

### 养号注意事项

| ✅ 必须做 | ❌ 不能做 |
|----------|----------|
| 垂直AI内容 | 跨领域发内容（系统无法打标签） |
| 每天固定时间发布 | 一天发5篇以上（被判定为营销号） |
| 每篇文章2-3个话题标签 | 搬运/抄袭 |
| 文末引导评论互动 | 标题党过度 |
| 登录、刷推荐、点赞评论 | 频繁修改已发布内容 |

---

## 图片配图机制

### 流水线
```
写作Agent → images: ["中文描述1", "中文描述2", ...]
  → ImageSearchService
    → Unsplash API（主源）
    → picsum.photos（备用源）
  → 替换文章中的 ![图片说明: xxx] 为 <img src="真实URL">
  → _upload_images_to_toutiao（Cookie上传到头条CDN）
    → 替换src为头条内部CDN地址
  → 发布到头条API
```

### Unsplash 中文搜索技巧

ImageSearchService 的 `_extract_keywords()` 从中文描述提取核心词（去修饰词）：
```
"一张乒乓球比赛AI裁判系统截图" → "乒乓球比赛 AI裁判系统"
```

### Cookie上传流程

`_upload_images_to_toutiao()` 使用浏览器Cookies直传图片到头条CDN：
```
CDP获取Cookie(Network.getCookies) 
  → Python requests下载图片 
    → multipart上传到 /mp/agw/article_material/photo/upload_picture
      → 字段名: upfile
        → 返回 web_url → 替换content中的img src
```

---

## 多租户隔离架构

### 三层目录结构
```
data/
├── 今日头条/AI热点/A账号/chrome_data/   # 登录态
├── 今日头条/AI热点/A账号/state.json     # 断点续跑
├── 今日头条/母婴类/C账号/...
└── 小红书/母婴类/E账号/...              # 不同平台
```

### 添加新账号
1. config.yaml 中新增 `tenants` 条目
2. 填手机号和密码
3. `enabled: true`
4. 运行 `python3 main.py --full`
5. 首次运行会自动触发扫码登录

### 添加新平台
1. `infrastructure/platform/` 下新建 `{平台名}.py`
2. 实现 `publish()` 方法，加 `@register("{平台名}")`
3. config.yaml 中 `publisher` 设为平台名

---

## 常见问题排查

### Q: Chrome 连不上，报 `BrowserConnectError`
**原因**：Chrome 没启动，或启动时没加 `--remote-allow-origins=*`。
**解决**：重新执行 Step 5。验证：`curl -s http://localhost:9222/json/version`

### Q: ❌ [头条] 登录态已过期，请扫码登录
**原因**：头条 Cookie 过期（几个月一次）。
**解决**：重新执行 Step 6 扫码。

### Q: API 返回 `code=4029 标题长度应该在2-30字之间`
**原因**：标题超过30字。代码已自动截断，但偶尔仍会触发。
**解决**：检查 `infrastructure/platform/toutiao.py` 的截断逻辑。

### Q: GitHub 搜索全部 403
**原因**：匿名请求受速率限制。
**解决**：在 `.env` 中配置 `GITHUB_TOKEN`，或忽略（只有头条源也能跑）。

### Q: 发布成功但文章里显示 `\n` 字面量（而不是换行）
**原因**：写作 Agent prompt 中换行符被双转义。
**根因**：`services/agents/agents.py` 中 prompt 的 JSON 输出模板用了 `\\\\n`（4反斜杠），导致 LLM 输出字面量 `\n`。
**解决**：改为 `\\n`（2反斜杠）。检查 find/replace：
```python
# ❌ 错误（已修复）
"content": "文章正文（用 \\\\n\\\\n 分段）",
# ✅ 正确
"content": "文章正文（用 \n\n 分段）",
```

### Q: 文章出现 `**加粗**` 或 `![图片说明: ...]` 原文
**原因**：LLM 输出的 Markdown 标记未转换为 HTML。
**解决**：`_api_publish()` 中已做预处理：
- `**加粗**` → `<b>加粗</b>`
- `![图片说明: ...]` → 自动移除

### Q: 发布失败 `code=7115 图片uri非法`
**原因**：头条 API 不接受外部图片 URL（Unsplash/picsum 链接）。
**解决**：`_upload_images_to_toutiao()` 已实现 Cookie 方式上传到头条 CDN。验证浏览器 Cookie 是否有效（重新扫码）。

### Q: 写作 Agent 输出混入了"好的，没问题"之类对话开头
**原因**：LLM 在输出 JSON 前先写了一段对话，`_parse_json()` 解析失败。
**解决**：fallback 用了原始输出。重新跑一次即可，偶尔会发生。

### Q: 图片上传报错 `"Invalid image data"` 或 code=1053
**原因**：旧版使用 CDP base64/Blob 方式上传，大图片数据可能被截断。
**解决**：已改用 Cookie + Python requests 方式上传。如果还失败，检查 `.env` 中是否有代理设置或网络限制。

### Q: 运行时报 `SingletonLock` 错误
**原因**：Chrome 进程异常退出留下了锁文件。
**解决**：
```bash
rm -f ~/.hermes/ai-news-workflow/data/今日头条/AI热点/A账号/chrome_data/SingletonLock
rm -f ~/.hermes/ai-news-workflow/data/今日头条/AI热点/A账号/chrome_data/Default/LOCK
```

---

## 验证清单

每完成一步，对照检查：

- [ ] Step 0: 项目文件已复制到新机器的 `~/.hermes/ai-news-workflow/`
- [ ] Step 1: `.venv/` 已创建，`pip install` 成功，导入验证通过
- [ ] Step 2: `~/.hermes/config.yaml` 中有 DeepSeek API Key
- [ ] Step 3: `.env` 文件已创建（GITHUB_TOKEN + UNSPLASH_ACCESS_KEY）
- [ ] Step 4: `config.yaml` 中 `phone` 和 `password` 已填好
- [ ] Step 4: `python3 main.py --list-tenants` 能看到租户信息
- [ ] Step 5: Chrome 已启动，`curl localhost:9222/json/version` 返回正常
- [ ] Step 6: 已扫码登录，终端显示「✅ 扫码登录成功！」
- [ ] Step 7: `python3 main.py --full` 完整跑通并发布

---

## 调试命令

```bash
# 检查 Chrome 进程
ps aux | grep chrome | grep remote-debugging

# 检查 Chrome CDP 接口
curl -s http://localhost:9222/json/version

# 查看所有浏览器标签页
curl -s http://localhost:9222/json | python3 -m json.tool | grep -E '"url"|"title"'

# 重启 Chrome
pkill -f "remote-debugging-port=9222"
sleep 2
# 然后重新执行 Step 5 的启动命令

# 查看发布记录
python3 main.py --logs

# 清理锁文件
rm -f ~/.hermes/ai-news-workflow/data/*/*/*/chrome_data/SingletonLock
rm -f ~/.hermes/ai-news-workflow/data/*/*/*/chrome_data/Default/LOCK
```
