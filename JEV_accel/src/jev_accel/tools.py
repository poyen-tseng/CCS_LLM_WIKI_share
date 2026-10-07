"""Collect -> L0 rules -> Jev (only when the rules are not decisive) -> concrete next step.

Shared by the CLI and the MCP server. jev_mode: "auto" (default) asks Jev only when L0 is not
decisive, "always" asks every time (benchmarking), "off" never asks.
The state sent to Jev holds measured values and derived metrics, never the L0 verdict.
"""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from . import questions as Q
from .config import load_config
from .jev import Decision, JevGate
from .rules import autoframe, diagnose as diag_rules, flash as flash_rules, menu as menu_rules
from .rules.frame import FrameInput, FrameResult, evaluate as eval_frame
from .scope_io import Scope, first_cross, open_scope

_gate: JevGate | None = None


def gate() -> JevGate:
    global _gate
    if _gate is None:
        _gate = JevGate()
    return _gate


def _resolve(l0_label: str, decisive: bool, mode: str, state: dict, questions: dict, qid: str,
             tag: str, use_jev: bool = True) -> tuple[str, str, Decision | None]:
    """A decisive rule answer is a measured fact and always wins; "always" still asks Jev so the
    disagreement is logged (replay 2026-10-07: Jev answered ok_running at 0.9 on a stale build).
    use_jev=False routes a case to the rules even when they are not decisive (see config jev.*_ask)."""
    if mode == "off" or (mode == "auto" and (decisive or not use_jev)):
        return l0_label, "l0", None
    d = gate().ask(state, questions, tag)
    if decisive or not use_jev:
        return l0_label, "l0", d
    label = gate().confident_choice(d, qid)
    if label is not None:
        return label, "jev", d
    return l0_label, "l0_fallback", d


# --- A: frame ---------------------------------------------------------------------------------
def frame_state(fi: FrameInput, r: FrameResult, goal: str = "") -> dict:
    c = load_config()["frame"]
    inputs = {k: v for k, v in asdict(fi).items() if k not in ("menu_open_rows",)}
    # the rubric, not the verdict: without limits Jev cannot tell 0.36 div off-center from fine
    limits = {
        "expected_probe": c["expected_probe"],
        "max_abs_center_err_div": c["max_center_div"],
        "max_abs_edge_div": c["max_edge_div"] if fi.view == "edge" else 4.5,
        "max_trigger_frac_from_50pct": c["max_trigger_frac"],
        "min_vpp_div_not_flat": c["flat_vpp_div"],
        "min_vpp_div_not_tiny": c["small_vpp_div"],
        "menu_rows_open_above": fi.menu_open_rows,
        "clipped_means": "raw BYTE value reached 0-3 or 252-255",
        "trig_status_WAIT_means": "armed but never triggered",
    }
    return {"goal": goal or "lab-report screenshot of a GPIO edge", "settings_and_levels": inputs,
            "derived": r.metrics, "limits": limits}


def frame_fix_scpi(label: str, r: FrameResult, channel: str = "CHAN1") -> list[str]:
    s = r.suggestion
    ch = f":{channel}"
    if label == "fix_probe":
        return [f"{ch}:PROB {s.get('probe', 10)}"]
    if label == "hide_menu":
        return [":SYST:KEY:PRES MOFF"]
    if label in ("fix_offset", "change_vdiv") and r.metrics.get("clipped"):
        return []  # clipped levels are the screen edge: re-frame with autoframe instead (see check_frame)
    if label in ("fix_offset", "change_vdiv") and "vdiv" in s:
        cmds = [f"{ch}:VERN {'ON' if s['vernier'] else 'OFF'}", f"{ch}:SCAL {s['vdiv']:g}"]
        return (cmds if label == "change_vdiv" or r.metrics.get("clipped") else []) + [f"{ch}:OFFS {s['offset']:g}"]
    if label == "move_trigger" and "trigger_level" in s:
        return [f":TRIG:EDGE:LEV {s['trigger_level']:g}"]
    if label == "shift_timebase" and "t_offset" in s:
        return [f":TIM:MAIN:OFFS {s['t_offset']:.4g}"]
    if label == "clear_meas":
        return [":MEAS:CLE ALL"]
    return []


