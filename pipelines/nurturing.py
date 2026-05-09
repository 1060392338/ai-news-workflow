"""养号 Pipeline — 新账号培育专用

与 content_creation 共用同一套 Agent 工作流，但附加养号策略：
- 每天最多发 1 篇（新手期降频）
- 自动勾选话题标签（增加推荐精准度）
- 记录每日发布状态，避免超发
"""
import json
from datetime import date
from pathlib import Path

from pipelines import register, BasePipeline
from models.tenant import TenantConfig
from services.workflow_graph import AgentWorkflow


@register("nurturing")
class NurturingPipeline(BasePipeline):
    """养号管线：在 content_creation 基础上添加新号培育逻辑"""

    DAILY_LIMIT = 1  # 新手期每天最多发 1 篇

    def __init__(self, tenant: TenantConfig):
        super().__init__(tenant)
        self._workflow = AgentWorkflow(tenant)

    def run(self) -> dict:
        """执行养号流程"""
        # 1. 检查今日是否已发布
        if self._reached_daily_limit():
            print(f"  ⏸️ 今日已达发布上限 ({self.DAILY_LIMIT}篇)，跳过")
            return {"stage": "__end__", "message": "daily limit reached"}

        # 2. 执行正常内容创作流程
        state = self._workflow.repo.load_state()
        if state:
            print(f"  📂 检测到已保存状态（阶段: {state.get('stage', '?')}）")
            print(f"  🔄 从保存状态恢复执行")

        result = self._workflow.run()

        # 3. 记录今日发布
        if result.get("publish_results"):
            self._record_publish_today()

        return result

    def _reached_daily_limit(self) -> bool:
        """检查今日发布次数是否已达上限"""
        record_path = self._get_record_path()
        if record_path.exists():
            with open(record_path) as f:
                record = json.load(f)
            today = str(date.today())
            count = record.get(today, 0)
            return count >= self.DAILY_LIMIT
        return False

    def _record_publish_today(self):
        """记录今日已发布"""
        record_path = self._get_record_path()
        today = str(date.today())
        record = {}
        if record_path.exists():
            with open(record_path) as f:
                record = json.load(f)
        record[today] = record.get(today, 0) + 1
        record_path.parent.mkdir(parents=True, exist_ok=True)
        with open(record_path, "w") as f:
            json.dump(record, f, indent=2)
        count = record[today]
        print(f"  📊 今日已发布 {count}/{self.DAILY_LIMIT} 篇")

    def _get_record_path(self) -> Path:
        """获取发布记录文件路径"""
        base = Path.cwd() / "data" / self.tenant.platform / self.tenant.category / self.tenant.account
        return base / "publish_record.json"
