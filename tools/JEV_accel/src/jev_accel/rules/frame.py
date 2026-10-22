"""A: L0 checks for "is this frame report-ready, and what to fix next".

Every check is computed from SCPI readbacks and the on-screen waveform, never from the PNG.
Labels match questions.FRAME_FIXES; the first violated label in that order is the L0 answer.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import math

from ..questions import FRAME_FIXES
from . import autoframe


@dataclass
class FrameInput:
    vdiv: float
    offset: float
    probe: float
    tdiv: float
    t_offset: float
    trig_level: float
    trig_status: str
    vtop: float | None
    vbase: float | None
    vmax: float
    vmin: float
    raw_min: int | None = None  # BYTE waveform extremes (0..255); None = use volts
    raw_max: int | None = None
    t50: float | None = None  # first 50% crossing, seconds, same time axis as t_offset
    rise_s: float | None = None
    menu_rows: int | None = None  # from rules.menu; None = unknown
    menu_open_rows: int = 80
    notes: list[str] = field(default_factory=list)  # caller hints, e.g. "RTIM overlay visible"
    trig_on_channel: bool = True  # False: trigger source is another channel, skip the 50% check
    view: str = "edge"  # "edge": edge must sit at center; "delay": two events, edge only has to be on screen
    period_s: float | None = None
    span_s: float | None = None
    min_periods: float = 2.0


@dataclass
class FrameResult:
    violations: list[str]
    borderline: list[str]
    metrics: dict
    suggestion: dict

    @property
    def label(self) -> str:
        return self.violations[0] if self.violations else "ok"

    @property
    def decisive(self) -> bool:
        """True when the rules alone settle it: one clear problem, or none and nothing near a limit."""
        return len(self.violations) == 1 or (not self.violations and not self.borderline)

    def to_dict(self) -> dict:
        return {**asdict(self), "label": self.label, "decisive": self.decisive}


def evaluate(fi: FrameInput, cfg: dict) -> FrameResult:
    if fi.view not in ("edge", "delay", "period"):
        raise ValueError("view must be edge, delay, or period")
    if not math.isfinite(fi.min_periods) or fi.min_periods <= 0:
        raise ValueError("min_periods must be finite and positive")
    c = cfg["frame"]
    hits: set[str] = set()
    near: set[str] = set()
    m: dict = {}

    def check(label: str, value: float, limit: float):
        if value > limit:
            hits.add(label)
        elif value > limit * c["borderline"]:
            near.add(label)

    vpp = fi.vmax - fi.vmin
    m["vpp_div"] = round(vpp / fi.vdiv, 3)
    if fi.trig_status == "WAIT" or m["vpp_div"] < c["flat_vpp_div"]:  # armed but nothing came, or flat
        hits.add("diagnose")

    if abs(fi.probe - c["expected_probe"]) > 1e-6:
        hits.add("fix_probe")

    if fi.menu_rows is not None:
        m["menu_rows"] = fi.menu_rows
        if fi.menu_rows > fi.menu_open_rows:
            hits.add("hide_menu")

    top = 4 * fi.vdiv - fi.offset
    bottom = -4 * fi.vdiv - fi.offset
    margin = c["clip_margin_div"] * fi.vdiv
    if fi.raw_min is not None and fi.raw_max is not None:
        clipped = fi.raw_max >= 252 or fi.raw_min <= 3
    else:
        clipped = fi.vmax >= top - margin or fi.vmin <= bottom + margin
    m["clipped"] = clipped

    vtop = fi.vtop if fi.vtop is not None else fi.vmax
    vbase = fi.vbase if fi.vbase is not None else fi.vmin
    mid = (vtop + vbase) / 2
    center_err = (mid + fi.offset) / fi.vdiv
    m["center_err_div"] = round(center_err, 3)
    fits = (fi.vmax - fi.vmin) <= 8 * fi.vdiv
    if abs(center_err) > c["max_center_div"] or (clipped and abs(center_err) > 0.25):
        hits.add("fix_offset")
    elif clipped or not fits:
        hits.add("change_vdiv")
    else:
        check("fix_offset", abs(center_err), c["max_center_div"])
        if m["vpp_div"] < c["small_vpp_div"]:  # trace uses too little of the 8 divisions
            hits.add("change_vdiv")

    swing = vtop - vbase
    if swing > 0 and fi.trig_on_channel:
        trig_frac = abs(fi.trig_level - mid) / swing
        m["trigger_frac"] = round(trig_frac, 3)
        # Period timing needs a level safely inside the swing, not the edge-view's 50% alignment.
        check("move_trigger", trig_frac, 0.4 if fi.view == "period" else c["max_trigger_frac"])

    if fi.view == "period":
        if fi.period_s is None or not math.isfinite(fi.period_s) or fi.period_s <= 0:
            hits.add("diagnose")
        else:
            span = fi.span_s if fi.span_s is not None else 10 * fi.tdiv
            m["visible_periods"] = span / fi.period_s
            if m["visible_periods"] < fi.min_periods:
                hits.add("shift_timebase")
    elif fi.t50 is not None:
        edge_div = (fi.t50 - fi.t_offset) / fi.tdiv
        m["edge_div"] = round(edge_div, 3)
        check("shift_timebase", abs(edge_div), c["max_edge_div"] if fi.view == "edge" else 4.5)

    if any("overlay" in n.lower() or "meas" in n.lower() for n in fi.notes):
        hits.add("clear_meas")
    if any("stale" in n.lower() or "not refreshed" in n.lower() for n in fi.notes):
        hits.add("rescreen")

    order = [k for k in FRAME_FIXES if k != "ok"]
    violations = [k for k in order if k in hits]
    borderline = [k for k in order if k in near and k not in hits]
    suggestion = {}
    if fi.vtop is not None and fi.vbase is not None:
        suggestion = autoframe.plan(fi.vtop, fi.vbase, fi.vmax, fi.vmin, rise_s=fi.rise_s)
        suggestion["tdiv"] = fi.tdiv  # keep the caller's timebase; only re-center it
        if fi.view == "period":
            suggestion.pop("t_offset", None)
        if fi.view != "period" and fi.t50 is not None:
            suggestion["t_offset"] = fi.t50
    if fi.view == "period" and "shift_timebase" in hits:
        suggestion["tdiv"] = autoframe.round_125(fi.min_periods * fi.period_s * 1.01 / 10)
    if "fix_probe" in hits:
        suggestion["probe"] = c["expected_probe"]
    return FrameResult(violations, borderline, m, suggestion)
