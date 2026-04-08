import hashlib
import json
import logging
import math
import os
import random
import re
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib import error as url_error
from urllib import request as url_request

from flask import Flask, Response, jsonify, render_template, request, send_file

try:
    from intent_local import (
        apply_intent_hybrid_search,
        clear_tag_vector_cache,
        is_fastembed_available,
        probe_intent_model,
    )
except ImportError:

    def is_fastembed_available() -> bool:
        return False

    def apply_intent_hybrid_search(*args, **kwargs):  # type: ignore[no-untyped-def]
        return []

    def clear_tag_vector_cache() -> None:
        pass

    def probe_intent_model(model_name: str) -> Dict:
        return {"ok": False, "error": "intent_local 模块不可用"}


APP_DIR = Path(__file__).resolve().parent
CONFIG_PATH = APP_DIR / "config.json"
VIDEO_EXTENSIONS = {".mp4", ".mkv", ".avi", ".mov", ".flv", ".wmv", ".webm", ".m4v"}

# Intent search synonyms for Chinese terms.
QUERY_SYNONYMS = {
    "丝袜": {"黑丝", "白丝", "丝"},
    "黑丝": {"丝袜", "丝"},
    "白丝": {"丝袜", "丝"},
    "丝": {"丝袜", "黑丝", "白丝"},
}

app = Flask(__name__, template_folder="templates", static_folder="static")

LOG = logging.getLogger("video_manager")


def setup_logging() -> None:
    log_file = APP_DIR / "local-video-manager.log"
    if LOG.handlers:
        return
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setFormatter(fmt)
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    LOG.setLevel(logging.INFO)
    LOG.addHandler(fh)
    LOG.addHandler(sh)
    LOG.propagate = False


setup_logging()

# Windows 上常见安装位置；PATH 未配置时仍可自动找到 ffmpeg/ffprobe
_FFMPEG_RESOLVED: Optional[str] = None
_FFPROBE_RESOLVED: Optional[str] = None

MISSING_FFMPEG_HINT = (
    "未找到 ffmpeg。请安装并加入 PATH："
    "在 PowerShell 执行 winget install --id Gyan.FFmpeg -e "
    "或从 https://www.gyan.dev/ffmpeg/builds/ 下载解压，将 bin 目录加入系统「环境变量」PATH，"
    "然后重启本程序。也可设置环境变量 FFMPEG_PATH / FFPROBE_PATH 指向完整 exe 路径。"
)


def _find_media_tool(name: str) -> Optional[str]:
    """解析 ffmpeg 或 ffprobe 可执行文件路径（优先 PATH，其次常见目录与环境变量）。"""
    is_win = sys.platform == "win32"
    exe_name = f"{name}.exe" if is_win else name
    if name == "ffmpeg":
        for k in ("FFMPEG_PATH", "FFMPEG_BINARY"):
            v = os.environ.get(k)
            if v and Path(v).is_file():
                return str(Path(v).resolve())
    else:
        for k in ("FFPROBE_PATH", "FFPROBE_BINARY"):
            v = os.environ.get(k)
            if v and Path(v).is_file():
                return str(Path(v).resolve())

    w = shutil.which(name)
    if w:
        return str(Path(w).resolve())

    if not is_win:
        return None

    dirs: List[Path] = [
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "ffmpeg" / "bin",
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "ffmpeg" / "bin",
        Path(r"C:\ffmpeg\bin"),
        Path.home() / "ffmpeg" / "bin",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Packages",
    ]
    choco = os.environ.get("ChocolateyInstall")
    if choco:
        dirs.append(Path(choco) / "bin")
    scoop = Path.home() / "scoop" / "shims"
    dirs.append(scoop)

    for d in dirs:
        if not d or not d.is_dir():
            continue
        candidate = d / exe_name
        if candidate.is_file():
            return str(candidate.resolve())
        # WinGet 包目录常为嵌套文件夹，浅层搜索一层
        if d.name == "Packages" and "WinGet" in str(d):
            try:
                for sub in d.iterdir():
                    if not sub.is_dir() or "ffmpeg" not in sub.name.lower():
                        continue
                    nested = sub / "ffmpeg" / "bin" / exe_name
                    if nested.is_file():
                        return str(nested.resolve())
                    for child in sub.glob("**/bin/" + exe_name):
                        if child.is_file():
                            return str(child.resolve())
            except OSError:
                continue
    return None


def get_ffmpeg_path() -> Optional[str]:
    global _FFMPEG_RESOLVED
    if _FFMPEG_RESOLVED is None:
        _FFMPEG_RESOLVED = _find_media_tool("ffmpeg")
        if _FFMPEG_RESOLVED:
            LOG.info("已解析 ffmpeg: %s", _FFMPEG_RESOLVED)
        else:
            LOG.warning("未找到 ffmpeg: %s", MISSING_FFMPEG_HINT)
    return _FFMPEG_RESOLVED


def get_ffprobe_path() -> Optional[str]:
    global _FFPROBE_RESOLVED
    if _FFPROBE_RESOLVED is None:
        p = _find_media_tool("ffprobe")
        if not p:
            # 与 ffmpeg 同目录（官方 zip / 多数安装包布局）
            ff = get_ffmpeg_path()
            if ff:
                sibling = Path(ff).parent / ("ffprobe.exe" if sys.platform == "win32" else "ffprobe")
                if sibling.is_file():
                    p = str(sibling.resolve())
        _FFPROBE_RESOLVED = p
        if _FFPROBE_RESOLVED:
            LOG.info("已解析 ffprobe: %s", _FFPROBE_RESOLVED)
        else:
            LOG.warning("未找到 ffprobe，时长探测可能为 0")
    return _FFPROBE_RESOLVED


def _default_config() -> Dict:
    return {
        "data_dir": str((APP_DIR / "data").resolve()),
        "library_dirs": [],
        "llm": {
            "base_url": "https://api.openai.com/v1",
            "api_key": "",
            "model": "gpt-4o-mini",
            "max_candidates": 120,
            "enabled": False,
        },
        "stats": {
            "performance_sampling_enabled": False,
            "sample_size": 30,
        },
        "player": {
            "external_path": "",
        },
        "intent": {
            "enabled": False,
            "model": "BAAI/bge-small-zh-v1.5",
            "lexical_blend": 0.42,
            "min_semantic": 0.18,
            "query_prefix": "",
        },
    }


