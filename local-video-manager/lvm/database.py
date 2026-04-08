"""SQLite 连接与表结构。"""
import sqlite3
from pathlib import Path

from lvm.config_store import ensure_data_dirs, load_config
from lvm.logging_config import LOG


def db_path() -> Path:
    cfg = load_config()
    data_dir = Path(cfg["data_dir"]).expanduser().resolve()
    ensure_data_dirs(data_dir)
    return data_dir / "video_manager.db"


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path()))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    init_db(conn)
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS videos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            path TEXT NOT NULL UNIQUE,
            filename TEXT NOT NULL,
            size_bytes INTEGER NOT NULL DEFAULT 0,
            duration_sec REAL NOT NULL DEFAULT 0,
            modified_at INTEGER NOT NULL DEFAULT 0,
            created_at INTEGER NOT NULL DEFAULT 0,
            watch_count INTEGER NOT NULL DEFAULT 0,
            cover_file TEXT,
            search_text TEXT NOT NULL DEFAULT '',
            indexed_at INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            is_auto INTEGER NOT NULL DEFAULT 0,
            created_at INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS video_tags (
            video_id INTEGER NOT NULL,
            tag_id INTEGER NOT NULL,
            source TEXT NOT NULL DEFAULT 'manual',
            created_at INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (video_id, tag_id),
            FOREIGN KEY(video_id) REFERENCES videos(id) ON DELETE CASCADE,
            FOREIGN KEY(tag_id) REFERENCES tags(id) ON DELETE CASCADE
        );
        """
    )
    conn.commit()
    migrate_db(conn)


def migrate_db(conn: sqlite3.Connection) -> None:
    cols = {row[1] for row in conn.execute("PRAGMA table_info(videos)").fetchall()}
    if "recycled_at" not in cols:
        conn.execute("ALTER TABLE videos ADD COLUMN recycled_at INTEGER")
        LOG.info("数据库迁移: 已添加列 videos.recycled_at")
        conn.commit()
