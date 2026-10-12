"""Project configuration: config.json at the project root, with SCOPE_MODEL / SCOPE_ADDR / SCOPE_BIND env overrides.

scope.model picks the scope ("rigol" or "keysight"). Per-model blocks are resolved here, so callers keep
reading cfg["scope"]["addr"/"port"] and cfg["menu"][...] for the active model:
  "scope": {"model": ..., "rigol": {"addr", "port"}, "keysight": {"addr", "port"}, ...}
  "menu":  {"rigol": {...}, "keysight": {...}}
"""
from __future__ import annotations

import copy
import json
import os
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "results"
CAPTURES = ROOT / "captures"
MODELS = ("rigol", "keysight")


def _merge(base: dict, extra: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in extra.items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


@lru_cache(maxsize=4)
def load_config(model: str | None = None) -> dict:
    """model=None: the configured model (SCOPE_MODEL env, else scope.model). Tests that replay RIGOL
    fixtures pass model="rigol"."""
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    local = ROOT / "config.local.json"  # optional, untracked overrides
    if local.exists():
        cfg = _merge(cfg, json.loads(local.read_text(encoding="utf-8")))
    model = (model or os.environ.get("SCOPE_MODEL") or cfg["scope"].get("model", "rigol")).lower()
    if model not in MODELS:
        raise ValueError(f"scope model {model!r}: use one of {MODELS}")
    sc = cfg["scope"]
    block = sc.get(model, {})
    for m in MODELS:
        sc.pop(m, None)
    for k, v in block.items():  # a top-level key (e.g. config.local.json {"scope": {"addr": ...}}) wins
        sc.setdefault(k, v)
    sc["model"] = model
    if isinstance(cfg.get("menu"), dict) and model in cfg["menu"]:
        cfg["menu"] = cfg["menu"][model]
    if os.environ.get("SCOPE_ADDR"):
        sc["addr"] = os.environ["SCOPE_ADDR"]
    if "SCOPE_BIND" in os.environ:
        sc["bind"] = os.environ["SCOPE_BIND"]
    return cfg
