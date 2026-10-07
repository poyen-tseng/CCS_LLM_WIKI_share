"""Replay the transcript-derived fixtures through the decision functions (no hardware needed).

Each case is decided with the given jev_mode; the summary reports accuracy, which layer answered,
Jev latency (p50/p95), confidence and input tokens. Misses are listed with their source line.
"""
from __future__ import annotations

import json
import statistics
import time
from dataclasses import fields

from . import tools, tools_ccs
from .config import RESULTS, ROOT, load_config
from .rules.diagnose import DiagInput
from .rules.frame import FrameInput

FIXTURES = ROOT / "tests" / "fixtures"
BRIDGES = ("frame", "diagnose", "flash", "menu", "build", "dss")


def load(bridge: str) -> list[dict]:
    lines = (FIXTURES / f"{bridge}.jsonl").read_text(encoding="utf-8").splitlines()
    return [json.loads(l) for l in lines if l.strip()]


def _frame_input(d: dict) -> FrameInput:
    names = {f.name for f in fields(FrameInput)}
    return FrameInput(**{k: v for k, v in d.items() if k in names})


def decide_case(bridge: str, case: dict, jev_mode: str) -> tuple[object, dict]:
    cfg = load_config()
    if bridge == "frame":
        out = tools.decide_frame(_frame_input(case["input"]), jev_mode, cfg=cfg)
        return out["next_fix"], out
    if bridge == "diagnose":
        out = tools.decide_diagnose(DiagInput(**case["input"]), jev_mode, cfg)
        return out["root_cause"], out
    if bridge == "flash":
        rng = tuple(case["expected_range"]) if "expected_range" in case else None
        out = tools.flash_state(path=str(FIXTURES / "logs" / case["log"]), expected_range=rng,
                                measured=case.get("measured"), expectation=case.get("expectation", ""),
                                jev_mode=jev_mode)
        return out["state"], out
    if bridge == "menu":
        out = tools.decide_menu(case["stats"], jev_mode, cfg)
        return out["visible"], out
    if bridge == "build":
        text = tools_ccs._decode((FIXTURES / "logs" / case["log"]).read_bytes())
        out = tools_ccs.decide_build(text, case.get("changed", []), case.get("project_dir", ""),
                                     case.get("elapsed_s"), jev_mode)
        return out["result"], out
    if bridge == "dss":
        text = tools_ccs._decode((FIXTURES / "logs" / case["log"]).read_bytes())
        out = tools_ccs.decide_dss(text, case.get("probe_present"), None, jev_mode)
        return out["state"], out
    raise ValueError(bridge)


QID = {"frame": "next_fix", "diagnose": "root_cause", "flash": "flash_state", "menu": "menu_visible",
       "build": "build_error", "dss": "dss_state"}


def jev_pick(bridge: str, answers: dict | None) -> tuple[object, float | None]:
    """Jev's own top answer for the bridge's main question (None when Jev was not asked)."""
    a = (answers or {}).get(QID[bridge])
    if not a:
        return None, None
    if a.get("type") == "noul":
        return a["noul"] > 0.5, a["noul"]
    return a.get("choice"), a.get("confidence")


def _pct(xs: list[float], q: float) -> float | None:
    if not xs:
        return None
    xs = sorted(xs)
    return round(xs[min(len(xs) - 1, int(round(q * (len(xs) - 1))))], 1)


