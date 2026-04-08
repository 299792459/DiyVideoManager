"""封面文件名规则：与视频绝对路径的 MD5 对应（与爬虫导入共用）。"""
import hashlib


def cover_name_for_path(resolved_path: str) -> str:
    return f"{hashlib.md5(resolved_path.encode('utf-8')).hexdigest()}.jpg"
