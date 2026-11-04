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
from .scope_io import RIGOL, RigolDialect, Scope, dialect_of, first_cross, open_scope, prepare_read, same_channel

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
    if fi.view == "period":
        limits.pop("max_abs_edge_div")
        limits["minimum_visible_periods"] = fi.min_periods
        limits["max_trigger_frac_from_50pct"] = 0.4
    return {"goal": goal or "lab-report screenshot of a GPIO edge", "settings_and_levels": inputs,
            "derived": r.metrics, "limits": limits}


def frame_fix_scpi(label: str, r: FrameResult, channel: str = "CHAN1", d: RigolDialect = RIGOL,
                   vdiv: float | None = None) -> list[str]:
    """The SCPI for a frame fix in the scope's dialect (suggestion values use the RIGOL offset convention).
    vdiv is the V/div now on screen (the Tektronix positions in divisions)."""
    return [c for c in _frame_fix_scpi(label, r, channel, d, vdiv) if c]  # Tek has no vernier command


def _frame_fix_scpi(label: str, r: FrameResult, channel: str, d: RigolDialect, vdiv: float | None) -> list[str]:
    s = r.suggestion
    if label == "fix_probe":
        return [d.cmd_probe(channel, s.get("probe", 10))]
    if label == "hide_menu":
        return [d.hide_menu] if d.hide_menu else []  # Keysight: no SCPI closes a dialog
    if label in ("fix_offset", "change_vdiv") and r.metrics.get("clipped"):
        return []  # clipped levels are the screen edge: re-frame with autoframe instead (see check_frame)
    if label in ("fix_offset", "change_vdiv") and "vdiv" in s:
        cmds = [d.cmd_vernier(channel, s["vernier"]), d.cmd_vdiv(channel, s["vdiv"])]
        new_vdiv = s["vdiv"] if label == "change_vdiv" else vdiv
        return (cmds if label == "change_vdiv" or r.metrics.get("clipped") else []) + [
            d.cmd_offset(channel, s["offset"], vdiv=new_vdiv)]
    if label == "move_trigger" and "trigger_level" in s:
        return [d.cmd_trig_level(s["trigger_level"])]
    if label == "shift_timebase" and "t_offset" not in s and "tdiv" in s:
        return [d.cmd_tdiv(s["tdiv"])]
    if label == "shift_timebase" and "t_offset" in s:
        return [d.cmd_t_offset(s["t_offset"])]
    if label == "clear_meas":
        return [d.clear_meas] if d.clear_meas else []
    return []


def read_frame(sc: Scope, channel: str = "CHAN1", notes: list[str] | None = None,
               check_menu: bool = True, view: str = "edge", min_periods: float = 2.0) -> FrameInput:
    cfg, d = sc.cfg, dialect_of(sc)
    prepare_read(sc, peek=False)  # never disturb an armed single shot just to look at it
    t, v, raw = sc.waveform_raw(channel)
    vtop, vbase = sc.measure("VTOP", channel), sc.measure("VBASE", channel)
    period = sc.measure("PER", channel) if view == "period" else None
    level = d.trig_level(sc)
    slope = d.trig_slope(sc)
    t50 = None
    if view != "period" and vtop is not None and vbase is not None:
        t50 = first_cross(t, v, (vtop + vbase) / 2, rising=not slope.startswith("NEG"))
    menu_rows = None
    # TDS2014B: the side menu has its own column and a hardcopy costs ~8.5 s, so menu.in_frame=false
    # leaves the overlay check to jev_menu_visible (D) instead of every frame check
    if check_menu and cfg["menu"].get("in_frame", True):
        menu_rows = menu_rules.stats(menu_rules.bmp_to_array(sc.screenshot_bmp()), cfg)["hit_rows"]
    return FrameInput(
        vdiv=d.vdiv(sc, channel), offset=d.offset(sc, channel), probe=d.probe(sc, channel),
        tdiv=d.tdiv(sc), t_offset=d.t_offset(sc), trig_level=level,
        trig_status=d.trig_status(sc), vtop=vtop, vbase=vbase,
        vmax=float(v.max()) if v.size else 0.0, vmin=float(v.min()) if v.size else 0.0,
        raw_min=int(raw.min()) if raw.size else None, raw_max=int(raw.max()) if raw.size else None,
        t50=t50, rise_s=sc.measure("RTIM", channel) if view != "period" else None, menu_rows=menu_rows,
        menu_open_rows=cfg["menu"]["open_rows"], notes=list(notes or []),
        trig_on_channel=same_channel(d.trig_source(sc), channel), view=view,
        period_s=period,
        span_s=float(t[-1] - t[0]) if t.size > 1 else 0.0, min_periods=min_periods,
    )


