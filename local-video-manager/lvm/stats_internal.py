"""系统统计：数据库聚合、磁盘、CPU 抽样、磁盘 IO 抽样。"""
import random
import shutil
import time
from pathlib import Path
from typing import Dict, List

import sqlite3

from lvm.database import db_path, get_conn


def db_usage_stats(conn: sqlite3.Connection) -> Dict:
    row = conn.execute(
        """
        SELECT
            COALESCE(SUM(CASE WHEN recycled_at IS NULL THEN 1 ELSE 0 END), 0) AS n,
            COALESCE(SUM(CASE WHEN recycled_at IS NOT NULL THEN 1 ELSE 0 END), 0) AS n_recycled,
            COALESCE(SUM(CASE WHEN recycled_at IS NULL THEN size_bytes ELSE 0 END), 0) AS total_bytes,
            COALESCE(SUM(CASE WHEN recycled_at IS NULL THEN watch_count ELSE 0 END), 0) AS total_watches,
            COALESCE(SUM(CASE WHEN recycled_at IS NULL THEN duration_sec ELSE 0 END), 0) AS total_duration,
            COALESCE(
                AVG(CASE WHEN recycled_at IS NULL THEN duration_sec ELSE NULL END),
                0
            ) AS avg_duration,
            COALESCE(
                SUM(
                    CASE
                        WHEN recycled_at IS NULL AND cover_file IS NOT NULL AND cover_file != ''
                        THEN 1 ELSE 0
                    END
                ),
                0
            ) AS with_cover
        FROM videos
        """
    ).fetchone()
    tag_n = conn.execute("SELECT COUNT(*) AS c FROM tags").fetchone()["c"]
    link_n = conn.execute("SELECT COUNT(*) AS c FROM video_tags").fetchone()["c"]
    return {
        "video_count": int(row["n"] or 0),
        "recycled_count": int(row["n_recycled"] or 0),
        "tag_count": int(tag_n),
        "video_tag_links": int(link_n),
        "total_bytes": int(row["total_bytes"] or 0),
        "total_watch_events": int(row["total_watches"] or 0),
        "total_duration_sec": round(float(row["total_duration"] or 0), 2),
        "avg_duration_sec": round(float(row["avg_duration"] or 0), 2),
        "videos_with_cover": int(row["with_cover"] or 0),
    }


def disk_usage_stats(data_dir: Path) -> Dict:
    data_dir = data_dir.resolve()
    du = shutil.disk_usage(data_dir)
    db_file = db_path()
    db_size = db_file.stat().st_size if db_file.exists() else 0
    covers_dir = data_dir / "covers"
    cov_size = 0
    cov_files = 0
    if covers_dir.is_dir():
        try:
            for ch in covers_dir.iterdir():
                if ch.is_file():
                    try:
                        cov_size += ch.stat().st_size
                        cov_files += 1
                    except OSError:
                        pass
        except OSError:
            pass
    return {
        "data_dir": str(data_dir),
        "disk_total_gb": round(du.total / (1024**3), 2),
        "disk_free_gb": round(du.free / (1024**3), 2),
        "disk_used_percent": round(100.0 * (1.0 - du.free / du.total), 1) if du.total else 0.0,
        "db_file_mb": round(db_size / (1024**2), 2),
        "covers_dir_mb": round(cov_size / (1024**2), 2),
        "cover_file_count": cov_files,
    }


def system_snapshot() -> Dict:
    out: Dict = {}
    try:
        import psutil  # type: ignore

        out["cpu_percent"] = round(psutil.cpu_percent(interval=0.15), 1)
        vm = psutil.virtual_memory()
        out["memory_percent"] = round(vm.percent, 1)
        out["memory_used_gb"] = round(vm.used / (1024**3), 2)
        out["memory_total_gb"] = round(vm.total / (1024**3), 2)
    except Exception as e:
        out["psutil_error"] = str(e)
    return out


def sample_disk_io(sample_size: int) -> Dict:
    """从已入库视频中随机抽样，测量 stat 与首 4KB 读取耗时（仅用户主动触发时调用）。"""
    conn = get_conn()
    rows = conn.execute("SELECT id, path FROM videos WHERE recycled_at IS NULL").fetchall()
    conn.close()
    if not rows:
        return {
            "sample_n": 0,
            "stat_ms": 0.0,
            "read_4k_ms": 0.0,
            "missing_files": 0,
            "bytes_read": 0,
        }
    n = max(5, min(sample_size, 100))
    picked = random.sample(list(rows), min(n, len(rows)))
    missing = 0
    t0 = time.perf_counter()
    for r in picked:
        p = Path(r["path"])
        if p.is_file():
            try:
                p.stat()
            except OSError:
                missing += 1
        else:
            missing += 1
    t1 = time.perf_counter()
    stat_ms = round((t1 - t0) * 1000.0, 2)

    br = 0
    t2 = time.perf_counter()
    for r in picked:
        p = Path(r["path"])
        if not p.is_file():
            continue
        try:
            with open(p, "rb") as fh:
                br += len(fh.read(4096))
        except OSError:
            pass
    t3 = time.perf_counter()
    read_ms = round((t3 - t2) * 1000.0, 2)
    return {
        "sample_n": len(picked),
        "stat_ms": stat_ms,
        "read_4k_ms": read_ms,
        "missing_files": missing,
        "bytes_read": br,
    }
