"""路径常量、视频扩展名、搜索同义词等。"""
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = APP_DIR / "config.json"

VIDEO_EXTENSIONS = {".mp4", ".mkv", ".avi", ".mov", ".flv", ".wmv", ".webm", ".m4v"}

# 意图搜索：中文词同义词扩展（非向量模型）
QUERY_SYNONYMS = {
    "丝袜": {"黑丝", "白丝", "丝"},
    "黑丝": {"丝袜", "丝"},
    "白丝": {"丝袜", "丝"},
    "丝": {"丝袜", "黑丝", "白丝"},
}