def run(jev_mode: str = "auto", bridges: tuple[str, ...] = BRIDGES, save: bool = True) -> dict:
    rows = []
    for b in bridges:
        for case in load(b):
            t0 = time.perf_counter()
            got, out = decide_case(b, case, jev_mode)
            jev = out.get("jev") or {}
            pick, pick_conf = jev_pick(b, jev.get("answers"))
            rows.append({
                "bridge": b, "id": case["id"], "expected": case["accept"], "got": got,
                "correct": got in case["accept"], "source": out["source"],
                "needs_jev": case.get("needs_jev", False),
                "jev_pick": pick, "jev_pick_conf": pick_conf,
                "jev_pick_correct": None if pick is None else pick in case["accept"],
                "jev_source": jev.get("source"), "jev_latency_ms": jev.get("latency_ms"),
                "jev_answers": jev.get("answers"), "input_tokens": jev.get("input_tokens"),
                "jev_error": jev.get("error"), "elapsed_ms": round((time.perf_counter() - t0) * 1000, 1),
                "case_source": case["source"],
            })
    summary = {"jev_mode": jev_mode, "ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "by_bridge": {}}
    for b in bridges:
        rs = [r for r in rows if r["bridge"] == b]
        lat = [r["jev_latency_ms"] for r in rs if r["jev_source"] == "jev"]
        confs = []
        for r in rs:
            for a in (r["jev_answers"] or {}).values():
                if "confidence" in a:
                    confs.append(a["confidence"])
        summary["by_bridge"][b] = {
            "cases": len(rs), "correct": sum(r["correct"] for r in rs),
            "accuracy": round(sum(r["correct"] for r in rs) / len(rs), 3) if rs else None,
            "answered_by": {s: sum(r["source"] == s for r in rs) for s in sorted({r["source"] for r in rs})},
            "jev_calls": len(lat), "jev_p50_ms": _pct(lat, 0.5), "jev_p95_ms": _pct(lat, 0.95),
            "jev_raw_correct": sum(bool(r["jev_pick_correct"]) for r in rs),
            "jev_raw_asked": sum(r["jev_pick_correct"] is not None for r in rs),
            "jev_confident_wrong": sum(r["jev_pick_correct"] is False and (r["jev_pick_conf"] or 0) >= 0.8
                                       and not isinstance(r["jev_pick"], bool) for r in rs),
            "jev_mean_confidence": round(statistics.mean(confs), 3) if confs else None,
            "input_tokens": sum(r["input_tokens"] or 0 for r in rs),
        }
    summary["misses"] = [{k: r[k] for k in ("bridge", "id", "expected", "got", "source", "needs_jev", "case_source")}
                         for r in rows if not r["correct"]]
    errors = sorted({r["jev_error"] for r in rows if r["jev_error"]})
    if errors:
        summary["jev_errors"] = errors
    if save:
        RESULTS.mkdir(parents=True, exist_ok=True)
        path = RESULTS / f"replay_{jev_mode}_{time.strftime('%Y%m%d_%H%M%S')}.json"
        path.write_text(json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=2, default=str),
                        encoding="utf-8")
        summary["saved"] = str(path)
    return summary


def markdown(summary: dict) -> str:
    lines = [f"Replay `jev_mode={summary['jev_mode']}` ({summary['ts']})", "",
             "| bridge | cases | final | answered by | Jev own pick | Jev wrong at conf>=0.8 | Jev calls "
             "| p50 ms | p95 ms | mean conf | tokens |",
             "|---|---|---|---|---|---|---|---|---|---|---|"]
    for b, s in summary["by_bridge"].items():
        by = ", ".join(f"{k} {v}" for k, v in s["answered_by"].items())
        raw = f"{s['jev_raw_correct']}/{s['jev_raw_asked']}" if s["jev_raw_asked"] else "-"
        lines.append(f"| {b} | {s['cases']} | {s['correct']}/{s['cases']} | {by} | {raw} | "
                     f"{s['jev_confident_wrong']} | {s['jev_calls']} | "
                     f"{s['jev_p50_ms']} | {s['jev_p95_ms']} | {s['jev_mean_confidence']} | {s['input_tokens']} |")
    if summary["misses"]:
        lines += ["", "Misses:"] + [f"- {m['bridge']} {m['id']}: expected {m['expected']}, got {m['got']} "
                                     f"({m['source']}{', needs Jev' if m['needs_jev'] else ''}) — {m['case_source']}" for m in summary["misses"]]
    return "\n".join(lines)