def decide_frame(fi: FrameInput, jev_mode: str = "auto", goal: str = "", cfg: dict | None = None,
                 channel: str = "CHAN1", dialect: RigolDialect = RIGOL) -> dict:
    cfg = cfg or load_config()
    r = eval_frame(fi, cfg)
    # replay 2026-10-07: on purely numeric frames Jev stayed at 0.2-0.7 confidence (no usable answer),
    # on free-text notes it was ~0.9 and right, so by default only notes are worth the ~250 ms call
    use_jev = cfg["jev"].get("frame_ask", "always") != "notes_only" or bool(fi.notes)
    if fi.view == "period":
        use_jev = False  # numerical period visibility must not be overruled by a model
    label, source, d = _resolve(r.label, r.decisive, jev_mode, frame_state(fi, r, goal), Q.frame_questions(),
                                "next_fix", "frame", use_jev)
    ready = label == "ok"
    if d is not None and d.source == "jev":
        p = gate().confident_noul(d, "report_ready")
        if p is not None and source == "jev":
            ready = p and label == "ok"
    out = {"ready": ready, "next_fix": label, "source": source, "scpi": frame_fix_scpi(label, r, channel, dialect, fi.vdiv),
           "l0": r.to_dict(), "jev": d.to_dict() if d else None}
    if label in ("fix_offset", "change_vdiv") and r.metrics.get("clipped"):
        out["hint"] = ("trace is clipped: restore known vertical settings and retain the period timebase"
                       if fi.view == "period" else
                       "trace is clipped, so VTOP/VBASE are unreliable: call jev_autoframe (or check_frame apply=true)")
    elif (label == "diagnose" and fi.view == "period" and r.metrics.get("clipped") and fi.trig_status != "WAIT"
          and r.metrics["vpp_div"] >= cfg["frame"]["flat_vpp_div"]):
        # TDS2014B 2026-11-03: PERI is refused (9.9E37) on a clipped trace, so "no period" is the clip
        out["hint"] = "trace is clipped and the period is not measurable: restore known vertical settings"
    if label == "hide_menu" and not dialect.hide_menu:
        out["hint"] = _NO_HIDE_HINT.get(dialect.name, _NO_HIDE_HINT["keysight"])
    return out


_NO_HIDE_HINT = {
    "keysight": "a dialog or menu covers the graticule and no SCPI closes it: ask the user to press [Back]",
    "tek": ("a message or help box covers the graticule and no SCPI closes it: ask the user to close it on the "
            "scope (HELP again, or the menu button that opened it); the side menu column itself is harmless"),
}


def diagnose_fixes(fixes: dict, di: diag_rules.DiagInput, d: RigolDialect, channel: str) -> dict:
    """The rules write their fixes in RIGOL CHAN1 syntax; rewrite them for another scope's dialect."""
    out = dict(fixes)
    if "probe_ratio" in out:
        out["probe_ratio"] = [d.cmd_probe(channel, di.expected_probe), "then set V/div and trigger level again"]
    if "trig_level_out_of_range" in out and di.vmax is not None and di.vmin is not None:
        out["trig_level_out_of_range"] = d.cmd_trig_level((di.vmax + di.vmin) / 2, ".3f")
    if "sweep_mode" in out:
        out["sweep_mode"] = d.cmds_single()
    return out


