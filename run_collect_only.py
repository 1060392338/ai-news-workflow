#!/usr/bin/env python3
"""运行头条工作流：搜索→选题→写作→合规→终审，跳过发布"""
import os, sys, json, time
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from models.tenant import TenantConfig
from services.workflow_graph import AgentWorkflow, WorkflowState

# ── 加载配置 ──
import yaml
with open(PROJECT_ROOT / "config.yaml") as f:
    raw = yaml.safe_load(f)

tenant_raw = None
for t in raw.get("tenants", []):
    if t.get("id") == "toutiao_ai_a":
        tenant_raw = t
        break

if not tenant_raw:
    print("❌ 未找到租户 toutiao_ai_a")
    sys.exit(1)

tenant = TenantConfig(**tenant_raw)

# ── 清空旧状态 ──
state_path = Path(f"data/今日头条/AI热点/A账号/state.json")
if state_path.exists():
    backup = state_path.read_text()
    state_path.unlink()
    print(f"📦 已备份旧状态 ({len(backup)} bytes) 并清除")

# ── 创建 workflow 并打补丁：终审后直接 END 不走 publish ──
wf = AgentWorkflow(tenant)

# 打补丁：修改 _route_after_final_review 让 publish → END
original_route = wf._route_after_final_review
def patched_route(state):
    stage = state.get("stage", "")
    print(f"  🚫 发布阶段被拦截 (stage={stage})，直接结束")
    return "__end__"

wf._route_after_final_review = patched_route

# 重新编译图
import langgraph.graph as lg
from langgraph.graph import StateGraph

builder = StateGraph(WorkflowState)
builder.add_node("search", wf._node_search)
builder.add_node("topic_collect", wf._node_topic_collect)
builder.add_node("main_review_topics", wf._node_main_review_topics)
builder.add_node("writer_draft", wf._node_writer_draft)
builder.add_node("compliance_check", wf._node_compliance_check)
builder.add_node("main_final_review", wf._node_main_final_review)

builder.set_entry_point("search")
builder.add_edge("search", "topic_collect")
builder.add_edge("topic_collect", "main_review_topics")
builder.add_edge("compliance_check", "main_final_review")

builder.add_conditional_edges(
    "main_review_topics",
    wf._route_after_topic_review,
)

builder.add_conditional_edges(
    "main_final_review",
    wf._route_after_final_review,
)

builder.add_edge("writer_draft", "compliance_check")

# 不添加 publish 节点
wf.graph = builder.compile()

# ── 运行 ──
print("=" * 60)
print("🤖 运行头条工作流（仅收集→文章生成，不发布）")
print("   流程: 搜索 → 选题 → 写作 → 合规 → 终审 → 结束")
print("=" * 60)

try:
    result = wf.run()
except Exception as e:
    print(f"\n❌ 工作流异常: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# ── 输出结果 ──
print("\n" + "=" * 60)
print("📋 运行结果")
print("=" * 60)

stage = result.get("stage", "")
print(f"  阶段: {stage}")
print(f"  选题: {len(result.get('topic_list', []))} 个")
print(f"  选中: {len(result.get('selected_topics', []))} 个")
print(f"  文章: {len(result.get('articles', []))} 篇")

articles = result.get("articles", [])
if articles:
    for i, art in enumerate(articles):
        title = art.get("title", "未知标题")
        wc = art.get("word_count", 0)
        sr = art.get("self_review", {})
        flag = "✅" if sr.get("passed") else "⚠️"
        print(f"\n  {'='*50}")
        print(f"  {flag} 文章 #{i+1}: {title}")
        print(f"    字数: {wc}")
        print(f"    自审: {sr.get('summary', 'N/A')}")
        if sr.get("issues"):
            for issue in sr.get("issues", []):
                print(f"    ⚠️ {issue}")
        # 打印前200字预览
        content = art.get("content", "")
        print(f"    预览: {content[:200]}...")
        print(f"  {'='*50}")

# 打印合规报告
reports = result.get("compliance_reports", [])
if reports:
    print(f"\n  合规报告: {len(reports)} 份")
    for i, r in enumerate(reports):
        flag = "✅" if r.get("passed") else "⚠️"
        print(f"    {flag} #{i+1}: {r.get('final_verdict', '?')} ({r.get('score', 0)}分)")

# 清理 state.json 以免下次 --full 发布时重复
state_path = Path(f"data/今日头条/AI热点/A账号/state.json")
if state_path.exists():
    # 保存文章内容到单独文件，供用户审阅
    output = {"articles": articles, "selected_topics": result.get("selected_topics", []),
              "topic_list": result.get("topic_list", []), "compliance_reports": reports}
    output_path = Path("data/collect_only_output.json")
    output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2))

    # 如果是 __end__ 就删掉 state（防止下次自动发布）
    if stage == "__end__":
        state_path.unlink()
        print(f"\n📝 文章已保存到 data/collect_only_output.json")
        print(f"🗑️  已清除 state.json（防止下次 --full 误发）")
    else:
        print(f"\n⚠️ 工作流未完成（stage={stage}），state 保留以供恢复")

print("\n✅ 完成")
