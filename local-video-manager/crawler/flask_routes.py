"""爬虫相关 HTTP 路由（注册到主 Flask app，逻辑不在 app.py 内实现）。"""
from __future__ import annotations

import json
import logging
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List
from urllib.parse import quote as url_quote

from flask import Flask, jsonify, request, send_file

from crawler.cover_io import crawler_dirs, replace_cover_from_url, safe_upload_basename
from crawler.import_body import decode_tags_import_text, read_tags_import_request_body
from crawler.pipeline import run_pipeline


@dataclass(frozen=True)
class CrawlerFlaskDeps:
    """由 app.py 注入，避免爬虫包反向 import app（兼容 `python app.py` 启动）。"""

    log: logging.Logger
    load_config: Callable[[], Dict[str, Any]]
    ensure_data_dirs: Callable[[Path], None]
    get_conn: Callable[[], sqlite3.Connection]
    clear_tag_vector_cache: Callable[[], None]
    normalize_import_tag_list: Callable[..., List[str]]
    set_video_tags_replace: Callable[..., None]


def register_crawler_routes(app: Flask, deps: CrawlerFlaskDeps) -> None:
    d = deps

    @app.route("/api/crawler/run", methods=["POST"])
    def api_crawler_run():
        """上传待爬取 JSONL，写入 data/crawler/input，运行流水线，结果写入 data/crawler/output。"""
        if not request.files or not request.files.get("file"):
            return jsonify({"ok": False, "error": "missing multipart field file"}), 400
        f = request.files["file"]
        cfg = d.load_config()
        data_dir = Path(cfg["data_dir"]).expanduser().resolve()
        d.ensure_data_dirs(data_dir)
        inp_dir, out_dir, _ = crawler_dirs(data_dir)
        ts = int(time.time())
        in_name = f"{ts}_{safe_upload_basename(f.filename)}"
        in_path = inp_dir / in_name
        f.save(str(in_path))
        out_name = f"crawler_out_{ts}.jsonl"
        out_path = out_dir / out_name
        try:
            stats = run_pipeline(in_path, out_path)
        except Exception as e:
            d.log.exception("爬虫流水线失败")
            return (
                jsonify({"ok": False, "error": str(e), "input_saved": str(in_path)}),
                500,
            )
        d.log.info("爬虫完成 output=%s stats=%s", out_path, stats)
        return jsonify(
            {
                "ok": True,
                "input_saved": str(in_path),
                "output_file": out_name,
                "output_path": str(out_path),
                "download_url": "/api/crawler/download?f=" + url_quote(out_name, safe=""),
                **stats,
            }
        )

    @app.route("/api/crawler/download", methods=["GET"])
    def api_crawler_download():
        """仅允许下载 crawler/output 下的文件名（防路径穿越）。"""
        name = (request.args.get("f") or "").strip()
        if not name or name != Path(name).name or ".." in name:
            return jsonify({"ok": False, "error": "invalid f"}), 400
        cfg = d.load_config()
        data_dir = Path(cfg["data_dir"]).expanduser().resolve()
        _, out_dir, _ = crawler_dirs(data_dir)
        path = (out_dir / name).resolve()
        try:
            path.relative_to(out_dir.resolve())
        except ValueError:
            return "", 404
        if not path.is_file():
            return "", 404
        return send_file(str(path), as_attachment=True, download_name=name)

    @app.route("/api/crawler/import", methods=["POST"])
    def api_crawler_import():
        """
        导入爬虫输出的 JSONL：按 i 整批替换标签（字段 t），若存在 cover_url 则下载到 covers 并替换封面。
        查询参数 strict_path：与 /api/tags/import 一致。
        """
        strict_path = request.args.get("strict_path", "0").lower() in ("1", "true", "yes")
        err, raw_bytes = read_tags_import_request_body()
        if err:
            return jsonify({"ok": False, "error": err}), 400
        dec_err, text = decode_tags_import_text(raw_bytes)
        if dec_err:
            return jsonify({"ok": False, "error": dec_err}), 400

        cfg = d.load_config()
        data_dir = Path(cfg["data_dir"]).expanduser().resolve()
        cover_dir = data_dir / "covers"
        d.ensure_data_dirs(data_dir)

        updated_rows = 0
        updated_covers = 0
        skipped_no_video = 0
        skipped_path = 0
        skipped_no_t = 0
        skipped_recycled = 0
        errors: List[Dict] = []
        cover_errors: List[Dict] = []

        conn = d.get_conn()
        try:
            for line_no, line in enumerate(text.splitlines(), 1):
                line = line.strip()
                if not line:
                    continue
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
                    "SELECT id, path, recycled_at FROM videos WHERE id = ?", (vid,)
                ).fetchone()
                if not row:
                    skipped_no_video += 1
                    continue
                if row["recycled_at"] is not None:
                    skipped_recycled += 1
                    continue
                if strict_path and "p" in obj and obj["p"] is not None:
                    p_in = str(obj["p"])
                    if p_in and p_in != row["path"]:
                        skipped_path += 1
                        continue
                tags = d.normalize_import_tag_list(obj.get("t"))
                cu = (obj.get("cover_url") or "").strip()
                try:
                    d.set_video_tags_replace(conn, vid, tags)
                    cover_ok = False
                    if cu:
                        cover_ok, cerr = replace_cover_from_url(
                            conn, vid, row["path"], cu, cover_dir
                        )
                        if not cover_ok:
                            cover_errors.append(
                                {
                                    "line": line_no,
                                    "i": vid,
                                    "error": cerr or "cover failed",
                                }
                            )
                    conn.commit()
                    updated_rows += 1
                    if cu and cover_ok:
                        updated_covers += 1
                except Exception as e:
                    conn.rollback()
                    errors.append({"line": line_no, "error": str(e), "i": vid})
                    d.log.exception("爬虫导入行失败 line=%s id=%s", line_no, vid)
        finally:
            conn.close()

        if updated_rows:
            try:
                d.clear_tag_vector_cache()
            except Exception:
                d.log.exception("clear_tag_vector_cache after crawler import")

        d.log.info(
            "爬虫导入完成 rows=%s covers=%s skipped_no_video=%s skipped_path=%s skipped_no_t=%s recycled=%s",
            updated_rows,
            updated_covers,
            skipped_no_video,
            skipped_path,
            skipped_no_t,
            skipped_recycled,
        )
        return jsonify(
            {
                "ok": True,
                "updated": updated_rows,
                "covers_updated": updated_covers,
                "skipped_no_video": skipped_no_video,
                "skipped_path": skipped_path,
                "skipped_no_t": skipped_no_t,
                "skipped_recycled": skipped_recycled,
                "errors": errors,
                "cover_errors": cover_errors,
            }
        )
