"""
PT 站点数据管理 Service
- SQLite 数据库：站点配置、数据快照、访问日志
- 站点的 Cookie 等信息存 SQLite（由前端界面管理，不放在 config.yaml）
"""

import sqlite3
import time
import json
import logging
from pathlib import Path
from typing import Optional
from datetime import datetime

logger = logging.getLogger(__name__)

DB_DIR = Path(__file__).parent.parent.parent / "data"
DB_DIR.mkdir(exist_ok=True)
DB_PATH = DB_DIR / "pt_sites.db"


def _now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _now_ts() -> int:
    return int(time.time())


class PtDatabase:
    """SQLite 数据库管理"""

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = str(db_path)
        self._init_db()
        self._migrate()

    def _get_conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_db(self):
        with self._get_conn() as conn:
            conn.executescript("""
                -- PT 站点配置表
                CREATE TABLE IF NOT EXISTS pt_sites (
                    id          TEXT PRIMARY KEY,          -- 站点 ID (slug, e.g. 'mteam')
                    name        TEXT NOT NULL,             -- 站点名称
                    url         TEXT NOT NULL,             -- 站点首页地址
                    cookie      TEXT DEFAULT '',           -- 登录 Cookie
                    auth_type   TEXT DEFAULT 'cookie',     -- 认证方式: cookie / local_storage
                    local_storage TEXT DEFAULT '',         -- localStorage 键值对 (JSON)
                    user_agent  TEXT DEFAULT '',           -- 自定义 UA（可选）
                    visit_freq  INTEGER DEFAULT 2,        -- 每天访问次数
                    visit_times TEXT DEFAULT '08:00,20:00', -- 自定义访问时间
                    enabled     INTEGER DEFAULT 1,         -- 是否启用
                    notes       TEXT DEFAULT '',           -- 备注
                    created_at  TEXT NOT NULL,
                    updated_at  TEXT NOT NULL
                );

                -- 用户手动跳转时间记录（用于活跃度计算）
                CREATE TABLE IF NOT EXISTS pt_user_visits (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    site_id     TEXT NOT NULL,
                    visit_type  TEXT NOT NULL DEFAULT 'manual',  -- manual / scheduled
                    visited_at  TEXT NOT NULL,
                    FOREIGN KEY (site_id) REFERENCES pt_sites(id) ON DELETE CASCADE
                );

                -- 数据快照表（每次访问记录一次数据）
                CREATE TABLE IF NOT EXISTS pt_snapshots (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    site_id     TEXT NOT NULL,
                    upload_bytes     BIGINT DEFAULT 0,     -- 上传量 (字节)
                    download_bytes   BIGINT DEFAULT 0,     -- 下载量 (字节)
                    seed_points      REAL DEFAULT 0,       -- 做种积分
                    bonus_points     REAL DEFAULT 0,       -- 魔力值/ bonus
                    share_ratio      REAL DEFAULT 0,       -- 分享率
                    seeding_count    INTEGER DEFAULT 0,    -- 做种数
                    leeching_count   INTEGER DEFAULT 0,    -- 下载中数
                    raw_data         TEXT DEFAULT '{}',    -- 原始解析数据 JSON
                    captured_at      TEXT NOT NULL,
                    FOREIGN KEY (site_id) REFERENCES pt_sites(id) ON DELETE CASCADE
                );

                -- 访问日志表
                CREATE TABLE IF NOT EXISTS pt_visit_logs (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    site_id     TEXT NOT NULL,
                    visit_type  TEXT NOT NULL DEFAULT 'scheduled', -- scheduled / manual / retry
                    success     INTEGER NOT NULL DEFAULT 1,
                    message     TEXT DEFAULT '',
                    details     TEXT DEFAULT '',
                    created_at  TEXT NOT NULL,
                    FOREIGN KEY (site_id) REFERENCES pt_sites(id) ON DELETE CASCADE
                );

                -- 索引
                CREATE INDEX IF NOT EXISTS idx_snapshots_site ON pt_snapshots(site_id, captured_at DESC);
                CREATE INDEX IF NOT EXISTS idx_visit_logs_site ON pt_visit_logs(site_id, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_user_visits_site ON pt_user_visits(site_id, visited_at DESC);
            """)

    def _migrate(self):
        """增量迁移：给已有表添加新列"""
        migrations = [
            "ALTER TABLE pt_sites ADD COLUMN auth_type TEXT DEFAULT 'cookie'",
            "ALTER TABLE pt_sites ADD COLUMN local_storage TEXT DEFAULT ''",
        ]
        with self._get_conn() as conn:
            existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(pt_sites)").fetchall()}
            for sql in migrations:
                col_name = sql.split("ADD COLUMN ")[1].split(" ")[0]
                if col_name not in existing_cols:
                    try:
                        conn.execute(sql)
                        logger.info(f"[PT DB] 迁移: {sql}")
                    except Exception as e:
                        logger.warning(f"[PT DB] 迁移失败 (可忽略): {e}")

    # ========== 站点 CRUD ==========

    def list_sites(self, enabled_only: bool = False) -> list:
        """列出所有站点"""
        sql = "SELECT * FROM pt_sites"
        if enabled_only:
            sql += " WHERE enabled = 1"
        sql += " ORDER BY name"
        with self._get_conn() as conn:
            rows = conn.execute(sql).fetchall()
        return [dict(r) for r in rows]

    def get_site(self, site_id: str) -> Optional[dict]:
        with self._get_conn() as conn:
            row = conn.execute("SELECT * FROM pt_sites WHERE id = ?", (site_id,)).fetchone()
        return dict(row) if row else None

    def create_site(self, data: dict) -> dict:
        site_id = data["id"]
        now = _now_iso()
        with self._get_conn() as conn:
            conn.execute("""
                INSERT INTO pt_sites (id, name, url, cookie, auth_type, local_storage, user_agent, visit_freq, visit_times, enabled, notes, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                site_id,
                data["name"],
                data["url"],
                data.get("cookie", ""),
                data.get("auth_type", "cookie"),
                data.get("local_storage", ""),
                data.get("user_agent", ""),
                data.get("visit_freq", 2),
                data.get("visit_times", ""),
                data.get("enabled", 1),
                data.get("notes", ""),
                now,
                now,
            ))
        logger.info(f"[PT] 创建站点: {site_id} ({data['name']})")
        return self.get_site(site_id)

    def update_site(self, site_id: str, data: dict) -> Optional[dict]:
        existing = self.get_site(site_id)
        if not existing:
            return None

        updates = {}
        for key in ("name", "url", "cookie", "auth_type", "local_storage", "user_agent", "visit_freq", "visit_times", "enabled", "notes"):
            if key in data:
                updates[key] = data[key]
        if not updates:
            return existing

        updates["updated_at"] = _now_iso()

        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [site_id]
        with self._get_conn() as conn:
            conn.execute(f"UPDATE pt_sites SET {set_clause} WHERE id = ?", values)
        logger.info(f"[PT] 更新站点: {site_id}")
        return self.get_site(site_id)

    def delete_site(self, site_id: str) -> bool:
        with self._get_conn() as conn:
            cursor = conn.execute("DELETE FROM pt_sites WHERE id = ?", (site_id,))
            deleted = cursor.rowcount > 0
        if deleted:
            logger.info(f"[PT] 删除站点: {site_id}")
        return deleted

    # ========== 数据快照 ==========

    def save_snapshot(self, site_id: str, data: dict) -> int:
        """保存一次数据快照，返回快照 ID"""
        now = _now_iso()
        with self._get_conn() as conn:
            cursor = conn.execute("""
                INSERT INTO pt_snapshots (site_id, upload_bytes, download_bytes, seed_points, bonus_points,
                                          share_ratio, seeding_count, leeching_count, raw_data, captured_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                site_id,
                data.get("upload_bytes", 0),
                data.get("download_bytes", 0),
                data.get("seed_points", 0),
                data.get("bonus_points", 0),
                data.get("share_ratio", 0),
                data.get("seeding_count", 0),
                data.get("leeching_count", 0),
                json.dumps(data.get("raw_data", {}), ensure_ascii=False),
                now,
            ))
            snap_id = cursor.lastrowid
        return snap_id

    def get_latest_snapshot(self, site_id: str) -> Optional[dict]:
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM pt_snapshots WHERE site_id = ? ORDER BY captured_at DESC LIMIT 1",
                (site_id,),
            ).fetchone()
        return dict(row) if row else None

    def get_snapshots(self, site_id: str, limit: int = 30) -> list:
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM pt_snapshots WHERE site_id = ? ORDER BY captured_at DESC LIMIT ?",
                (site_id, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_site_summary(self, site_id: str) -> dict:
        """获取站点数据摘要（包含最新快照、今日变化等）"""
        latest = self.get_latest_snapshot(site_id)
        # 获取最早今天的数据计算变化
        today_start = datetime.now().strftime("%Y-%m-%d 00:00:00")
        with self._get_conn() as conn:
            first_today_row = conn.execute(
                "SELECT * FROM pt_snapshots WHERE site_id = ? AND captured_at >= ? ORDER BY captured_at ASC LIMIT 1",
                (site_id, today_start),
            ).fetchone()

        summary = {
            "latest": latest,
            "today_delta": {},
        }

        if latest and first_today_row:
            first_today = dict(first_today_row)
            if first_today["id"] != latest["id"]:  # 有变化才计算
                summary["today_delta"] = {
                    "upload_bytes": latest["upload_bytes"] - first_today["upload_bytes"],
                    "download_bytes": latest["download_bytes"] - first_today["download_bytes"],
                    "seed_points": latest["seed_points"] - first_today["seed_points"],
                    "bonus_points": latest["bonus_points"] - first_today["bonus_points"],
                }
        return summary

    # ========== 访问日志 ==========

    def log_visit(self, site_id: str, visit_type: str, success: bool, message: str = "", details: str = ""):
        """记录一次访问"""
        now = _now_iso()
        with self._get_conn() as conn:
            conn.execute(
                "INSERT INTO pt_visit_logs (site_id, visit_type, success, message, details, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (site_id, visit_type, 1 if success else 0, message, details, now),
            )

    def get_visit_logs(self, site_id: str = None, limit: int = 50) -> list:
        """获取访问日志"""
        if site_id:
            sql = "SELECT * FROM pt_visit_logs WHERE site_id = ? ORDER BY created_at DESC LIMIT ?"
            params = (site_id, limit)
        else:
            sql = "SELECT * FROM pt_visit_logs ORDER BY created_at DESC LIMIT ?"
            params = (limit,)
        with self._get_conn() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    # ========== 用户手动访问 ==========

    def record_user_visit(self, site_id: str, visit_type: str = "manual"):
        """记录用户手动跳转访问"""
        now = _now_iso()
        with self._get_conn() as conn:
            conn.execute(
                "INSERT INTO pt_user_visits (site_id, visit_type, visited_at) VALUES (?, ?, ?)",
                (site_id, visit_type, now),
            )

    def get_last_user_visit(self, site_id: str) -> Optional[str]:
        """获取用户最后一次手动 Playwright 刷新时间"""
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT created_at FROM pt_visit_logs WHERE site_id = ? AND visit_type = 'manual' AND success = 1 ORDER BY created_at DESC LIMIT 1",
                (site_id,),
            ).fetchone()
            return row["created_at"] if (row and row["created_at"]) else None

    def get_last_redirect_time(self, site_id: str) -> Optional[str]:
        """获取用户最后一次链接跳转时间"""
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT created_at FROM pt_visit_logs WHERE site_id = ? AND visit_type = 'redirect' AND success = 1 ORDER BY created_at DESC LIMIT 1",
                (site_id,),
            ).fetchone()
            return row["created_at"] if (row and row["created_at"]) else None

    def get_last_success_time(self, site_id: str) -> Optional[str]:
        """获取最后一次成功的 Playwright 访问时间（scheduled 或 manual）"""
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT created_at FROM pt_visit_logs WHERE site_id = ? AND success = 1 AND visit_type IN ('scheduled', 'manual') ORDER BY created_at DESC LIMIT 1",
                (site_id,),
            ).fetchone()
        return row["created_at"] if row else None


# 全局单例
db = PtDatabase()
