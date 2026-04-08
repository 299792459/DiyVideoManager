"""ffmpeg/ffprobe、默认封面、系统内打开文件与外部播放器。"""
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Tuple

import sqlite3

from lvm.cover_names import cover_name_for_path
from lvm.logging_config import LOG

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
    cover_name = cover_name_for_path(str(video_path.resolve()))
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
