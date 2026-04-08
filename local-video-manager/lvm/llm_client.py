"""OpenAI 兼容 Chat、候选构建、AI 搜索回退逻辑。"""
import json
from typing import Any, Dict, List, Optional, Tuple
from urllib import error as url_error
from urllib import request as url_request

from lvm.intent_extra import apply_intent_hybrid_search, is_fastembed_available
from lvm.logging_config import LOG
from lvm.search_query import calc_intent_score, expand_query_terms, filter_videos_lexical_search


def safe_json_loads_from_text(s: str) -> Optional[Dict]:
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


def openai_compatible_chat(messages: List[Dict], cfg: Dict) -> Tuple[bool, Dict]:
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

    parsed = safe_json_loads_from_text(raw) or {}
    choices = parsed.get("choices") or []
    if not choices:
        return False, {"error": "llm response has no choices"}
    content = (((choices[0] or {}).get("message") or {}).get("content") or "").strip()
    obj = safe_json_loads_from_text(content)
    if not obj:
        return False, {"error": "cannot parse llm json content", "raw_content": content}
    return True, obj


def build_ai_candidates(videos: List[Dict], max_candidates: int) -> List[Dict]:
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