def load_config() -> Dict:
    defaults = _default_config()
    if not CONFIG_PATH.exists():
        cfg = defaults
        save_config(cfg)
        return cfg
    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        cfg = json.load(f)
    if "data_dir" not in cfg:
        cfg["data_dir"] = defaults["data_dir"]
    if "library_dirs" not in cfg:
        cfg["library_dirs"] = defaults["library_dirs"]
    llm = cfg.get("llm") or {}
    for k, v in defaults["llm"].items():
        llm.setdefault(k, v)
    cfg["llm"] = llm
    st = cfg.get("stats") or {}
    for k, v in defaults["stats"].items():
        st.setdefault(k, v)
    cfg["stats"] = st
    pl = cfg.get("player") or {}
    for k, v in defaults["player"].items():
        pl.setdefault(k, v)
    cfg["player"] = pl
    intent = cfg.get("intent") or {}
    for k, v in defaults["intent"].items():
        intent.setdefault(k, v)
    cfg["intent"] = intent
    return cfg


def save_config(cfg: Dict) -> None:
    with CONFIG_PATH.open("w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


def ensure_data_dirs(data_dir: Path) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "covers").mkdir(parents=True, exist_ok=True)


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


def reveal_path_in_os(file_path: str) -> Tuple[bool, str]:
    """在系统文件管理器中定位到文件（若存在）。"""
    p = Path(file_path)
    if not p.exists():
        return False, "路径不存在"
    try:
        if sys.platform == "win32":
            subprocess.run(["explorer", f"/select,{p.resolve()}"], check=False)
        elif sys.platform == "darwin":
            subprocess.run(["open", "-R", str(p.resolve())], check=False)
        else:
            subprocess.run(["xdg-open", str(p.parent)], check=False)
        return True, ""
    except Exception as e:
        return False, str(e)


def launch_external_player(exe: str, video_path: Path) -> Tuple[bool, str]:
    if not video_path.is_file():
        return False, "视频文件不存在"
    exe_p = Path(exe)
    if not exe_p.is_file():
        return False, "外部播放器路径无效或文件不存在"
    try:
        args = [str(exe_p.resolve()), str(video_path.resolve())]
        if sys.platform == "win32":
            cf = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(
                subprocess, "CREATE_NEW_PROCESS_GROUP", 0
            )
            subprocess.Popen(args, close_fds=True, creationflags=cf)
        else:
            subprocess.Popen(args, close_fds=True, start_new_session=True)
        return True, ""
    except Exception as e:
        return False, str(e)


def run_cmd(args: List[str]) -> Tuple[int, str, str]:
    try:
        p = subprocess.run(args, capture_output=True, text=True, check=False)
        return p.returncode, p.stdout, p.stderr
    except FileNotFoundError:
        return 127, "", f"missing executable: {args[0]}"


def ffprobe_duration(file_path: Path) -> float:
    probe = get_ffprobe_path()
    if not probe:
        return 0
    code, out, _ = run_cmd(
        [
            probe,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(file_path),
        ]
    )
    if code != 0:
        return 0
    try:
        return round(float(out.strip()), 2)
    except ValueError:
        return 0


def generate_default_cover(video_path: Path, duration: float, cover_output: Path) -> Tuple[bool, str]:
    """生成默认封面。成功返回 (True, '')，失败返回 (False, 错误信息)。"""
    ffmpeg = get_ffmpeg_path()
    if not ffmpeg:
        return False, MISSING_FFMPEG_HINT
    # 时长 >= 10s：沿用「最后 60 秒内的第一帧」
    # 时长 < 10s：改为「最后一帧」（从文件末尾向前 seek 再取一帧）
    if duration > 0 and duration < 10:
        code, _, err = run_cmd(
            [
                ffmpeg,
                "-y",
                "-sseof",
                "-0.05",
                "-i",
                str(video_path),
                "-frames:v",
                "1",
                str(cover_output),
            ]
        )
    else:
        ts = max(duration - 60, 0) if duration > 0 else 0
        code, _, err = run_cmd(
            [
                ffmpeg,
                "-y",
                "-ss",
                str(ts),
                "-i",
                str(video_path),
                "-frames:v",
                "1",
                str(cover_output),
            ]
        )
    if code == 0 and cover_output.exists():
        return True, ""
    err_text = (err or "").strip()[:800]
    if not err_text:
        err_text = f"ffmpeg 退出码 {code}"
    return False, err_text


def _cover_name_for_path(resolved_path: str) -> str:
    return f"{hashlib.md5(resolved_path.encode('utf-8')).hexdigest()}.jpg"


def refresh_cover_for_row(
    conn: sqlite3.Connection,
    row: sqlite3.Row,
    cover_dir: Path,
) -> Tuple[bool, str]:
    """根据规则生成默认封面并写入数据库。扫描流程不再生成封面，请单独调用刷新。"""
    vid = row["id"]
    p = row["path"]
    video_path = Path(p)
    if not video_path.is_file():
        return False, "视频文件不存在"
    duration = ffprobe_duration(video_path)
    cover_name = _cover_name_for_path(str(video_path.resolve()))
    cover_path = cover_dir / cover_name
    old_name = row["cover_file"]
    ok, err = generate_default_cover(video_path, duration, cover_path)
    if not ok:
        return False, err or "ffmpeg 失败"
    conn.execute("UPDATE videos SET cover_file=? WHERE id=?", (cover_name, vid))
    if old_name and old_name != cover_name:
        old_path = cover_dir / old_name
        try:
            if old_path.is_file() and old_path.resolve() != cover_path.resolve():
                old_path.unlink()
        except OSError:
            pass
    return True, ""


def make_search_text(filename: str, tags: List[str]) -> str:
    return f"{filename.lower()} {' '.join(t.lower() for t in tags)}"


def _read_tags_llm_readme() -> str:
    p = APP_DIR / "docs" / "TAGS_LLM_README.md"
    if p.is_file():
        return p.read_text(encoding="utf-8")
    return "# 未找到 docs/TAGS_LLM_README.md\n"


def _normalize_import_tag_list(raw) -> List[str]:
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


def _tags_list_equal(a: List[str], b: List[str]) -> bool:
    return sorted(a) == sorted(b)


def _video_tag_names(conn: sqlite3.Connection, video_id: int) -> List[str]:
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


def _read_tags_import_request_body() -> Tuple[Optional[str], bytes]:
    raw_bytes: Optional[bytes] = None
    if request.files and request.files.get("file"):
        raw_bytes = request.files["file"].read()
    elif request.data:
        raw_bytes = request.data
    if not raw_bytes:
        return "empty body: use multipart file or raw JSONL", b""
    return None, raw_bytes


