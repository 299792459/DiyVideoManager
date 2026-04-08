"""标签 JSONL 规范化、整批替换、导入预览。"""
import json
import time
from typing import Dict, List, Optional

import sqlite3

from lvm.constants import APP_DIR
from lvm.database import get_conn


def make_search_text(filename: str, tags: List[str]) -> str:
    return f"{filename.lower()} {' '.join(t.lower() for t in tags)}"


def read_tags_llm_readme() -> str:
    p = APP_DIR / "docs" / "TAGS_LLM_README.md"
    if p.is_file():
        return p.read_text(encoding="utf-8")
    return "# 未找到 docs/TAGS_LLM_README.md\n"


def normalize_import_tag_list(raw) -> List[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        return []
    out: List[str] = []
    for x in raw:
        s = str(x).strip()
        if not s or len(s) > 200:
            continue
        if s not in out:
            out.append(s)
    return out


def tags_list_equal(a: List[str], b: List[str]) -> bool:
    return sorted(a) == sorted(b)


def video_tag_names(conn: sqlite3.Connection, video_id: int) -> List[str]:
    rows = conn.execute(
        """
        SELECT t.name
        FROM video_tags vt
        JOIN tags t ON t.id = vt.tag_id
        WHERE vt.video_id = ?
        ORDER BY t.name
        """,
        (video_id,),
    ).fetchall()
    return [r[0] for r in rows]


def preview_tags_import(text: str, strict_path: bool) -> Dict:
    """解析 JSONL，统计将应用的行与示例，不写库。"""
    lines_nonempty = 0
    would_apply = 0
    skipped_no_video = 0
    skipped_path = 0
    skipped_no_t = 0
    unchanged = 0
    errors: List[Dict] = []
    samples: List[Dict] = []

    conn = get_conn()
    try:
        for line_no, line in enumerate(text.splitlines(), 1):
            line = line.strip()
            if not line:
                continue
            lines_nonempty += 1
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as e:
                errors.append({"line": line_no, "error": f"json: {e}"})
                continue
            if not isinstance(obj, dict):
                errors.append({"line": line_no, "error": "line is not a JSON object"})
                continue
            if "i" not in obj:
                errors.append({"line": line_no, "error": "missing i"})
                continue
            try:
                vid = int(obj["i"])
            except (TypeError, ValueError):
                errors.append({"line": line_no, "error": "invalid i"})
                continue
            if "t" not in obj:
                skipped_no_t += 1
                continue
            row = conn.execute(
                "SELECT id, path, filename FROM videos WHERE id = ?", (vid,)
            ).fetchone()
            if not row:
                skipped_no_video += 1
                continue
            if strict_path and "p" in obj and obj["p"] is not None:
                p_in = str(obj["p"])
                if p_in and p_in != row["path"]:
                    skipped_path += 1
                    continue
            new_tags = normalize_import_tag_list(obj.get("t"))
            old_tags = video_tag_names(conn, vid)
            if tags_list_equal(old_tags, new_tags):
                unchanged += 1
            would_apply += 1
            if len(samples) < 15:
                samples.append(
                    {
                        "i": vid,
                        "n": row["filename"],
                        "old": old_tags,
                        "new": new_tags,
                    }
                )
    finally:
        conn.close()

    return {
        "ok": True,
        "lines_nonempty": lines_nonempty,
        "would_apply": would_apply,
        "unchanged": unchanged,
        "would_change": max(0, would_apply - unchanged),
        "skipped_no_video": skipped_no_video,
        "skipped_path": skipped_path,
        "skipped_no_t": skipped_no_t,
        "errors": errors,
        "samples": samples,
    }


def set_video_tags_replace(conn: sqlite3.Connection, video_id: int, tag_names: List[str]) -> None:
    """清空该视频原有关联后，写入新标签列表（source=import），并更新 search_text。"""
    now = int(time.time())
    conn.execute("DELETE FROM video_tags WHERE video_id = ?", (video_id,))
    row = conn.execute("SELECT filename FROM videos WHERE id = ?", (video_id,)).fetchone()
    if not row:
        raise ValueError("video not found")
    filename = row["filename"]
    for name in tag_names:
        conn.execute(
            "INSERT INTO tags(name, is_auto, created_at) VALUES(?, 0, ?) ON CONFLICT(name) DO NOTHING",
            (name, now),
        )
        tr = conn.execute("SELECT id FROM tags WHERE name = ?", (name,)).fetchone()
        conn.execute(
            "INSERT INTO video_tags(video_id, tag_id, source, created_at) VALUES(?,?, 'import', ?)",
            (video_id, tr["id"], now),
        )
    conn.execute(
        "UPDATE videos SET search_text = ? WHERE id = ?",
        (make_search_text(filename, tag_names), video_id),
    )
