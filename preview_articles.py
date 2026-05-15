"""选题→写作 预览脚本 —— 直接调搜索源+Agent"""
import sys, os, json
from concurrent.futures import ThreadPoolExecutor, as_completed

os.chdir('/Users/mac/.hermes/ai-news-workflow')
sys.path.insert(0, '/Users/mac/.hermes/ai-news-workflow')
sys.path.insert(0, '/Users/mac/.hermes/ai-news-workflow/.venv/lib/python3.9/site-packages')

from services.agents.agents import TopicAgent, WriterAgent, MainAgent
from infrastructure.llm_client import LLMClient
from infrastructure.searchers.github import GitHubSearcher
from infrastructure.searchers.hn import HackerNewsSearcher
from infrastructure.searchers.arxiv import ArXivSearcher
from infrastructure.searchers.zhihu import ZhiHuSearcher
from infrastructure.searchers.toutiao import TouTiaoSearcher
from infrastructure.searchers.baidu import BaiduSearcher
from infrastructure.searchers.douyin import DouyinSearcher
from infrastructure.searchers.tools import ToolsSearcher

KW = ["AI", "Skills", "Workflow", "Agent", "大模型", "编程"]

searchers = {
    "github": GitHubSearcher(), "hn": HackerNewsSearcher(),
    "arxiv": ArXivSearcher(), "zhihu": ZhiHuSearcher(),
    "toutiao": TouTiaoSearcher(), "baidu": BaiduSearcher(),
    "douyin": DouyinSearcher(), "tools": ToolsSearcher(),
}

print("🔍 搜索 8 源...")
raw = {}
kw = " ".join(KW)
with ThreadPoolExecutor(max_workers=8) as pool:
    futures = {pool.submit(s.search, kw): name for name, s in searchers.items()}
    for f in as_completed(futures, timeout=60):
        name = futures[f]
        try:
            results = f.result(timeout=30)
            raw[name] = results
            print(f"  {name}: {len(results)} 条")
        except Exception as e:
            raw[name] = []
            print(f"  {name}: ❌ {e}")

total = sum(len(v) for v in raw.values())
print(f"  总计: {total} 条")

print("\n🎯 选题 Agent 筛选 10 个...")
llm = LLMClient()
topic_agent = TopicAgent(llm=llm)
topics = topic_agent.select_topics(raw, KW)

for i, t in enumerate(topics[:10]):
    print(f"  [{i+1}] {t.get('title','无标题')[:70]}")
print(f"  选题数: {len(topics)}")

selected = topics[:3]
print(f"\n  写前3篇: {selected[0].get('title','')[:40]}, ...")

print("\n✍️ 写作 Agent 生成中...")
writer = WriterAgent(llm=llm)
articles = []
for i, topic in enumerate(selected):
    result = writer.write_articles(topic, count=1)
    articles.extend(result)

print(f"\n{'='*50}")
print(f"📄 共 {len(articles)} 篇")
print(f"{'='*50}")

for i, art in enumerate(articles):
    title = art.get('title', '无标题')
    content = art.get('content', '无内容')
    wc = art.get('word_count', 0)
    images = art.get('images', [])
    sr = art.get('self_review', {})

    print(f"\n{'─'*50}")
    print(f"【第{i+1}篇】{title}")
    print(f"字数:{wc} | 配图:{len(images)}张 | 自评:{'✅' if sr.get('passed') else '⚠️'}")
    if sr.get('issues'):
        print(f"问题: {sr['issues']}")
    if images:
        print(f"配图描述: {images}")
    print(f"\n{content}")
    print()
