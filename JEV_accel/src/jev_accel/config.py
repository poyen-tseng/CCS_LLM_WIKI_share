"""Project configuration: config.json at the project root, with SCOPE_ADDR / SCOPE_BIND env overrides."""
from __future__ import annotations

import copy
import json
import os
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "results"
CAPTURES = ROOT / "captures"


def _merge(base: dict, extra: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in extra.items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


@lru_cache(maxsize=1)
def load_config() -> dict:
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    local = ROOT / "config.local.json"  # optional, untracked overrides
    if local.exists():
        cfg = _merge(cfg, json.loads(local.read_text(encoding="utf-8")))
    if os.environ.get("SCOPE_ADDR"):
        cfg["scope"]["addr"] = os.environ["SCOPE_ADDR"]
    if "SCOPE_BIND" in os.environ:
        cfg["scope"]["bind"] = os.environ["SCOPE_BIND"]
    return cfg
