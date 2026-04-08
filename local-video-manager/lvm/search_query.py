"""列表查询、关键词扩展与排序辅助。"""
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import sqlite3

from lvm.constants import QUERY_SYNONYMS


def extract_filename_tokens(filename: str) -> List[str]:
    base = Path(filename).stem.lower()
    ascii_tokens = re.findall(r"[a-z0-9]{2,}", base)
    zh_blocks = re.findall(r"[\u4e00-\u9fff]{2,}", base)
    zh_ngrams = []
    for b in zh_blocks:
        for i in range(len(b) - 1):
            zh_ngrams.append(b[i : i + 2])
    return ascii_tokens + zh_blocks + zh_ngrams


def expand_query_terms(q: str) -> List[str]:
    q = q.strip().lower()
    if not q:
        return []
    terms = {q}
    terms.update(re.findall(r"[a-z0-9]{2,}", q))
    for block in re.findall(r"[\u4e00-\u9fff]+", q):
        terms.add(block)
        for i in range(len(block)):
            terms.add(block[i])
        for i in range(len(block) - 1):
            terms.add(block[i : i + 2])
    for t in list(terms):
        if t in QUERY_SYNONYMS:
            terms.update(QUERY_SYNONYMS[t])
    return [t for t in terms if t]


def calc_intent_score(text: str, terms: List[str]) -> float:
    if not terms:
        return 0
    text = text.lower()
    score = 0.0
    for t in terms:
        if not t:
            continue
        if t in text:
            score += 3.0
        else:
            overlap = sum(1 for ch in t if ch in text)
            if overlap:
                score += overlap / max(len(t), 1)
    return score


def filter_videos_lexical_search(
    videos: List[Dict], search: str, *, include_path: bool = False
) -> List[Dict]:
    """本地关键词意图：与 GET /api/videos 一致（默认不含路径）；AI 回退时可含路径。"""
    if not search:
        return videos
    terms = expand_query_terms(search)
    scored: List[Tuple[float, Dict]] = []
    for v in videos:
        combined = f"{v['filename']} {' '.join(v.get('tags') or [])}"
        if include_path:
            combined += f" {v.get('path', '')}"
        combined = combined.lower()
        score = calc_intent_score(combined, terms)
        if score > 0:
            scored.append((score, v))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [x[1] for x in scored]


def normalize_tag_filters(names: Optional[List[str]]) -> List[str]:
    """去重、去空，保持顺序；用于 ?tags= 多参数与单参数 tag= 兼容。"""
    if not names:
        return []
    seen = set()
    out: List[str] = []
    for x in names:
        s = (x or "").strip()
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out[:24]


def list_video_rows(
    conn: sqlite3.Connection,
    tag_filters: Optional[List[str]],
    *,
    recycled_only: bool = False,
) -> List[sqlite3.Row]:
    conditions: List[str] = []
    params: List = []
    if recycled_only:
        conditions.append("v.recycled_at IS NOT NULL")
    else:
        conditions.append("v.recycled_at IS NULL")
    tf = normalize_tag_filters(tag_filters)
    if tf:
        n = len(tf)
        ph = ",".join(["?"] * n)
        conditions.append(
            f"""
            v.id IN (
                SELECT vt.video_id FROM video_tags vt
                JOIN tags t ON t.id = vt.tag_id
                WHERE t.name IN ({ph})
                GROUP BY vt.video_id
                HAVING COUNT(DISTINCT t.name) = ?
            )
            """
        )
        params.extend(tf)
        params.append(n)
    where_clause = "WHERE " + " AND ".join(conditions)

    sql = f"""
        SELECT
            v.*,
            GROUP_CONCAT(t.name, '|') AS tag_names,
            GROUP_CONCAT(t.id ORDER BY t.name, '|') AS tag_ids
        FROM videos v
        LEFT JOIN video_tags vt ON vt.video_id = v.id
        LEFT JOIN tags t ON t.id = vt.tag_id
        {where_clause}
        GROUP BY v.id
    """
    return conn.execute(sql, params).fetchall()


def serialize_video_row(row: sqlite3.Row) -> Dict:
    tag_names_raw = row["tag_names"]
    tags = tag_names_raw.split("|") if tag_names_raw else []
    keys = row.keys()
    tag_ids_raw = row["tag_ids"] if "tag_ids" in keys else None
    ids = [int(x) for x in tag_ids_raw.split("|")] if tag_ids_raw else []
    n = min(len(ids), len(tags))
    tag_items = [{"id": ids[i], "name": tags[i]} for i in range(n)]
    recycled_at = row["recycled_at"] if "recycled_at" in keys else None
    return {
        "id": row["id"],
        "path": row["path"],
        "filename": row["filename"],
        "size_bytes": row["size_bytes"],
        "duration_sec": row["duration_sec"],
        "modified_at": row["modified_at"],
        "created_at": row["created_at"],
        "watch_count": row["watch_count"],
        "cover_url": f"/api/covers/{row['cover_file']}" if row["cover_file"] else "",
        "tags": tags,
        "tag_items": tag_items,
        "recycled": recycled_at is not None,
        "recycled_at": recycled_at,
    }
