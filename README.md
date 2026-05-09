# 头条AI热点多Agent工作流 — Hermes 安装部署文档

> 本文档写给另一个 Hermes Agent 阅读和执行。
> 按顺序执行每一步，完成后即可在新机器上跑通完整工作流。

---

## 项目概述

一个自动化的AI热点内容生产系统：
```
搜索(头条热搜/GitHub/ArXiv)
  → 选题Agent(产出10个选题)
  → 主Agent(精选3个)
  → 写作Agent(写3篇文章)
  → 合规Agent(8维度审核)
  → 主Agent(3篇选最优1篇)
  → Chrome CDP直连 → API发布到今日头条
```

项目目录：`~/.hermes/ai-news-workflow/`

---

## Step 1 — 安装 Python 依赖

```bash
cd ~/.hermes/ai-news-workflow
python3 -m venv .venv
source .venv/bin/activate
pip install langchain-openai httpx pyyaml loguru langgraph DrissionPage websocket-client requests
```

验证安装：
```bash
source .venv/bin/activate
python3 -c "import langchain_openai, httpx, yaml, loguru, langgraph, DrissionPage, websocket, requests; print('✅ 所有依赖安装成功')"
```

如果在中国大陆网络环境下，换国内镜像：
```bash
pip install -i https://pypi.tuna.tsinghua.edu.cn/simple langchain-openai httpx pyyaml loguru langgraph DrissionPage websocket-client requests
```

---

## Step 2 — 配置 LLM API Key

工作流使用 DeepSeek 作为 AI 模型（文章生成 + 审核判断）。

API Key 从 Hermes 配置读取，确认 `~/.hermes/config.yaml` 中有 DeepSeek 配置：

```yaml
providers:
  custom:
    api_key: "sk-你的DeepSeekAPIKey"
    base_url: "https://api.deepseek.com/v1"
```

如果还没有，去 https://platform.deepseek.com 注册获取 API Key。

---

## Step 3 — 配置账号

编辑 `config.yaml`，找到 `tenants` → `toutiao_ai_a` → `platform_config`：

```yaml
platform_config:
  publisher: toutiao
  chrome_data: "chrome_data"
  max_daily: 3
  phone: "填你的头条手机号"         # ← 改成你的
  password: "填你的头条密码"         # ← 改成你的
```

> 手机号和密码目前只用于备选。实际登录走扫码（Step 5）。

---

## Step 4 — 启动 Chrome（带远程调试端口）

工作流通过 Chrome DevTools Protocol (CDP) 连接浏览器，在页面中执行 JavaScript 调用头条发布 API。

Chrome 必须用以下参数启动（Chrome 147+ 需要 `--remote-allow-origins=*`）：

```bash
# 先杀掉已存在的 Chrome 实例
pkill -f "Google Chrome.*9222" 2>/dev/null; sleep 1

# 清理 Chrome 用户数据锁文件
CHROME_DATA="$HOME/.hermes/ai-news-workflow/data/今日头条/AI热点/A账号/chrome_data"
rm -f "$CHROME_DATA/SingletonLock" "$CHROME_DATA/SingletonSocket" "$CHROME_DATA/Default/LOCK" 2>/dev/null

# 启动 Chrome
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  --remote-debugging-port=9222 \
  --remote-allow-origins=* \
  --user-data-dir="$CHROME_DATA" \
  --no-first-run \
  --no-default-browser-check \
  --new-window "about:blank"
```

验证 Chrome 是否启动成功：
```bash
curl -s http://localhost:9222/json/version | python3 -c "import json,sys;d=json.load(sys.stdin);print(f'✅ Chrome {d[\"Browser\"]}')"
```

> ⚠️ 如果 Chrome 不在 `/Applications/Google Chrome.app/`，请先确认安装路径。
>
> ⚠️ 如果这一步报锁文件冲突，执行：
> ```bash
> rm -f "$HOME/.hermes/ai-news-workflow/data/今日头条/AI热点/A账号/chrome_data/SingletonLock" "$HOME/.hermes/ai-news-workflow/data/今日头条/AI热点/A账号/chrome_data/Default/LOCK"
> ```

---

## Step 5 — 首次扫码登录（只需一次）

Chrome 启动后，导航到头条登录页：

```bash
cd ~/.hermes/ai-news-workflow
source .venv/bin/activate
python3 -c "
from infrastructure.platform.toutiao import CDPClient
cdp = CDPClient().connect()
cdp.navigate('https://mp.toutiao.com/auth/page/login')
print('✅ 已打开头条登录页，请在 Chrome 窗口中扫码登录')
print('等待扫码中...')
import time
for i in range(120):
    time.sleep(1)
    url = cdp.get_url()
    if 'passport' not in url and 'login' not in url:
        print(f'✅ 扫码登录成功！（耗时 {i+1} 秒）')
        break
    if i % 15 == 0:
        print(f'⏳ 等待中 ({120-i}秒)...')
cdp.close()
"
```

