"""
读取输入 JSONL（字段 i/n/p/t），经 mock 匹配后写出增强 JSONL。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from crawler.mock_source import match_filename_to_entity, step1_mock_discover


def _parse_jsonl(text: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def _norm_tags(raw: Any) -> List[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        return []
    out: List[str] = []
    for x in raw:
        s = str(x).strip()
        if s and s not in out and len(s) <= 200:
            out.append(s)
    return out


def run_pipeline(input_path: Path, output_path: Path) -> Dict[str, Any]:
    text = input_path.read_text(encoding="utf-8-sig")
    rows_in = _parse_jsonl(text)
    registry = step1_mock_discover()

    enriched: List[Dict[str, Any]] = []
    skipped_no_match = 0
    skipped_bad = 0

    for row in rows_in:
        if "i" not in row:
            skipped_bad += 1
            continue
        try:
            int(row["i"])
        except (TypeError, ValueError):
            skipped_bad += 1
            continue

        fn = row.get("n") or ""
        match = match_filename_to_entity(fn, registry)
        if not match:
            skipped_no_match += 1
            continue

        input_tags = _norm_tags(row.get("t"))
        mock_tags = _norm_tags(match.get("tags"))
        merged = list(dict.fromkeys(input_tags + mock_tags))

        out_row: Dict[str, Any] = {
            "i": row["i"],
            "n": row.get("n"),
            "p": row.get("p"),
            "t": merged,
            "input_t": input_tags,
            "code": match.get("code"),
            "actor_name": match.get("actor_name"),
            "matched_by": match.get("matched_by"),
        }
        if match.get("cover_url"):
            out_row["cover_url"] = match["cover_url"]
        if match.get("notes"):
            out_row["mock_notes"] = match["notes"]

        # 去掉值为 None 的键，便于阅读
        enriched.append({k: v for k, v in out_row.items() if v is not None})

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        for r in enriched:
            f.write(json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n")

    return {
        "lines_in": len(rows_in),
        "lines_out": len(enriched),
        "skipped_no_match": skipped_no_match,
        "skipped_bad": skipped_bad,
    }
