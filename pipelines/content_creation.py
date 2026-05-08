"""内容创作 Pipeline — 搜索 → 选题 → 写作 → 合规 → 发布

这是系统内置的第一个 pipeline，也是默认 pipeline。
依赖 services/ 下的现有 Agent 工作流实现。
"""
from pipelines import register, BasePipeline
from models.tenant import TenantConfig
from services.workflow_graph import AgentWorkflow


@register("content_creation")
class ContentCreationPipeline(BasePipeline):
    """内容创作管线：搜索资讯 → AI 选题 → AI 写作 → 合规审核 → 发布"""

    def __init__(self, tenant: TenantConfig):
        super().__init__(tenant)
        self._workflow = AgentWorkflow(tenant)

    def run(self) -> dict:
        """执行完整内容创作流程"""
        state = self._workflow.repo.load_state()
        if state:
            print(f"  📂 检测到已保存状态（阶段: {state.get('stage', '?')}）")
            print(f"  🔄 从保存状态恢复执行，如需重新开始请先清除 state.json")

        result = self._workflow.run()
        return result