def _decode_tags_import_text(raw_bytes: bytes) -> Tuple[Optional[str], str]:
    try:
        return None, raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        return "decode error: need UTF-8", ""


def _preview_tags_import(text: str, strict_path: bool) -> Dict:
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
            new_tags = _normalize_import_tag_list(obj.get("t"))
            old_tags = _video_tag_names(conn, vid)
            if _tags_list_equal(old_tags, new_tags):
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


def _set_video_tags_replace(conn: sqlite3.Connection, video_id: int, tag_names: List[str]) -> None:
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


def _safe_json_loads_from_text(s: str) -> Optional[Dict]:
    s = (s or "").strip()
    if not s:
        return None
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass

    start = s.find("{")
    end = s.rfind("}")
    if start >= 0 and end > start:
        part = s[start : end + 1]
        try:
            return json.loads(part)
        except json.JSONDecodeError:
            return None
    return None


def _openai_compatible_chat(messages: List[Dict], cfg: Dict) -> Tuple[bool, Dict]:
    base_url = (cfg.get("base_url") or "").strip().rstrip("/")
    api_key = (cfg.get("api_key") or "").strip()
    model = (cfg.get("model") or "").strip()
    if not base_url or not model:
        return False, {"error": "llm config missing base_url/model"}
    if not api_key:
        return False, {"error": "llm config missing api_key"}

    payload = {
        "model": model,
        "temperature": 0.1,
        "messages": messages,
        "response_format": {"type": "json_object"},
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = url_request.Request(
        f"{base_url}/chat/completions",
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )
    try:
        with url_request.urlopen(req, timeout=35) as resp:
            raw = resp.read().decode("utf-8")
    except url_error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="ignore")
        return False, {"error": f"http {e.code}: {detail}"}
    except Exception as e:
        return False, {"error": str(e)}

    parsed = _safe_json_loads_from_text(raw) or {}
    choices = parsed.get("choices") or []
    if not choices:
        return False, {"error": "llm response has no choices"}
    content = (((choices[0] or {}).get("message") or {}).get("content") or "").strip()
    obj = _safe_json_loads_from_text(content)
    if not obj:
        return False, {"error": "cannot parse llm json content", "raw_content": content}
    return True, obj


def build_ai_candidates(videos: List[Dict], max_candidates: int) -> List[Dict]:
    # Prefer high-signal candidates to reduce prompt length and improve relevance.
    ordered = sorted(
        videos,
        key=lambda v: (v.get("watch_count", 0), v.get("modified_at", 0)),
        reverse=True,
    )
    selected = ordered[: max(max_candidates, 20)]
    return [
        {
            "id": v["id"],
            "filename": v["filename"],
            "tags": v.get("tags", []),
            "duration_sec": v.get("duration_sec", 0),
            "watch_count": v.get("watch_count", 0),
            "path": v.get("path", ""),
        }
        for v in selected
    ]


def local_fallback_ai_search(
    question: str,
    videos: List[Dict],
    top_k: int,
    *,
    intent_cfg: Optional[Dict] = None,
    all_tag_names: Optional[List[str]] = None,
) -> Dict:
    icfg = intent_cfg or {}
    if (
        icfg.get("enabled")
        and all_tag_names is not None
        and is_fastembed_available()
    ):
        try:
            ranked = apply_intent_hybrid_search(
                videos,
                question,
                icfg,
                all_tag_names,
                expand_query_terms,
                calc_intent_score,
            )
            if ranked:
                return {
                    "matched_ids": [v["id"] for v in ranked[:top_k]],
                    "reason": "本地标签语义（fastembed）与字符意图混合排序",
                }
        except Exception as e:
            LOG.warning("本地语义检索失败，回退字符意图: %s", e)
    ranked_lex = filter_videos_lexical_search(
        videos, question, include_path=True
    )
    return {
        "matched_ids": [v["id"] for v in ranked_lex[:top_k]],
        "reason": "使用本地意图匹配作为回退结果（未调用模型或模型不可用）",
    }


def list_video_rows(
    conn: sqlite3.Connection,
    tag_filter: Optional[str],
    *,
    recycled_only: bool = False,
) -> List[sqlite3.Row]:
    conditions: List[str] = []
    params: List = []
    if recycled_only:
        conditions.append("v.recycled_at IS NOT NULL")
    else:
        conditions.append("v.recycled_at IS NULL")
    if tag_filter:
        conditions.append(
            "v.id IN (SELECT vt.video_id FROM video_tags vt JOIN tags t ON t.id = vt.tag_id WHERE t.name = ?)"
        )
        params.append(tag_filter)
    where_clause = "WHERE " + " AND ".join(conditions)

    sql = f"""
        SELECT
            v.*,
            GROUP_CONCAT(t.name, '|') AS tag_names
        FROM videos v
        LEFT JOIN video_tags vt ON vt.video_id = v.id
        LEFT JOIN tags t ON t.id = vt.tag_id
        {where_clause}
        GROUP BY v.id
    """
    return conn.execute(sql, params).fetchall()


def serialize_video_row(row: sqlite3.Row) -> Dict:
    tags = row["tag_names"].split("|") if row["tag_names"] else []
    keys = row.keys()
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
        "recycled": recycled_at is not None,
        "recycled_at": recycled_at,
    }


def _db_usage_stats(conn: sqlite3.Connection) -> Dict:
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


def _disk_usage_stats(data_dir: Path) -> Dict:
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


def _system_snapshot() -> Dict:
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


def _sample_disk_io(sample_size: int) -> Dict:
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


@app.route("/")
def index():
    LOG.info("页面访问 GET /")
    return render_template("index.html")


