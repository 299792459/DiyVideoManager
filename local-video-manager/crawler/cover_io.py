"""爬虫导入封面：下载 URL 并按与主程序一致的规则命名封面文件。"""
from __future__ import annotations

import hashlib
import re
import sqlite3
from pathlib import Path
from typing import Tuple
from urllib import error as url_error
from urllib import request as url_request


def crawler_dirs(data_dir: Path) -> Tuple[Path, Path, Path]:
    base = data_dir / "crawler"
    return base / "input", base / "output", base / "cache"


def safe_upload_basename(name: str, *, max_len: int = 120) -> str:
    base = Path(name or "").name
    if not base or ".." in base:
        return "upload.jsonl"
    base = re.sub(r"[^\w\u4e00-\u9fff.\- ()\[\]]+", "_", base).strip("._ ")
    if not base:
        return "upload.jsonl"
    return base[:max_len]


def cover_filename_for_resolved_path(resolved_path: str) -> str:
    return f"{hashlib.md5(resolved_path.encode('utf-8')).hexdigest()}.jpg"


def download_url_to_path(url: str, dest: Path) -> Tuple[bool, str]:
    if not (url or "").strip():
        return False, "empty url"
    try:
        req = url_request.Request(
            url.strip(),
            headers={"User-Agent": "local-video-manager/1.0 (crawler import)"},
        )
        with url_request.urlopen(req, timeout=90) as resp:
            data = resp.read()
        if len(data) > 25_000_000:
            return False, "response too large"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        return True, ""
    except (url_error.URLError, OSError, ValueError) as e:
        return False, str(e)


def replace_cover_from_url(
    conn: sqlite3.Connection,
    video_id: int,
    video_path: str,
    cover_url: str,
    cover_dir: Path,
) -> Tuple[bool, str]:
    """将远程封面保存为与抽帧规则一致的文件名，并更新数据库。"""
    vp = Path(video_path)
    if not vp.is_file():
        return False, "video file missing"
    cover_name = cover_filename_for_resolved_path(str(vp.resolve()))
    cover_path = cover_dir / cover_name
    ok, err = download_url_to_path(cover_url, cover_path)
    if not ok:
        return False, err or "download failed"
    old_row = conn.execute(
        "SELECT cover_file FROM videos WHERE id = ?", (video_id,)
    ).fetchone()
    old_name = old_row["cover_file"] if old_row else None
    conn.execute("UPDATE videos SET cover_file=? WHERE id=?", (cover_name, video_id))
    if old_name and old_name != cover_name:
        old_p = cover_dir / old_name
        try:
            if old_p.is_file() and old_p.resolve() != cover_path.resolve():
                old_p.unlink()
        except OSError:
            pass
    return True, ""
