"""
可选本地标签语义检索：依赖 fastembed（ONNX，CPU）。
仅缓存「全库标签名」的向量；查询时编码用户输入，与每条视频的标签做最大余弦相似度，
再与原有字符级意图分加权融合。不对每个视频文件名单独做向量，以控制耗时与内存。
"""
from __future__ import annotations

import logging
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np

LOG = logging.getLogger("video_manager.intent")

_EMBED = None
_MODEL_ID: Optional[str] = None

_TAG_VEC: Dict[str, np.ndarray] = {}
_TAG_NAMES_FINGERPRINT: str = ""


def is_fastembed_available() -> bool:
    try:
        import fastembed  # noqa: F401

        return True
    except ImportError:
        return False


def probe_intent_model(model_name: str) -> Dict[str, object]:
    """探测模型是否可加载（会触发下载）。"""
    if not is_fastembed_available():
        return {"ok": False, "error": "未安装 fastembed，请执行: pip install fastembed"}
    try:
        model = _get_embed_model(model_name)
        v = _embed_one(model, "ping")
        return {"ok": True, "dim": int(v.shape[0])}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _get_embed_model(model_name: str):
    global _EMBED, _MODEL_ID
    if _EMBED is not None and _MODEL_ID == model_name:
        return _EMBED
    from fastembed import TextEmbedding

    LOG.info("加载 fastembed 模型（首次运行会从网络拉取 ONNX，约百余 MB）: %s", model_name)
    _EMBED = TextEmbedding(model_name=model_name)
    _MODEL_ID = model_name
    return _EMBED


def _l2n(v: np.ndarray) -> np.ndarray:
    n = float(np.linalg.norm(v))
    if n < 1e-12:
        return v
    return (v / n).astype(np.float32)


def _embed_many(model, texts: List[str], batch_size: int = 128) -> np.ndarray:
    """返回 (len(texts), dim) float32，L2 已归一化。"""
    if not texts:
        return np.zeros((0, 0), dtype=np.float32)
    out: List[np.ndarray] = []
    for i in range(0, len(texts), batch_size):
        chunk = texts[i : i + batch_size]
        for emb in model.embed(chunk):
            out.append(_l2n(np.asarray(emb, dtype=np.float32)))
    if not out:
        return np.zeros((0, 0), dtype=np.float32)
    return np.stack(out, axis=0)


def _embed_one(model, text: str) -> np.ndarray:
    m = _embed_many(model, [text], batch_size=1)
    return m[0]


def _fingerprint_tag_names(names: List[str]) -> str:
    return "\n".join(sorted(names))


def ensure_tag_vectors(tag_names: List[str], model_name: str) -> None:
    """全库标签名 → 向量缓存；标签增删改后指纹变化会重建。"""
    global _TAG_VEC, _TAG_NAMES_FINGERPRINT
    fp = _fingerprint_tag_names(tag_names)
    if fp == _TAG_NAMES_FINGERPRINT and _TAG_VEC:
        return
    model = _get_embed_model(model_name)
    if not tag_names:
        _TAG_VEC = {}
        _TAG_NAMES_FINGERPRINT = fp
        return
    mat = _embed_many(model, tag_names)
    _TAG_VEC = {tag_names[i]: mat[i] for i in range(len(tag_names))}
    _TAG_NAMES_FINGERPRINT = fp
    LOG.info("标签向量缓存已更新 count=%s dim=%s", len(_TAG_VEC), mat.shape[1] if len(mat) else 0)


def _max_tag_similarity(tags: List[str], q: np.ndarray) -> float:
    if not tags:
        return 0.0
    best = 0.0
    for t in tags:
        v = _TAG_VEC.get(t)
        if v is None:
            continue
        c = float(np.dot(q, v))
        if c > best:
            best = c
    return max(0.0, best)


def apply_intent_hybrid_search(
    videos: List[Dict],
    search: str,
    intent_cfg: Dict,
    all_tag_names: List[str],
    expand_query_terms: Callable[[str], List[str]],
    calc_intent_score: Callable[[str, List[str]], float],
) -> List[Dict]:
    """
    混合：lexical（原 calc_intent_score） + 标签语义（query 与视频标签的最大余弦）。
    保留条件：lex>0 或 sem>=min_semantic。
    排序：按加权综合分降序。
    """
    if not search or not videos:
        return videos

    model_name = (intent_cfg.get("model") or "BAAI/bge-small-zh-v1.5").strip()
    blend = float(intent_cfg.get("lexical_blend", 0.42))
    blend = max(0.0, min(1.0, blend))
    min_sem = float(intent_cfg.get("min_semantic", 0.18))

    ensure_tag_vectors(all_tag_names, model_name)
    model = _get_embed_model(model_name)

    q_text = (intent_cfg.get("query_prefix") or "").strip() + search.strip()
    q_vec = _embed_one(model, q_text)

    terms = expand_query_terms(search)
    lexical_scores: List[float] = []
    sem_scores: List[float] = []
    for v in videos:
        combined = f"{v['filename']} {' '.join(v.get('tags') or [])}".lower()
        lexical_scores.append(calc_intent_score(combined, terms))
        sem_scores.append(_max_tag_similarity(v.get("tags") or [], q_vec))

    max_lex = max(lexical_scores) if lexical_scores else 0.0
    if max_lex <= 0:
        max_lex = 1.0

    scored: List[Tuple[float, Dict]] = []
    for i, v in enumerate(videos):
        lex = lexical_scores[i]
        sem = sem_scores[i]
        lex_n = lex / (max_lex + 1e-9)
        final = blend * lex_n + (1.0 - blend) * sem
        if lex <= 0 and sem < min_sem:
            continue
        scored.append((final, v))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [x[1] for x in scored]


def clear_tag_vector_cache() -> None:
    """单元测试或需要强制重建缓存时可调用。"""
    global _TAG_VEC, _TAG_NAMES_FINGERPRINT
    _TAG_VEC = {}
    _TAG_NAMES_FINGERPRINT = ""