@app.route("/api/config", methods=["GET", "POST"])
def api_config():
    if request.method == "GET":
        LOG.info("读取配置 GET /api/config")
        return jsonify(load_config())

    payload = request.get_json(force=True) or {}
    cfg = load_config()
    data_dir = payload.get("data_dir")
    library_dirs = payload.get("library_dirs")
    llm_cfg = payload.get("llm")
    if data_dir:
        cfg["data_dir"] = str(Path(data_dir).expanduser().resolve())
    if isinstance(library_dirs, list):
        cleaned = []
        for p in library_dirs:
            try:
                rp = str(Path(p).expanduser().resolve())
                cleaned.append(rp)
            except Exception:
                continue
        cfg["library_dirs"] = cleaned
    if isinstance(llm_cfg, dict):
        target = cfg.get("llm") or {}
        target["base_url"] = str(llm_cfg.get("base_url") or target.get("base_url") or "").strip()
        target["api_key"] = str(llm_cfg.get("api_key") or "").strip()
        target["model"] = str(llm_cfg.get("model") or target.get("model") or "").strip()
        try:
            target["max_candidates"] = int(llm_cfg.get("max_candidates") or target.get("max_candidates") or 120)
        except Exception:
            target["max_candidates"] = 120
        target["enabled"] = bool(llm_cfg.get("enabled"))
        cfg["llm"] = target
    stats_cfg = payload.get("stats")
    if isinstance(stats_cfg, dict):
        st = cfg.get("stats") or {}
        if "performance_sampling_enabled" in stats_cfg:
            st["performance_sampling_enabled"] = bool(stats_cfg["performance_sampling_enabled"])
        if "sample_size" in stats_cfg:
            try:
                st["sample_size"] = max(10, min(100, int(stats_cfg["sample_size"])))
            except (TypeError, ValueError):
                pass
        cfg["stats"] = st
    player_cfg = payload.get("player")
    if isinstance(player_cfg, dict):
        pl = cfg.get("player") or {}
        if "external_path" in player_cfg:
            pl["external_path"] = str(player_cfg.get("external_path") or "").strip()
        cfg["player"] = pl
    intent_cfg = payload.get("intent")
    if isinstance(intent_cfg, dict):
        inc = cfg.get("intent") or {}
        if "enabled" in intent_cfg:
            inc["enabled"] = bool(intent_cfg["enabled"])
        if "model" in intent_cfg:
            inc["model"] = str(intent_cfg.get("model") or "").strip()
        if "lexical_blend" in intent_cfg:
            try:
                inc["lexical_blend"] = max(
                    0.0, min(1.0, float(intent_cfg.get("lexical_blend")))
                )
            except (TypeError, ValueError):
                pass
        if "min_semantic" in intent_cfg:
            try:
                inc["min_semantic"] = max(
                    0.0, min(1.0, float(intent_cfg.get("min_semantic")))
                )
            except (TypeError, ValueError):
                pass
        if "query_prefix" in intent_cfg:
            inc["query_prefix"] = str(intent_cfg.get("query_prefix") or "")
        cfg["intent"] = inc
        clear_tag_vector_cache()
    save_config(cfg)
    ensure_data_dirs(Path(cfg["data_dir"]))
    safe = dict(cfg)
    if isinstance(safe.get("llm"), dict) and safe["llm"].get("api_key"):
        safe["llm"] = dict(safe["llm"])
        safe["llm"]["api_key"] = "***"
    LOG.info("保存配置 POST /api/config data_dir=%s library_dirs=%s", safe.get("data_dir"), safe.get("library_dirs"))
    return jsonify({"ok": True, "config": cfg})


@app.route("/api/intent/status", methods=["GET"])
def api_intent_status():
    """fastembed 是否可用；可选 ?probe=1 试加载模型（会下载）。"""
    cfg = load_config()
    icfg = cfg.get("intent") or {}
    model = (icfg.get("model") or "BAAI/bge-small-zh-v1.5").strip()
    installed = is_fastembed_available()
    out: Dict = {
        "ok": True,
        "fastembed_installed": installed,
        "model": model,
        "probe": None,
    }
    if request.args.get("probe") == "1" and installed:
        out["probe"] = probe_intent_model(model)
    elif not installed:
        out["hint"] = "请安装: pip install fastembed（约百余 MB 模型首次使用时下载）"
    return jsonify(out)


@app.route("/api/scan", methods=["POST"])
def api_scan():
    """仅扫描并更新元数据，不生成封面。封面请使用「刷新封面」接口。"""
    cfg = load_config()
    library_dirs = [Path(d) for d in cfg.get("library_dirs", [])]
    data_dir = Path(cfg["data_dir"]).resolve()
    ensure_data_dirs(data_dir)

    LOG.info("开始扫描视频 library_dirs=%s", [str(x) for x in library_dirs])
    conn = get_conn()
    now = int(time.time())
    created = 0
    updated = 0
    skipped = 0

    for root in library_dirs:
        if not root.exists():
            LOG.warning("扫描路径不存在，已跳过: %s", root)
            continue
        for f in root.rglob("*"):
            if not f.is_file() or f.suffix.lower() not in VIDEO_EXTENSIONS:
                continue
            try:
                stat = f.stat()
            except OSError:
                skipped += 1
                continue
            p = str(f.resolve())
            filename = f.name
            modified = int(stat.st_mtime)
            created_at = int(stat.st_ctime)
            size_bytes = int(stat.st_size)

            row = conn.execute("SELECT id FROM videos WHERE path = ?", (p,)).fetchone()
            duration = ffprobe_duration(f)
            if row:
                conn.execute(
                    """
                    UPDATE videos
                    SET filename=?, size_bytes=?, duration_sec=?, modified_at=?, created_at=?, indexed_at=?, search_text=?,
                        recycled_at=NULL
                    WHERE id=?
                    """,
                    (
                        filename,
                        size_bytes,
                        duration,
                        modified,
                        created_at,
                        now,
                        filename.lower(),
                        row["id"],
                    ),
                )
                updated += 1
            else:
                conn.execute(
                    """
                    INSERT INTO videos(path, filename, size_bytes, duration_sec, modified_at, created_at, indexed_at, search_text)
                    VALUES(?,?,?,?,?,?,?,?)
                    """,
                    (p, filename, size_bytes, duration, modified, created_at, now, filename.lower()),
                )
                created += 1

    moved_invalid = 0
    stale = conn.execute(
        "SELECT id, path FROM videos WHERE recycled_at IS NULL"
    ).fetchall()
    for r in stale:
        if not Path(r["path"]).is_file():
            conn.execute(
                "UPDATE videos SET recycled_at = ? WHERE id = ?",
                (now, r["id"]),
            )
            moved_invalid += 1
            LOG.info("扫描：路径无效，已移入回收站 id=%s path=%s", r["id"], r["path"][:120])

    conn.commit()
    conn.close()
    LOG.info(
        "扫描结束 created=%s updated=%s skipped=%s invalid_to_recycle=%s（封面请单独点击刷新）",
        created,
        updated,
        skipped,
        moved_invalid,
    )
    return jsonify(
        {
            "ok": True,
            "created": created,
            "updated": updated,
            "skipped": skipped,
            "moved_invalid_to_recycle": moved_invalid,
        }
    )


