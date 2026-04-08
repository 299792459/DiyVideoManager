"""
步骤 1：模拟「网页分页解析」得到的代号 / 演员 / 标签 / 封面等。
后续可替换为真实请求与 HTML 解析，接口保持 discover() 的返回结构即可。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


# 模拟：从「站点」拉到的作品目录（含代号、演员、推荐标签、示例封面 URL）
# match_substrings：用于与输入 JSONL 的 n（文件名）做子串匹配，命中则视为该代号作品
MOCK_DISCOVERY: List[Dict[str, Any]] = [
    {
        "code": "SITE_V_DH_01",
        "actor_name": "【模拟】大华线演员",
        "match_substrings": ["大华"],
        "tags": ["风景", "瀑布", "旅行", "友情"],
        "cover_url": "https://picsum.photos/seed/crawler_dh/640/360.jpg",
        "notes": "mock：由代号 SITE_V_DH_01 分页解析得到",
    },
    {
        "code": "SITE_V_XM_02",
        "actor_name": "【模拟】小米线演员",
        "match_substrings": ["小米"],
        "tags": ["亲子", "户外", "钓鱼", "日落"],
        "cover_url": "https://picsum.photos/seed/crawler_xm/640/360.jpg",
        "notes": "mock：由代号 SITE_V_XM_02 分页解析得到",
    },
]


def step1_mock_discover() -> List[Dict[str, Any]]:
    """
    对应需求「1」：非中文名时按代号搜演员、再拉片单分页——此处全部用本地 mock 代替。
    返回的列表可被 match_filename_to_entity 使用。
    """
    return list(MOCK_DISCOVERY)


def match_filename_to_entity(
    filename: str, registry: Optional[List[Dict[str, Any]]] = None
) -> Optional[Dict[str, Any]]:
    """
    步骤 2：用 mock 表中的代号关联规则，按文件名子串匹配。
    命中第一条（列表顺序优先；可把更具体的规则放在前面）。
    """
    reg = registry if registry is not None else step1_mock_discover()
    name = filename or ""
    for ent in reg:
        for sub in ent.get("match_substrings") or []:
            if sub and sub in name:
                out = {k: v for k, v in ent.items() if k != "match_substrings"}
                out["matched_by"] = sub
                return out
    return None
