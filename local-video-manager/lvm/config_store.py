"""config.json 读写与数据目录结构。"""
import json
from pathlib import Path
from typing import Any, Dict

from lvm.constants import APP_DIR, CONFIG_PATH


def _default_config() -> Dict[str, Any]:
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


def load_config() -> Dict[str, Any]:
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


def save_config(cfg: Dict[str, Any]) -> None:
    with CONFIG_PATH.open("w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


def ensure_data_dirs(data_dir: Path) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "covers").mkdir(parents=True, exist_ok=True)
    cr = data_dir / "crawler"
    for sub in ("input", "output", "cache"):
        (cr / sub).mkdir(parents=True, exist_ok=True)