操作：
1. Chrome 窗口会显示头条登录页的二维码
2. 打开手机今日头条 APP 扫码
3. 手机上确认登录
4. 终端显示 "✅ 扫码登录成功！"

> **为什么只需一次？** Chrome 的用户数据目录（`chrome_data/`）会持久化登录 session。
> 以后每次启动 Chrome 使用同一个用户数据目录，登录态自动恢复。
> 只有 Cookie 过期（通常几个月）才需要重新扫码。

---

## Step 6 — 运行完整工作流

每次运行前，确保 Chrome（port 9222）已在运行（Step 4）。

运行完整流程：
```bash
cd ~/.hermes/ai-news-workflow
source .venv/bin/activate
python3 main.py --tenant toutiao_ai_a --full
```

正常输出应该是这样的：
```
🤖 头条AI号-A — 多 Agent 工作流启动
==================================================
📡 搜索 [今日头条 > AI热点 > A账号]
  ✅ [toutiao] 20 条
📊 选题Agent: 筛选爆款选题
  ✅ 产出 10 个选题
🧠 主Agent: 审核选题
  ✅ 通过! 选定 3 个选题
✍️ 写作Agent: 写文章+自省
  ✅ 共完成 3 篇文章
🛡️ 合规Agent: 审核内容
  ✅ 全部通过
🧠 主Agent: 终审
  ✅ 通过 1 篇，准备发布最优的 1 篇
🚀 发布 [今日头条]
  ✅ [头条发布] Chrome 已连接
  ✅ [头条] 登录态有效（用户数据持久化）
  ✅ [头条发布] 提交成功! pgc_id=...
============================================================
✅ 流程完成
```

如果 Chrome 没启动，代码会自动尝试启动，但建议手动启动（Step 4）更稳定。

---

## Step 7 — 辅助命令

```bash
# 查看当前工作流状态（支持断点续跑）
python3 main.py --status

# 查看历史发布记录
python3 main.py --logs

# 查看所有可用租户
python3 main.py --list-tenants
```

## 多租户隔离架构

系统支持**多平台 × 多领域 × 多账号** 三层隔离，互不干扰。

### 三层目录结构

```
data/
├── 今日头条/                      # ← 平台层隔离
│   ├── AI热点/                    # ← 领域层隔离
│   │   ├── A账号/                 # ← 账号层隔离
│   │   │   ├── chrome_data/       # Chrome 用户数据（登录态持久化）
│   │   │   ├── state.json         # 工作流断点续跑
│   │   │   └── cookies.json       # （已废弃）
│   │   └── B账号/
│   │       └── ...
│   └── 母婴类/
│       ├── C账号/
│       └── D账号/
└── 小红书/                        # ← 不同平台完全独立
    └── 母婴类/
        └── E账号/
```

### 隔离机制

| 隔离维度 | 实现方式 | 效果 |
|----------|----------|------|
| **平台隔离** | 不同平台使用不同的 `publisher` 类型 | 头条用 CDP 直连，小红书暂未实现 |
| **账号隔离** | 每个账号独立的 Chrome 用户数据目录 | 登录态互不干扰，可同时登录多个头条号 |
| **发布器隔离** | 工厂模式分发 | `config.yaml` 中 `publisher` 字段决定走哪个平台 |
| **数据隔离** | data/ 目录三层嵌套 | state.json/chrome_data 完全独立 |

### config.yaml 中的对应关系

一个租户 = 一个 (平台 × 领域 × 账号) 组合：

```yaml
tenants:
  - id: toutiao_ai_a                # 全局唯一 ID
    platform: "今日头条"             # = 平台
    category: "AI热点"               # = 领域
    account: "A账号"                 # = 账号名
    platform_config:
      publisher: toutiao             # 对应注册的发布器类型
      chrome_data: "chrome_data"     # Chrome 用户数据子目录
      phone: "手机号"                # 该账号的手机号
      password: "密码"               # 该账号的密码
    category_config:
      keywords: [ "AI", "大模型" ]   # 该领域的搜索关键词
```

### 添加新账号的步骤

1. 在 `config.yaml` 中新增一个 `tenants` 条目
2. 设置 `platform`/`category`/`account` 标识唯一身份
3. 填上该账号的手机号和密码
4. 设置 `enabled: true` 激活
5. 运行 `python3 main.py --full`
6. **首次运行会自动弹出扫码登录**，扫码后 Chrome 用户数据持久化

### 添加新平台的步骤

1. 在 `infrastructure/platform/` 下新建 `{平台名}.py`
2. 实现 `publish()` 方法，加上 `@register("{平台名}")` 装饰器
3. 在 `config.yaml` 中配置新租户，`publisher` 设为你的平台名
4. 运行验证

---

## 常见问题排查