def check_frame_on(sc: Scope, channel: str = "CHAN1", jev_mode: str = "auto", goal: str = "",
                   notes: list[str] | None = None, settle_s: float | None = None,
                   check_menu: bool = True, apply: bool = False, view: str = "edge",
                   min_periods: float = 2.0) -> dict:
    """Check using a caller-owned connection. settle_s=0 requires an already completed capture."""
    cfg = sc.cfg
    sc.settle(cfg["frame"]["settle_s"] if settle_s is None else settle_s)
    fi = read_frame(sc, channel, notes, check_menu, view, min_periods)
    out = decide_frame(fi, jev_mode, goal, cfg, channel, dialect_of(sc))
    if view == "period":
        out["measurements"] = {"PER": fi.period_s, "VTOP": fi.vtop, "VBASE": fi.vbase}
    if apply and view == "period" and out["next_fix"] == "hide_menu" and dialect_of(sc).hide_menu:
        cmd = dialect_of(sc).hide_menu
        sc.w(cmd)
        sc.settle(.8)
        fi.menu_rows = menu_rules.stats(menu_rules.bmp_to_array(sc.screenshot_bmp()), cfg)["hit_rows"]
        out = decide_frame(fi, jev_mode, goal, cfg, channel, dialect_of(sc))
        out["measurements"] = {"PER": fi.period_s, "VTOP": fi.vtop, "VBASE": fi.vbase}
        out["applied"] = [cmd]
    elif apply and "hint" in out and view == "edge":
        af = autoframe_on(sc, cfg, channel, "edge", None, True)
        out["autoframe"] = af
        out["applied"] = af["pre_scpi"] + af.get("scpi", []) + af.get("verify", {}).get("scpi", [])
    elif apply and out["scpi"]:
        for cmd in out["scpi"]:
            sc.w(cmd)
        out["applied"] = out["scpi"]
    return out


def check_frame(channel: str = "CHAN1", jev_mode: str = "auto", goal: str = "", notes: list[str] | None = None,
                settle_s: float | None = None, check_menu: bool = True, apply: bool = False,
                view: str = "edge", min_periods: float = 2.0) -> dict:
    with open_scope() as sc:
        return check_frame_on(sc, channel, jev_mode, goal, notes, settle_s, check_menu, apply, view, min_periods)


