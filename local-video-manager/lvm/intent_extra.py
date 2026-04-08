"""可选依赖 intent_local（fastembed）；缺失时提供空实现。"""
from typing import Any, Dict

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

    def probe_intent_model(model_name: str) -> Dict[str, Any]:
        return {"ok": False, "error": "intent_local 模块不可用"}