def read_frame(sc: Scope, channel: str = "CHAN1", notes: list[str] | None = None,
               check_menu: bool = True, view: str = "edge") -> FrameInput:
    cfg = sc.cfg
    t, v, raw = sc.waveform_raw(channel)
    vtop, vbase = sc.measure("VTOP", channel), sc.measure("VBASE", channel)
    level = sc.qf(":TRIG:EDGE:LEV?")
    slope = sc.q(":TRIG:EDGE:SLOP?").upper()
    t50 = None
    if vtop is not None and vbase is not None:
        t50 = first_cross(t, v, (vtop + vbase) / 2, rising=not slope.startswith("NEG"))
    menu_rows = None
    if check_menu:
        menu_rows = menu_rules.stats(menu_rules.bmp_to_array(sc.screenshot_bmp()), cfg)["hit_rows"]
    return FrameInput(
        vdiv=sc.qf(f":{channel}:SCAL?"), offset=sc.qf(f":{channel}:OFFS?"), probe=sc.qf(f":{channel}:PROB?"),
        tdiv=sc.qf(":TIM:MAIN:SCAL?"), t_offset=sc.qf(":TIM:MAIN:OFFS?"), trig_level=level,
        trig_status=sc.q(":TRIG:STAT?"), vtop=vtop, vbase=vbase,
        vmax=float(v.max()) if v.size else 0.0, vmin=float(v.min()) if v.size else 0.0,
        raw_min=int(raw.min()) if raw.size else None, raw_max=int(raw.max()) if raw.size else None,
        t50=t50, rise_s=sc.measure("RTIM", channel), menu_rows=menu_rows,
        menu_open_rows=cfg["menu"]["open_rows"], notes=list(notes or []),
        trig_on_channel=sc.q(":TRIG:EDGE:SOUR?").upper() == channel.upper(), view=view,
    )


def decide_frame(fi: FrameInput, jev_mode: str = "auto", goal: str = "", cfg: dict | None = None,
                 channel: str = "CHAN1") -> dict:
    cfg = cfg or load_config()
    r = eval_frame(fi, cfg)
    # replay 2026-10-07: on purely numeric frames Jev stayed at 0.2-0.7 confidence (no usable answer),
    # on free-text notes it was ~0.9 and right, so by default only notes are worth the ~250 ms call
    use_jev = cfg["jev"].get("frame_ask", "always") != "notes_only" or bool(fi.notes)
    label, source, d = _resolve(r.label, r.decisive, jev_mode, frame_state(fi, r, goal), Q.frame_questions(),
                                "next_fix", "frame", use_jev)
    ready = label == "ok"
    if d is not None and d.source == "jev":
        p = gate().confident_noul(d, "report_ready")
        if p is not None and source == "jev":
            ready = p and label == "ok"
    out = {"ready": ready, "next_fix": label, "source": source, "scpi": frame_fix_scpi(label, r, channel),
           "l0": r.to_dict(), "jev": d.to_dict() if d else None}
    if label in ("fix_offset", "change_vdiv") and r.metrics.get("clipped"):
        out["hint"] = "trace is clipped, so VTOP/VBASE are unreliable: call jev_autoframe (or check_frame apply=true)"
    return out


def check_frame(channel: str = "CHAN1", jev_mode: str = "auto", goal: str = "", notes: list[str] | None = None,
                settle_s: float | None = None, check_menu: bool = True, apply: bool = False,
                view: str = "edge") -> dict:
    cfg = load_config()
    with open_scope(cfg) as sc:
        sc.settle(cfg["frame"]["settle_s"] if settle_s is None else settle_s)
        fi = read_frame(sc, channel, notes, check_menu, view)
        out = decide_frame(fi, jev_mode, goal, cfg, channel)
        if apply and "hint" in out and view == "edge":
            af = autoframe_on(sc, cfg, channel, "edge", None, True)
            out["autoframe"] = af
            out["applied"] = af["pre_scpi"] + af.get("scpi", [])
        elif apply and out["scpi"]:
            for cmd in out["scpi"]:
                sc.w(cmd)
            out["applied"] = out["scpi"]
    return out


