"""租户感知的 SQLite 数据库操作"""
import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from models.article import PublishLog
from models.tenant import TenantConfig


class Repository:
    """
    数据持久化层，按 平台/类别/账号 三层目录隔离。
    每个账号独立 SQLite + 状态 JSON + Cookie。
    """

    def __init__(self, tenant: TenantConfig):
        self.tenant = tenant
        # 数据根目录 → data/今日头条/AI热点/A账号/
        base = Path(os.path.expanduser(
            "~/.hermes/ai-news-workflow"
        )) / tenant.data_dir
        base.mkdir(parents=True, exist_ok=True)
        self._db_path = base / "articles.db"
        self._state_path = base / "state.json"
        self._init_db()

    # ---- 数据库 ----

    def _init_db(self):
        conn = sqlite3.connect(str(self._db_path))
        conn.execute("""
            CREATE TABLE IF NOT EXISTS publish_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id TEXT NOT NULL,
                platform TEXT NOT NULL,
                category TEXT NOT NULL,
                account TEXT NOT NULL,
                article_title TEXT NOT NULL,
                article_content TEXT DEFAULT '',
                success INTEGER DEFAULT 0,
                url TEXT DEFAULT '',
                error TEXT DEFAULT '',
                created_at TEXT DEFAULT ''
            )
        """)
        conn.commit()
        conn.close()

    def save_publish_log(self, log: PublishLog) -> int:
        conn = sqlite3.connect(str(self._db_path))
        conn.execute(
            """INSERT INTO publish_log
               (tenant_id, platform, category, account,
                article_title, article_content,
                success, url, error, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (log.tenant_id,
             self.tenant.platform, self.tenant.category, self.tenant.account,
             log.article_title, log.article_content,
             1 if log.success else 0, log.url, log.error,
             datetime.now().isoformat())
        )
        conn.commit()
        row_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.close()
        return row_id

    def get_publish_logs(self, limit: int = 20) -> list[PublishLog]:
        conn = sqlite3.connect(str(self._db_path))
        rows = conn.execute(
            "SELECT * FROM publish_log ORDER BY id DESC LIMIT ?",
            (limit,)
        ).fetchall()
        conn.close()
        results = []
        for row in rows:
            results.append(PublishLog(
                id=row[0], tenant_id=row[1], platform=row[2],
                category=row[3], article_title=row[4],
                article_content=row[5], success=bool(row[6]),
                url=row[7], error=row[8], created_at=row[9],
            ))
        return results

    def get_today_count(self) -> int:
        today = datetime.now().strftime("%Y-%m-%d")
        conn = sqlite3.connect(str(self._db_path))
        count = conn.execute(
            "SELECT COUNT(*) FROM publish_log "
            "WHERE created_at LIKE ? AND success=1",
            (f"{today}%",)
        ).fetchone()[0]
        conn.close()
        return count

    # ---- 工作流状态 checkpoint ----

    def save_state(self, state: dict):
        state["_updated_at"] = datetime.now().isoformat()
        state["_tenant_id"] = self.tenant.id
        state["_platform"] = self.tenant.platform
        state["_category"] = self.tenant.category
        state["_account"] = self.tenant.account
        with open(self._state_path, "w") as f:
            json.dump(state, f, ensure_ascii=False, indent=2, default=str)

    def load_state(self) -> Optional[dict]:
        if not self._state_path.exists():
            return None
        with open(self._state_path, "r") as f:
            return json.load(f)

    def clear_state(self):
        if self._state_path.exists():
            self._state_path.unlink()