# --- B: diagnose -------------------------------------------------------------------------------
def decide_diagnose(di: diag_rules.DiagInput, jev_mode: str = "auto", cfg: dict | None = None,
                    dialect: RigolDialect = RIGOL, channel: str = "CHAN1") -> dict:
    cfg = cfg or load_config()
    r = diag_rules.evaluate(di, cfg)
    if dialect.name == "tek":  # RIGOL / Keysight accept the rules' SCPI as written
        r.fixes = diagnose_fixes(r.fixes, di, dialect, channel)
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
        d = dialect_of(sc)
        prepare_read(sc, peek=True)  # live VMAX/VMIN even when nothing triggers
        di = diag_rules.DiagInput(
            probe=d.probe(sc, channel), expected_probe=cfg["frame"]["expected_probe"],
            trig_level_set=trig_level_set, trig_level_readback=d.trig_level(sc),
            trig_status=d.trig_status(sc), sweep=d.sweep(sc), want_single=want_single,
            vmax=sc.measure("VMAX", channel), vmin=sc.measure("VMIN", channel),
            pc=int(pc, 16) if isinstance(pc, str) else pc, build_stale=build_stale,
        )
    return decide_diagnose(di, jev_mode, cfg, d, channel)


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
        d = dialect_of(sc)
        out = decide_menu(menu_rules.stats(menu_rules.bmp_to_array(sc.screenshot_bmp()), cfg), jev_mode, cfg)
        out["hide_supported"] = bool(d.hide_menu)
        if hide and out["visible"] and not d.hide_menu:
            out["hint"] = ("no SCPI closes this dialog or menu: ask the user to press [Back] on the scope"
                           if d.name != "tek" else _NO_HIDE_HINT["tek"])
        elif hide and out["visible"]:
            sc.w(d.hide_menu)  # RIGOL MOFF toggles: only pressed when the menu is known to be open
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
    d = dialect_of(sc)
    prepare_read(sc, peek=True)
    out: dict = {"applied": apply, "coarse_pass": False, "pre_scpi": []}
    probe = cfg["frame"]["expected_probe"]
    if apply and abs(d.probe(sc, channel) - probe) > 1e-6:
        out["pre_scpi"].append(d.cmd_probe(channel, probe))
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
        coarse_tdiv = autoframe.tdiv_for_delay(delay_s, d.min_tdiv) if delay_s else cfg["autoframe"]["coarse_tdiv"]
        cmds = [c for c in (d.cmd_vernier(channel, False), d.cmd_vdiv(channel, 1),
                            d.cmd_offset(channel, -mid, ".3f", vdiv=1), d.cmd_trig_level(mid, ".3f"),
                            d.cmd_tdiv(coarse_tdiv), d.cmd_t_offset(0, "g")) if c]
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
    plan = autoframe.plan(m["VTOP"], m["VBASE"], m["VMAX"], m["VMIN"], mode, m["RTIM"], delay_s, d.min_tdiv)
    cmds = [c for c in (d.cmd_vernier(channel, plan["vernier"]), d.cmd_vdiv(channel, plan["vdiv"]),
                        d.cmd_offset(channel, plan["offset"], vdiv=plan["vdiv"]),
                        d.cmd_trig_level(plan["trigger_level"]), d.cmd_tdiv(plan["tdiv"]),
                        d.cmd_t_offset(plan["t_offset"])) if c]
    out.update(plan=plan, scpi=cmds, readback={})
    if apply:
        for c in cmds:
            sc.w(c)
        sc.settle(0.3)
        # only verified on the TDS2014B so far; RIGOL / Keysight keep their hardware-tested behavior
        verify = _verify_vertical(sc, d, channel, plan) if d.name == "tek" else None
        if verify:
            out["verify"] = verify
        out["readback"] = {q: sc.q(q) for q in d.readback_queries(channel)}
    return out


def _verify_vertical(sc: Scope, d: RigolDialect, channel: str, plan: dict) -> dict | None:
    """One re-check at the planned timebase. The levels came from the coarse timebase, where a GPIO edge's
    overshoot is not resolved; at the edge timebase it is (TDS2014B 2026-11-03: VMAX-VMIN 3.36 V at
    250 us/div, 3.76 V at 250 ns/div, so 0.5 V/div clipped). Widen V/div once, keep the planned center."""
    _, _, raw = sc.waveform_raw(channel)
    vmax, vmin = sc.measure("VMAX", channel), sc.measure("VMIN", channel)
    if raw is None or not raw.size or vmax is None or vmin is None:
        return None
    clipped = int(raw.max()) >= 252 or int(raw.min()) <= 3
    span_div = (vmax - vmin) / plan["vdiv"]
    if not clipped and span_div <= 8 / 1.05:
        return None
    bump = autoframe.vdiv_for(plan["vdiv"] * 1.2 * 8 / 1.15, 0.0)  # at least one readable step wider
    vdiv = max(autoframe.vdiv_for(vmax, vmin), bump)
    cmds = [c for c in (d.cmd_vernier(channel, not autoframe.is_std_step(vdiv)), d.cmd_vdiv(channel, vdiv),
                        d.cmd_offset(channel, plan["offset"], vdiv=vdiv)) if c]
    for c in cmds:
        sc.w(c)
    sc.settle(0.3)
    return {"reason": "clipped" if clipped else "span", "vmax": vmax, "vmin": vmin,
            "span_div_before": round(span_div, 2), "vdiv": vdiv, "scpi": cmds}


def autoframe_apply(channel: str = "CHAN1", mode: str = "edge", delay_s: float | None = None,
                    apply: bool = True) -> dict:
    cfg = load_config()
    with open_scope(cfg) as sc:
        return autoframe_on(sc, cfg, channel, mode, delay_s, apply)