# --- B: diagnose -------------------------------------------------------------------------------
def decide_diagnose(di: diag_rules.DiagInput, jev_mode: str = "auto", cfg: dict | None = None) -> dict:
    cfg = cfg or load_config()
    r = diag_rules.evaluate(di, cfg)
    state = {"capture": {k: (hex(v) if k == "pc" and v is not None else v) for k, v in asdict(di).items()},
             "derived": r.metrics,
             "limits": {"boot_rom_pc_at_or_above": hex(diag_rules.BOOT_ROM_MIN),
                        "flat_if_vpp_below_v": cfg["diagnose"]["flat_vpp_v"],
                        "level_clamped_if_readback_differs_by_frac": cfg["diagnose"]["level_readback_tol"]}}
    label, source, d = _resolve(r.label, r.decisive, jev_mode, state, Q.diagnose_questions(), "root_cause",
                                "diagnose")
    sw = label != "wiring"
    if d is not None and d.source == "jev":
        j = gate().confident_noul(d, "fix_is_software")
        sw = sw if j is None else j
    return {"root_cause": label, "fix_is_software": sw, "source": source,
            "fix": r.fixes.get(label, "re-run jev_diagnose_capture after the next capture"),
            "l0": r.to_dict(), "jev": d.to_dict() if d else None}


def diagnose(channel: str = "CHAN1", want_single: bool = True, trig_level_set: float | None = None,
             pc: str | int | None = None, build_stale: bool | None = None, jev_mode: str = "auto") -> dict:
    cfg = load_config()
    with open_scope(cfg) as sc:
        di = diag_rules.DiagInput(
            probe=sc.qf(f":{channel}:PROB?"), expected_probe=cfg["frame"]["expected_probe"],
            trig_level_set=trig_level_set, trig_level_readback=sc.qf(":TRIG:EDGE:LEV?"),
            trig_status=sc.q(":TRIG:STAT?"), sweep=sc.q(":TRIG:SWE?"), want_single=want_single,
            vmax=sc.measure("VMAX", channel), vmin=sc.measure("VMIN", channel),
            pc=int(pc, 16) if isinstance(pc, str) else pc, build_stale=build_stale,
        )
    return decide_diagnose(di, jev_mode, cfg)


# --- C: flash ----------------------------------------------------------------------------------
def flash_state(text: str | None = None, path: str | None = None, expected_range: tuple[float, float] | None = None,
                measured: float | None = None, expectation: str = "", jev_mode: str = "auto") -> dict:
    if text is None:
        if path is None:
            raise ValueError("give the terminal text or a path to it")
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    p = flash_rules.parse(text)
    r = flash_rules.classify(p, expected_range, measured)
    with_behavior = bool(expectation) and measured is not None and expected_range is None
    state = {"terminal_tail": "\n".join(l for l in text.splitlines() if "GEL" not in l)[-2500:],
             "parsed": r.to_dict()["parsed"], "expectation": expectation, "measured": measured,
             "expected_range": list(expected_range) if expected_range else None}
    decisive = r.decisive and not with_behavior
    label, source, d = _resolve(r.label, decisive, jev_mode, state, Q.flash_questions(with_behavior),
                                "flash_state", "flash")
    matches = r.behavior_matches
    if d is not None and d.source == "jev" and with_behavior:
        matches = gate().confident_noul(d, "behavior_matches_source")
        if matches is False and label == "ok_running":
            label, source = "rebuild_needed", "jev"
    return {"state": label, "source": source, "behavior_matches_source": matches,
            "next_step": flash_rules.NEXT_STEPS[label], "l0": r.to_dict(), "jev": d.to_dict() if d else None}



# --- D: menu -----------------------------------------------------------------------------------
def decide_menu(stats: dict, jev_mode: str = "auto", cfg: dict | None = None) -> dict:
    cfg = cfg or load_config()
    l0 = menu_rules.classify(stats, cfg)
    visible, source, d = l0, "l0", None
    # replay 2026-10-07: Jev sat at ~0.45 on gray-zone pixel counts, so auto mode uses the wiki rule
    if jev_mode == "always" or (jev_mode == "auto" and l0 is None and cfg["jev"].get("menu_ask", True)):
        d = gate().ask({"pixel_stats": stats, "thresholds": cfg["menu"]}, Q.menu_questions(), "menu")
        j = gate().confident_noul(d, "menu_visible")
        if j is not None and l0 is None:  # a clear pixel count is a fact; Jev only settles the gray zone
            visible, source = j, "jev"
    if visible is None:  # ambiguous and no confident Jev answer: the wiki's 40-row rule
        visible, source = stats["hit_rows"] > cfg["menu"]["wiki_rows"], "l0_fallback"
    return {"visible": visible, "source": source, "stats": stats, "jev": d.to_dict() if d else None}