@app.route("/api/covers/refresh", methods=["POST"])
def api_covers_refresh():
    payload = request.get_json(force=True) or {}
    only_missing = bool(payload.get("only_missing", True))
    cfg = load_config()
    data_dir = Path(cfg["data_dir"]).resolve()
    cover_dir = data_dir / "covers"
    ensure_data_dirs(data_dir)

    conn = get_conn()
    if only_missing:
        rows = conn.execute(
            """
            SELECT * FROM videos
            WHERE recycled_at IS NULL
              AND (cover_file IS NULL OR cover_file = '')
            """
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM videos WHERE recycled_at IS NULL").fetchall()
    LOG.info(
        "批量刷新封面开始 only_missing=%s total=%s",
        only_missing,
        len(rows),
    )
    ok_count = 0
    fail_count = 0
    first_errors: List[str] = []
    for row in rows:
        ok, msg = refresh_cover_for_row(conn, row, cover_dir)
        if ok:
            ok_count += 1
        else:
            fail_count += 1
            if len(first_errors) < 5:
                first_errors.append(f"id={row['id']} {msg}")
            LOG.warning("封面失败 id=%s filename=%s %s", row["id"], row["filename"], msg)
    conn.commit()
    conn.close()
    LOG.info("批量刷新封面结束 success=%s failed=%s", ok_count, fail_count)
    return jsonify(
        {
            "ok": True,
            "only_missing": only_missing,
            "success": ok_count,
            "failed": fail_count,
            "sample_errors": first_errors,
        }
    )


@app.route("/api/videos/<int:video_id>/cover/refresh", methods=["POST"])
def api_video_cover_refresh(video_id: int):
    cfg = load_config()
    data_dir = Path(cfg["data_dir"]).resolve()
    cover_dir = data_dir / "covers"
    ensure_data_dirs(data_dir)

    conn = get_conn()
    row = conn.execute("SELECT * FROM videos WHERE id = ?", (video_id,)).fetchone()
    if not row:
        conn.close()
        LOG.warning("刷新封面：视频不存在 video_id=%s", video_id)
        return jsonify({"ok": False, "error": "not found"}), 404
    ok, msg = refresh_cover_for_row(conn, row, cover_dir)
    conn.commit()
    cover_url = ""
    if ok:
        row2 = conn.execute("SELECT cover_file FROM videos WHERE id=?", (video_id,)).fetchone()
        if row2 and row2["cover_file"]:
            cover_url = f"/api/covers/{row2['cover_file']}"
    conn.close()
    if ok:
        LOG.info("单条刷新封面成功 video_id=%s filename=%s", video_id, row["filename"])
        return jsonify({"ok": True, "cover_url": cover_url})
    LOG.warning("单条刷新封面失败 video_id=%s %s", video_id, msg)
    return jsonify({"ok": False, "error": msg}), 500


@app.route("/api/videos", methods=["GET"])
def api_videos():
    search = (request.args.get("search") or "").strip()
    tag_filter = (request.args.get("tag") or "").strip()
    sort = (request.args.get("sort") or "modified_at").strip()
    order = (request.args.get("order") or "desc").strip().lower()
    order = "desc" if order not in ("asc", "desc") else order
    try:
        page = int(request.args.get("page") or 1)
    except (TypeError, ValueError):
        page = 1
    try:
        per_page = int(request.args.get("per_page") or 24)
    except (TypeError, ValueError):
        per_page = 24
    page = max(1, page)
    per_page = max(6, min(per_page, 200))

    recycled_only = request.args.get("recycled", "0").lower() in ("1", "true", "yes")
    cfg = load_config()
    icfg = cfg.get("intent") or {}

    LOG.info(
        "列表查询 search=%r tag=%r sort=%s order=%s page=%s per_page=%s recycled=%s intent=%s",
        search[:80] if search else "",
        tag_filter,
        sort,
        order,
        page,
        per_page,
        recycled_only,
        icfg.get("enabled") and is_fastembed_available(),
    )

    conn = get_conn()
    all_tag_rows = conn.execute("SELECT name FROM tags ORDER BY name").fetchall()
    all_tag_names = [r[0] for r in all_tag_rows]
    rows = list_video_rows(conn, tag_filter or None, recycled_only=recycled_only)
    videos = [serialize_video_row(r) for r in rows]

    if search:
        if icfg.get("enabled") and is_fastembed_available():
            try:
                ranked = apply_intent_hybrid_search(
                    videos,
                    search,
                    icfg,
                    all_tag_names,
                    expand_query_terms,
                    calc_intent_score,
                )
                if ranked:
                    videos = ranked
                else:
                    videos = filter_videos_lexical_search(videos, search)
            except Exception as e:
                LOG.warning("标签语义检索失败，回退字符意图: %s", e)
                videos = filter_videos_lexical_search(videos, search)
        else:
            videos = filter_videos_lexical_search(videos, search)

    def sort_key(v: Dict):
        if sort == "filename":
            return v["filename"].lower()
        if sort == "watch_count":
            return v["watch_count"]
        if sort == "duration_sec":
            return v["duration_sec"]
        if sort == "size_bytes":
            return v["size_bytes"]
        if sort == "hot":
            age_days = max((time.time() - v["created_at"]) / 86400, 1)
            return round(v["watch_count"] / age_days, 6)
        return v.get("modified_at", 0)

    reverse = order == "desc"
    videos.sort(key=sort_key, reverse=reverse)

    total = len(videos)
    total_pages = max(1, math.ceil(total / per_page)) if total else 1
    if page > total_pages:
        page = total_pages
    start = (page - 1) * per_page
    page_videos = videos[start : start + per_page]

    tags = conn.execute("SELECT id, name, is_auto FROM tags ORDER BY is_auto DESC, name ASC").fetchall()
    conn.close()
    return jsonify(
        {
            "videos": page_videos,
            "tags": [{"id": t["id"], "name": t["name"], "is_auto": bool(t["is_auto"])} for t in tags],
            "total": total,
            "page": page,
            "per_page": per_page,
            "total_pages": total_pages,
            "recycled_view": recycled_only,
        }
    )


@app.route("/api/ai/search", methods=["POST"])
def api_ai_search():
    payload = request.get_json(force=True) or {}
    question = (payload.get("question") or "").strip()
    top_k = int(payload.get("top_k") or 30)
    if not question:
        return jsonify({"ok": False, "error": "question is empty"}), 400
    top_k = max(1, min(top_k, 100))
    LOG.info("AI搜索 question=%r top_k=%s", question[:200], top_k)

    cfg = load_config()
    llm_cfg = cfg.get("llm") or {}
    intent_cfg = cfg.get("intent") or {}
    conn = get_conn()
    all_tag_rows = conn.execute("SELECT name FROM tags ORDER BY name").fetchall()
    all_tag_names = [r[0] for r in all_tag_rows]
    rows = list_video_rows(conn, None)
    conn.close()
    videos = [serialize_video_row(r) for r in rows]
    by_id = {v["id"]: v for v in videos}

    source = "fallback"
    reason = ""
    matched_ids: List[int] = []

    if llm_cfg.get("enabled"):
        candidates = build_ai_candidates(videos, int(llm_cfg.get("max_candidates") or 120))
        sys_prompt = (
            "你是本地视频库检索助手。请根据用户问题，在候选视频中选出最相关的视频ID。"
            "输出严格 JSON 对象，格式为："
            '{"matched_ids":[int...],"reason":"简短中文解释","keywords":["词1","词2"]}。'
            "不要输出 markdown。"
        )
        user_prompt = (
            f"用户问题：{question}\n"
            f"候选视频列表（JSON）：{json.dumps(candidates, ensure_ascii=False)}\n"
            f"返回最多 {top_k} 个结果。"
        )
        ok, llm_ret = _openai_compatible_chat(
            [{"role": "system", "content": sys_prompt}, {"role": "user", "content": user_prompt}],
            llm_cfg,
        )
        if ok:
            for x in llm_ret.get("matched_ids") or []:
                try:
                    vid = int(x)
                except Exception:
                    continue
                if vid in by_id and vid not in matched_ids:
                    matched_ids.append(vid)
                if len(matched_ids) >= top_k:
                    break
            source = "llm"
            reason = str(llm_ret.get("reason") or "由模型按语义与标签综合排序")
        else:
            fb = local_fallback_ai_search(
                question,
                videos,
                top_k,
                intent_cfg=intent_cfg,
                all_tag_names=all_tag_names,
            )
            matched_ids = fb["matched_ids"]
            reason = f"模型调用失败，已回退本地搜索：{llm_ret.get('error', '')}"
    else:
        fb = local_fallback_ai_search(
            question,
            videos,
            top_k,
            intent_cfg=intent_cfg,
            all_tag_names=all_tag_names,
        )
        matched_ids = fb["matched_ids"]
        reason = fb["reason"]

    result_videos = [by_id[i] for i in matched_ids if i in by_id]
    LOG.info("AI搜索完成 source=%s 返回条数=%s", source, len(result_videos))
    return jsonify(
        {
            "ok": True,
            "source": source,
            "reason": reason,
            "question": question,
            "videos": result_videos,
        }
    )


@app.route("/api/ai/export")
def api_ai_export():
    fmt = (request.args.get("format") or "json").strip().lower()
    LOG.info("导出AI数据 format=%s", fmt)
    conn = get_conn()
    rows = list_video_rows(conn, None)
    conn.close()
    videos = [serialize_video_row(r) for r in rows]
    docs = []
    for v in videos:
        docs.append(
            {
                "id": v["id"],
                "filename": v["filename"],
                "path": v["path"],
                "tags": v["tags"],
                "watch_count": v["watch_count"],
                "duration_sec": v["duration_sec"],
                "modified_at": v["modified_at"],
                "text": f"{v['filename']} 标签: {' '.join(v['tags'])}",
            }
        )
    if fmt == "jsonl":
        lines = [json.dumps(d, ensure_ascii=False) for d in docs]
        return (
            "\n".join(lines),
            200,
            {
                "Content-Type": "application/json; charset=utf-8",
                "Content-Disposition": "attachment; filename=video_library.jsonl",
            },
        )
    return jsonify({"ok": True, "count": len(docs), "items": docs})


@app.route("/api/videos/<int:video_id>/play", methods=["POST"])
def api_play(video_id: int):
    LOG.info("播放计数 video_id=%s", video_id)
    conn = get_conn()
    conn.execute("UPDATE videos SET watch_count = watch_count + 1 WHERE id = ?", (video_id,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.route("/api/videos/<int:video_id>/recycle", methods=["POST"])
def api_video_recycle(video_id: int):
    now = int(time.time())
    conn = get_conn()
    cur = conn.execute(
        "UPDATE videos SET recycled_at = ? WHERE id = ? AND recycled_at IS NULL",
        (now, video_id),
    )
    conn.commit()
    n = cur.rowcount
    conn.close()
    if n == 0:
        return jsonify({"ok": False, "error": "not found or already in recycle"}), 400
    LOG.info("移入回收站 video_id=%s", video_id)
    return jsonify({"ok": True})


@app.route("/api/videos/<int:video_id>/restore", methods=["POST"])
def api_video_restore(video_id: int):
    conn = get_conn()
    cur = conn.execute(
        "UPDATE videos SET recycled_at = NULL WHERE id = ? AND recycled_at IS NOT NULL",
        (video_id,),
    )
    conn.commit()
    n = cur.rowcount
    conn.close()
    if n == 0:
        return jsonify({"ok": False, "error": "not found or not in recycle"}), 400
    LOG.info("从回收站恢复 video_id=%s", video_id)
    return jsonify({"ok": True})


@app.route("/api/videos/<int:video_id>/open-external", methods=["POST"])
def api_video_open_external(video_id: int):
    cfg = load_config()
    exe = (cfg.get("player") or {}).get("external_path") or ""
    exe = str(exe).strip()
    if not exe:
        return jsonify({"ok": False, "error": "未配置外部播放器路径"}), 400
    conn = get_conn()
    row = conn.execute("SELECT path FROM videos WHERE id = ?", (video_id,)).fetchone()
    conn.close()
    if not row:
        return jsonify({"ok": False, "error": "not found"}), 404
    ok, err = launch_external_player(exe, Path(row["path"]))
    if not ok:
        return jsonify({"ok": False, "error": err}), 400
    LOG.info("外部播放器打开 video_id=%s", video_id)
    return jsonify({"ok": True})


@app.route("/api/videos/<int:video_id>/reveal", methods=["POST"])
def api_video_reveal(video_id: int):
    conn = get_conn()
    row = conn.execute("SELECT path FROM videos WHERE id = ?", (video_id,)).fetchone()
    conn.close()
    if not row:
        return jsonify({"ok": False, "error": "not found"}), 404
    ok, err = reveal_path_in_os(row["path"])
    if not ok:
        return jsonify({"ok": False, "error": err}), 400
    LOG.info("打开文件位置 video_id=%s", video_id)
    return jsonify({"ok": True})


@app.route("/api/recycle/purge", methods=["POST"])
def api_recycle_purge():
    """删除回收站内记录对应的磁盘视频文件与封面，并移除数据库行。"""
    cfg = load_config()
    data_dir = Path(cfg["data_dir"]).resolve()
    cover_dir = data_dir / "covers"
    ensure_data_dirs(data_dir)

    conn = get_conn()
    rows = conn.execute(
        "SELECT id, path, cover_file FROM videos WHERE recycled_at IS NOT NULL"
    ).fetchall()
    files_deleted = 0
    rows_removed = 0
    errors: List[str] = []
    for r in rows:
        vid = r["id"]
        p = Path(r["path"])
        if p.is_file():
            try:
                p.unlink()
                files_deleted += 1
            except OSError as e:
                errors.append(f"id={vid} 删除文件: {e}")
        cf = r["cover_file"]
        if cf:
            cp = cover_dir / cf
            if cp.is_file():
                try:
                    cp.unlink()
                except OSError as e:
                    errors.append(f"id={vid} 删除封面: {e}")
        conn.execute("DELETE FROM videos WHERE id = ?", (vid,))
        rows_removed += 1
    conn.commit()
    conn.close()
    LOG.info(
        "清空回收站 files_deleted=%s rows_removed=%s errors=%s",
        files_deleted,
        rows_removed,
        len(errors),
    )
    return jsonify(
        {
            "ok": True,
            "files_deleted": files_deleted,
            "rows_removed": rows_removed,
            "errors": errors,
        }
    )


@app.route("/api/videos/<int:video_id>/tags", methods=["POST"])
def api_add_tag(video_id: int):
    payload = request.get_json(force=True) or {}
    name = (payload.get("tag") or "").strip()
    if not name:
        return jsonify({"ok": False, "error": "tag is empty"}), 400
    LOG.info("添加标签 video_id=%s tag=%r", video_id, name)

    conn = get_conn()
    now = int(time.time())
    conn.execute(
        "INSERT INTO tags(name, is_auto, created_at) VALUES(?, 0, ?) ON CONFLICT(name) DO NOTHING",
        (name, now),
    )
    tag_row = conn.execute("SELECT id FROM tags WHERE name = ?", (name,)).fetchone()
    conn.execute(
        "INSERT INTO video_tags(video_id, tag_id, source, created_at) VALUES(?,?, 'manual', ?) ON CONFLICT(video_id, tag_id) DO NOTHING",
        (video_id, tag_row["id"], now),
    )
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.route("/api/videos/<int:video_id>/tags/<int:tag_id>", methods=["DELETE"])
def api_delete_tag(video_id: int, tag_id: int):
    LOG.info("删除标签关联 video_id=%s tag_id=%s", video_id, tag_id)
    conn = get_conn()
    conn.execute("DELETE FROM video_tags WHERE video_id = ? AND tag_id = ?", (video_id, tag_id))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.route("/api/tags/auto-generate", methods=["POST"])
def api_auto_generate_tags():
    LOG.info("开始根据文件名自动生成标签")
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, filename FROM videos WHERE recycled_at IS NULL"
    ).fetchall()
    token_count: Dict[str, int] = {}
    for r in rows:
        for t in extract_filename_tokens(r["filename"]):
            token_count[t] = token_count.get(t, 0) + 1

    now = int(time.time())
    candidates = [k for k, v in token_count.items() if v >= 2 and len(k) >= 2]
    candidates = sorted(candidates, key=lambda x: token_count[x], reverse=True)[:200]

    for tag in candidates:
        conn.execute(
            "INSERT INTO tags(name, is_auto, created_at) VALUES(?, 1, ?) ON CONFLICT(name) DO NOTHING",
            (tag, now),
        )

    tag_map = {
        r["name"]: r["id"]
        for r in conn.execute("SELECT id, name FROM tags WHERE is_auto = 1").fetchall()
    }
    attached = 0
    for r in rows:
        text = r["filename"].lower()
        for tag_name, tag_id in tag_map.items():
            if tag_name in text:
                conn.execute(
                    "INSERT INTO video_tags(video_id, tag_id, source, created_at) VALUES(?,?, 'auto', ?) ON CONFLICT(video_id, tag_id) DO NOTHING",
                    (r["id"], tag_id, now),
                )
                attached += 1
    conn.commit()
    conn.close()
    LOG.info("自动标签完成 generated=%s attached=%s", len(candidates), attached)
    return jsonify({"ok": True, "generated_tags": len(candidates), "attached": attached})


@app.route("/api/tags/export", methods=["GET"])
def api_tags_export():
    """导出 JSONL：每行 i/n/p/t，供外部大模型重写标签。"""
    conn = get_conn()
    videos = conn.execute(
        "SELECT id, filename, path FROM videos WHERE recycled_at IS NULL ORDER BY id"
    ).fetchall()
    tag_rows = conn.execute(
        """
        SELECT vt.video_id, t.name
        FROM video_tags vt
        JOIN tags t ON t.id = vt.tag_id
        INNER JOIN videos v ON v.id = vt.video_id AND v.recycled_at IS NULL
        ORDER BY vt.video_id, t.name
        """
    ).fetchall()
    conn.close()
    by_vid: Dict[int, List[str]] = {}
    for r in tag_rows:
        vid = r["video_id"]
        by_vid.setdefault(vid, []).append(r["name"])

    lines: List[str] = []
    for v in videos:
        vid = v["id"]
        obj = {"i": vid, "n": v["filename"], "p": v["path"], "t": by_vid.get(vid, [])}
        lines.append(json.dumps(obj, ensure_ascii=False, separators=(",", ":")))
    body = "\n".join(lines) + ("\n" if lines else "")
    LOG.info("导出标签 JSONL 行数=%s", len(lines))
    return Response(
        body,
        mimetype="application/x-ndjson; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="tags_export.jsonl"'},
    )


@app.route("/api/tags/export-readme", methods=["GET"])
def api_tags_export_readme():
    text = _read_tags_llm_readme()
    return Response(
        text,
        mimetype="text/markdown; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="TAGS_LLM_README.md"'},
    )


@app.route("/api/tags/import-preview", methods=["POST"])
def api_tags_import_preview():
    """
    导入前预览：与 POST /api/tags/import 使用相同正文与 strict_path，不写库。
    """
    strict_path = request.args.get("strict_path", "0").lower() in ("1", "true", "yes")
    err, raw_bytes = _read_tags_import_request_body()
    if err:
        return jsonify({"ok": False, "error": err}), 400
    dec_err, text = _decode_tags_import_text(raw_bytes)
    if dec_err:
        return jsonify({"ok": False, "error": dec_err}), 400
    LOG.info("标签导入预览 strict_path=%s", strict_path)
    return jsonify(_preview_tags_import(text, strict_path))


@app.route("/api/tags/import", methods=["POST"])
def api_tags_import():
    """
    导入大模型处理后的 JSONL。multipart 字段 file，或 raw UTF-8 正文。
    查询参数 strict_path=1：若行内含 p 且与库内 path 不一致则跳过该行。
    """
    strict_path = request.args.get("strict_path", "0").lower() in ("1", "true", "yes")
    err, raw_bytes = _read_tags_import_request_body()
    if err:
        return jsonify({"ok": False, "error": err}), 400
    dec_err, text = _decode_tags_import_text(raw_bytes)
    if dec_err:
        return jsonify({"ok": False, "error": dec_err}), 400

    updated = 0
    skipped_no_video = 0
    skipped_path = 0
    skipped_no_t = 0
    errors: List[Dict] = []

    conn = get_conn()
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
                LOG.warning("导入跳过（无 t） line=%s video_id=%s", line_no, vid)
                continue
            row = conn.execute("SELECT id, path FROM videos WHERE id = ?", (vid,)).fetchone()
            if not row:
                skipped_no_video += 1
                continue
            if strict_path and "p" in obj and obj["p"] is not None:
                p_in = str(obj["p"])
                if p_in and p_in != row["path"]:
                    skipped_path += 1
                    LOG.warning(
                        "导入跳过（路径不一致 strict_path） line=%s id=%s", line_no, vid
                    )
                    continue
            tags = _normalize_import_tag_list(obj.get("t"))
            try:
                _set_video_tags_replace(conn, vid, tags)
                conn.commit()
                updated += 1
            except Exception as e:
                conn.rollback()
                errors.append({"line": line_no, "error": str(e), "i": vid})
                LOG.exception("导入行失败 line=%s id=%s", line_no, vid)
    finally:
        conn.close()

    LOG.info(
        "导入标签完成 updated=%s skipped_no_video=%s skipped_path=%s skipped_no_t=%s errors=%s",
        updated,
        skipped_no_video,
        skipped_path,
        skipped_no_t,
        len(errors),
    )
    return jsonify(
        {
            "ok": True,
            "updated": updated,
            "skipped_no_video": skipped_no_video,
            "skipped_path": skipped_path,
            "skipped_no_t": skipped_no_t,
            "errors": errors,
        }
    )


@app.route("/api/videos/<int:video_id>/cover", methods=["POST"])
def api_upload_cover(video_id: int):
    if "file" not in request.files:
        return jsonify({"ok": False, "error": "missing file"}), 400
    f = request.files["file"]
    if not f.filename:
        return jsonify({"ok": False, "error": "empty filename"}), 400
    LOG.info("上传自定义封面 video_id=%s filename=%r", video_id, f.filename)

    cfg = load_config()
    data_dir = Path(cfg["data_dir"]).resolve()
    cover_dir = data_dir / "covers"
    ensure_data_dirs(data_dir)
    ext = Path(f.filename).suffix.lower() or ".jpg"
    cover_name = f"manual_{video_id}_{int(time.time())}{ext}"
    target = cover_dir / cover_name
    f.save(str(target))

    conn = get_conn()
    conn.execute("UPDATE videos SET cover_file=? WHERE id=?", (cover_name, video_id))
    conn.commit()
    conn.close()
    return jsonify({"ok": True, "cover_url": f"/api/covers/{cover_name}"})


@app.route("/api/covers/<path:name>")
def api_cover(name: str):
    cfg = load_config()
    cover_path = Path(cfg["data_dir"]).resolve() / "covers" / name
    if not cover_path.exists():
        return "", 404
    return send_file(str(cover_path))


@app.route("/api/videos/<int:video_id>/stream")
def api_stream(video_id: int):
    LOG.debug("视频流请求 video_id=%s", video_id)
    conn = get_conn()
    row = conn.execute("SELECT path FROM videos WHERE id = ?", (video_id,)).fetchone()
    conn.close()
    if not row:
        return "", 404
    p = Path(row["path"])
    if not p.exists():
        return "", 404
    return send_file(str(p), conditional=True)


@app.route("/api/stats/summary", methods=["GET"])
def api_stats_summary():
    """轻量汇总：仅 SQLite 聚合 + 磁盘空间 + 封面目录体积，不做抽样 IO。"""
    LOG.info("GET /api/stats/summary")
    conn = get_conn()
    dbu = _db_usage_stats(conn)
    conn.close()
    cfg = load_config()
    data_dir = Path(cfg["data_dir"]).expanduser().resolve()
    ensure_data_dirs(data_dir)
    disk = _disk_usage_stats(data_dir)
    return jsonify({"ok": True, "db": dbu, "disk": disk, "ts": int(time.time())})


@app.route("/api/stats/sample", methods=["POST"])
def api_stats_sample():
    """按需抽样：CPU/内存快照 + 随机视频的 stat / 4KB 读取耗时（仅在用户点击时调用）。"""
    payload = request.get_json(force=True) or {}
    cfg = load_config()
    st = cfg.get("stats") or {}
    try:
        sample_size = int(payload.get("sample_size") or st.get("sample_size") or 30)
    except (TypeError, ValueError):
        sample_size = 30
    sample_size = max(5, min(sample_size, 100))
    LOG.info("POST /api/stats/sample sample_size=%s", sample_size)
    sys_snap = _system_snapshot()
    io_s = _sample_disk_io(sample_size)
    return jsonify(
        {
            "ok": True,
            "system": sys_snap,
            "io_sample": io_s,
            "sample_size": sample_size,
            "ts": int(time.time()),
        }
    )


if __name__ == "__main__":
    # Start with: python app.py
    LOG.info("启动服务 host=127.0.0.1 port=5050 日志文件=%s", APP_DIR / "local-video-manager.log")
    LOG.info(
        "媒体工具: ffmpeg=%r ffprobe=%r",
        get_ffmpeg_path(),
        get_ffprobe_path(),
    )
    app.run(host="127.0.0.1", port=5050, debug=True)