### Q: Chrome 连不上，报 `BrowserConnectError`
**原因**：Chrome 没启动，或启动时没加 `--remote-allow-origins=*`。
**解决**：重新执行 Step 4。

### Q: 提示 `登录态已过期，请扫码登录`
**原因**：头条 Cookie 过期（几个月一次）。
**解决**：重新执行 Step 5。

### Q: 发布失败，`code=4029 标题长度应该在2-30字之间`
**原因**：写作 Agent 生成的标题超过30字。
**解决**：代码已自动截断，若仍失败说明截断逻辑有问题，可手动修改 `infrastructure/platform/toutiao.py` 的 `publish()` 方法中标题截断逻辑。

### Q: GitHub 搜索全部 403
**原因**：匿名请求受速率限制。
**解决**：在 `infrastructure/searchers/github.py` 中添加 GitHub Token，或忽略（只有头条源也能跑）。

### Q: ArXiv 搜索 429
**原因**：请求频率过高。
**解决**：忽略，头条源已经足够。

### Q: 发布成功但文章里显示 `\n` 字面量
**原因**：写作 Agent prompt 中换行符格式写错了。
**具体**：`services/agents/agents.py` 第 222 行附近，JSON 输出模板中的 `content` 字段用了 `\\\\n`（4个反斜杠+n）。
**完整链条**：prompt中 `\\\\n` → Python 解码为 `\\n` → LLM 看到 `\\n` 以为要输出**字面量** `\n` → `json.loads()` 解出字面量 `\n`（反斜杠+n两个字符）→ 文章里显示 `\n` 文本。
**解决**：改为 `\\n`（2个反斜杠+n），这样 LLM 看到 `\n` 后输出 JSON 标准换行转义，`json.loads()` 解码为真正换行符。

### Q: 文章出现 `**加粗**` 或 `![图片说明: ...]` 原文
**原因**：LLM 输出的 Markdown 标记在发布时未转换为 HTML。
**解决**：`infrastructure/platform/toutiao.py` 的 `_api_publish()` 中做预处理：
- `**加粗**` → `<b>加粗</b>`
- `*斜体*` → `<i>斜体</i>`  
- `![图片说明: ...]` 占位符自动移除

### Q: 发布失败 `code=7115 图片uri非法`
**原因**：头条 publish API 不接受外部图片 URL（如 Unsplash、picsum 链接）。
**解决**：`_upload_images_to_toutiao()` 剥离所有 `<img>` 标签，纯文字发布。如需带图，需通过 `/mp/agw/article_material/photo/upload_picture` 接口上传到头条 CDN（字段名 `upfile`），但 CDP 方式上传实测有兼容问题。

### Q: 写作 Agent 输出混入了"好的，没问题"之类对话开头
**原因**：LLM 有时在输出 JSON 前先写一段对话文字，导致 `_parse_json()` 解析失败，fallback 用原始输出当正文。
**解决**：已强化 prompt 中"只输出 JSON，不要额外文字"的指令，偶尔仍会发生，可人工检查后重新跑一次。

---

## 项目文件说明

| 文件 | 作用 |
|------|------|
| `main.py` | CLI 入口，支持 `--full` `--status` `--logs` `--list-tenants` |
| `config.yaml` | 租户配置（平台、账号、关键词、搜索源） |
| `requirements.txt` | Python 依赖列表 |
| `models/tenant.py` | 租户配置数据模型 |
| `models/article.py` | 文章/发布结果模型 |
| `infrastructure/llm_client.py` | LLM 调用封装（DeepSeek，指数退避重试） |
| `infrastructure/platform/toutiao.py` | 头条发布器（CDP 直连，关键文件） |
| `infrastructure/searchers/` | 各平台搜索器（GitHub/ArXiv/头条/知乎/HN） |
| `services/workflow_graph.py` | LangGraph 工作流编排 |
| `services/agents/agents.py` | 4个 Agent 的提示词和逻辑 |
| `services/aggregator.py` | 搜索结果聚合排序 |
| `services/reviewer.py` | 敏感词规则检查 |

---

## 迁移到新电脑

1. 复制整个项目目录到新机器的 `~/.hermes/ai-news-workflow/`
2. 排除 `data/` 目录（每个机器独立生成）
3. 排除 `.venv/` 目录（每个机器重新创建）
4. 在新机器上执行 **Step 1 → Step 2 → Step 3 → Step 4 → Step 5 → Step 6**

---

## 验证清单

- [ ] Python 3.9+ 已安装
- [ ] 虚拟环境创建完成，依赖安装成功
- [ ] config.yaml 已配置（填了手机号和密码）
- [ ] DeepSeek API Key 在 Hermes 配置中
- [ ] Chrome 已启动（port 9222，带 `--remote-allow-origins=*`）
- [ ] 已扫码登录完成（一次性的）
- [ ] `python3 main.py --list-tenants` 能看到租户
- [ ] `python3 main.py --tenant toutiao_ai_a --full` 完整跑通并发布