def menu(hide: bool = False, jev_mode: str = "auto") -> dict:
    cfg = load_config()
    with open_scope(cfg) as sc:
        out = decide_menu(menu_rules.stats(menu_rules.bmp_to_array(sc.screenshot_bmp()), cfg), jev_mode, cfg)
        if hide and out["visible"]:
            sc.w(":SYST:KEY:PRES MOFF")  # toggles: only pressed when the menu is known to be open
            sc.settle(0.8)
            after = decide_menu(menu_rules.stats(menu_rules.bmp_to_array(sc.screenshot_bmp()), cfg), "off", cfg)
            out["after_hide"] = {"visible": after["visible"], "hit_rows": after["stats"]["hit_rows"]}
    return out


# --- E: autoframe ------------------------------------------------------------------------------
LEVELS = ("VTOP", "VBASE", "VMAX", "VMIN", "RTIM")


def _levels(sc: Scope, channel: str) -> dict:
    return {k: sc.measure(k, channel) for k in LEVELS}


def autoframe_on(sc: Scope, cfg: dict, channel: str = "CHAN1", mode: str = "edge", delay_s: float | None = None,
                 apply: bool = True) -> dict:
    """Probe ratio first (every level is in probe units), then a coarse pass when VTOP/VBASE are not
    measurable (seen 2026-10-07: 1x probe setting, 1 us/div on a 1 kHz signal), then the fine plan."""
    out: dict = {"applied": apply, "coarse_pass": False, "pre_scpi": []}
    probe = cfg["frame"]["expected_probe"]
    if apply and abs(sc.qf(f":{channel}:PROB?") - probe) > 1e-6:
        out["pre_scpi"].append(f":{channel}:PROB {probe}")
        sc.w(out["pre_scpi"][-1])
        sc.settle(0.5)
    _, _, raw = sc.waveform_raw(channel)
    clipped = bool(raw.size) and (int(raw.max()) >= 252 or int(raw.min()) <= 3)
    out["was_clipped"] = clipped
    m = _levels(sc, channel)
    if (clipped or m["VTOP"] is None or m["VBASE"] is None) and apply:
        vmax, vmin = m["VMAX"], m["VMIN"]
        # clipped extremes are the screen edge, not the signal: center on the 3.3 V logic midpoint instead
        usable = not clipped and vmax is not None and vmin is not None and vmax - vmin > 0.3
        mid = (vmax + vmin) / 2 if usable else 1.65
        coarse_tdiv = autoframe.tdiv_for_delay(delay_s) if delay_s else cfg["autoframe"]["coarse_tdiv"]
        cmds = [f":{channel}:VERN OFF", f":{channel}:SCAL 1", f":{channel}:OFFS {-mid:.3f}",
                f":TRIG:EDGE:LEV {mid:.3f}", f":TIM:MAIN:SCAL {coarse_tdiv:g}", ":TIM:MAIN:OFFS 0"]
        for c in cmds:
            sc.w(c)
        out["pre_scpi"] += cmds
        out["coarse_pass"] = True
        sc.settle(cfg["autoframe"]["coarse_settle_s"])
        m = _levels(sc, channel)
    out["measured"] = m
    if m["VTOP"] is None or m["VBASE"] is None:
        out["error"] = "VTOP/VBASE still invalid after the coarse pass: no signal on the channel (run jev_diagnose_capture)"
        return out
    plan = autoframe.plan(m["VTOP"], m["VBASE"], m["VMAX"], m["VMIN"], mode, m["RTIM"], delay_s)
    cmds = [f":{channel}:VERN {'ON' if plan['vernier'] else 'OFF'}", f":{channel}:SCAL {plan['vdiv']:g}",
            f":{channel}:OFFS {plan['offset']:g}", f":TRIG:EDGE:LEV {plan['trigger_level']:g}",
            f":TIM:MAIN:SCAL {plan['tdiv']:g}", f":TIM:MAIN:OFFS {plan['t_offset']:.4g}"]
    out.update(plan=plan, scpi=cmds, readback={})
    if apply:
        for c in cmds:
            sc.w(c)
        sc.settle(0.3)
        out["readback"] = {q: sc.q(q) for q in (f":{channel}:PROB?", f":{channel}:SCAL?", f":{channel}:OFFS?",
                                                ":TRIG:EDGE:LEV?", ":TIM:MAIN:SCAL?", ":TIM:MAIN:OFFS?")}
    return out


def autoframe_apply(channel: str = "CHAN1", mode: str = "edge", delay_s: float | None = None,
                    apply: bool = True) -> dict:
    cfg = load_config()
    with open_scope(cfg) as sc:
        return autoframe_on(sc, cfg, channel, mode, delay_s, apply)
