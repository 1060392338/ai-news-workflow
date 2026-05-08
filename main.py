"""
AI 热点新闻工作流 — 多 Agent 入口

用法:
  完整流程:  python3 main.py --tenant toutiao_ai_a --full
  查看状态:  python3 main.py --tenant toutiao_ai_a --status
  查看日志:  python3 main.py --tenant toutiao_ai_a --logs
  列表租户:  python3 main.py --list-tenants
"""
import argparse
import sys
from pathlib import Path

from models.tenant import TenantConfig
from services.workflow_graph import AgentWorkflow

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))


def load_config() -> dict:
    import yaml
    with open(PROJECT_ROOT / "config.yaml") as f:
        return yaml.safe_load(f)


def get_tenant_config(raw: dict, tenant_id: str) -> dict:
    for t in raw.get("tenants", []):
        if t.get("id") == tenant_id:
            return t
    raise ValueError(f"租户 '{tenant_id}' 未找到")


def list_tenants(raw: dict):
    print("=" * 60)
    print("📋 已配置的租户:")
    print("=" * 60)
    for t in raw.get("tenants", []):
        s = "🟢" if t.get("enabled") else "🔴"
        print(f"  {s} [{t['id']}] {t['platform']} > {t['category']} > {t['account']}")


def main():
    raw_config = load_config()
    parser = argparse.ArgumentParser(description="AI 热点工作流 — 多 Agent")
    parser.add_argument("--tenant", default="toutiao_ai_a")
    parser.add_argument("--full", action="store_true", help="完整流程")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--logs", action="store_true")
    parser.add_argument("--list-tenants", action="store_true")

    args = parser.parse_args()

    if args.list_tenants:
        list_tenants(raw_config)
        return

    tenant = TenantConfig(**get_tenant_config(raw_config, args.tenant))
    wf = AgentWorkflow(tenant)

    if args.status:
        state = wf.repo.load_state()
        if not state:
            print(f"📭 [{args.tenant}] 无保存状态")
            return
        print(f"📋 [{args.tenant}] 状态:")
        print(f"   阶段: {state.get('stage', 'N/A')}")
        print(f"   选题: {len(state.get('topic_list', []))} 个")
        print(f"   选中: {len(state.get('selected_topics', []))} 个")
        print(f"   文章: {len(state.get('articles', []))} 篇")
        print(f"   发布: {len(state.get('publish_results', []))} 条")
        print(f"   错误: {len(state.get('errors', []))} 条")
        for e in state.get("errors", []):
            print(f"     · {e}")
        return

    if args.logs:
        logs = wf.repo.get_publish_logs(10)
        if not logs:
            print(f"📭 [{args.tenant}] 暂无发布记录")
            return
        print(f"📋 [{args.tenant}] 最近发布:")
        for log in logs:
            s = "✅" if log.success else "❌"
            print(f"  {s} {log.created_at[:19]} | {log.article_title[:40]}")

    if args.full:
        print("=" * 60)
        print(f"🤖 {tenant.display_name} — 多 Agent 工作流启动")
        print(f"   Agent: 主Agent+选题Agent+写作Agent+合规Agent")
        print("=" * 60)
        wf.run()

        # 检查最终状态
        state = wf.repo.load_state()
        stage = state.get("stage", "") if state else "N/A"
        print(f"\n{'='*60}")
        if stage == "__end__" or not state:
            print("✅ 流程完成")
        else:
            print(f"⏸️  流程暂停于: {stage}")
            articles = state.get("articles", []) if state else []
            posts = state.get("publish_results", []) if state else []
            print(f"   文章: {len(articles)} 篇 | 发布: {len(posts)} 条")
            for e in (state or {}).get("errors", []):
                print(f"   ⚠️ {e}")
        return

    parser.print_help()


if __name__ == "__main__":
    main()
