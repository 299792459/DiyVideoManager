"""读取标签/爬虫类 JSONL 导入请求的原始正文（multipart 或 raw）。"""
from typing import Optional, Tuple

from flask import request


def read_tags_import_request_body() -> Tuple[Optional[str], bytes]:
    raw_bytes: Optional[bytes] = None
    if request.files and request.files.get("file"):
        raw_bytes = request.files["file"].read()
    elif request.data:
        raw_bytes = request.data
    if not raw_bytes:
        return "empty body: use multipart file or raw JSONL", b""
    return None, raw_bytes


def decode_tags_import_text(raw_bytes: bytes) -> Tuple[Optional[str], str]:
    try:
        return None, raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        return "decode error: need UTF-8", ""
