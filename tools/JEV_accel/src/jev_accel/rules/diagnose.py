"""B: L0 root-cause rules for a flat / untriggered single-shot capture.

Labels match questions.ROOT_CAUSES; the first matching label in that order is the L0 answer.
'wiring' is only returned when no software cause matches, and then it is never decisive.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

from ..questions import ROOT_CAUSES

BOOT_ROM_MIN = 0x3F0000


@dataclass
class DiagInput:
    probe: float
    expected_probe: float
    trig_level_set: float | None
    trig_level_readback: float
    trig_status: str
    sweep: str
    want_single: bool
    vmax: float | None  # live (AUTO / running) extremes on the trigger source, probe-corrected
    vmin: float | None
    pc: int | None = None  # from flash_state / DSS output
    build_stale: bool | None = None


@dataclass
class DiagResult:
    causes: list[str]
    metrics: dict
    fixes: dict
    also_fix: list[str] = field(default_factory=list)  # wrong settings that do not explain the symptom

    @property
    def label(self) -> str:
        return self.causes[0] if self.causes else "wiring"

    @property
    def decisive(self) -> bool:
        return len(self.causes) == 1 and self.causes[0] != "wiring"

    def to_dict(self) -> dict:
        return {**asdict(self), "label": self.label, "decisive": self.decisive,
                "fix_is_software": self.label != "wiring"}


def evaluate(di: DiagInput, cfg: dict) -> DiagResult:
    c = cfg["diagnose"]
    hits: set[str] = set()
    m: dict = {}
    fixes: dict = {}

    if di.pc is not None:
        m["pc"] = hex(di.pc)
        if di.pc >= BOOT_ROM_MIN:
            hits.add("pc_in_bootrom")
            fixes["pc_in_bootrom"] = "reload with edge_run.js (reset BEFORE loadProgram, then halt), check PC < 0x10000"
    if di.build_stale:
        hits.add("stale_build")
        fixes["stale_build"] = "touch the edited source (e.g. Init.c) and rerun gmake, then reload"
    if abs(di.probe - di.expected_probe) > 1e-6:
        hits.add("probe_ratio")
        fixes["probe_ratio"] = [f":CHAN1:PROB {di.expected_probe:g}", "then set V/div and trigger level again"]

    if di.trig_level_set is not None:
        tol = max(abs(di.trig_level_set) * c["level_readback_tol"], 0.01)
        m["level_clamped"] = abs(di.trig_level_readback - di.trig_level_set) > tol
        if m["level_clamped"]:
            hits.add("trig_level_out_of_range")
    if di.vmax is not None and di.vmin is not None:
        vpp = di.vmax - di.vmin
        m["vpp"] = round(vpp, 4)
        m["flat"] = vpp < c["flat_vpp_v"]
        if not m["flat"] and not (di.vmin < di.trig_level_readback < di.vmax):
            hits.add("trig_level_out_of_range")
    if "trig_level_out_of_range" in hits and di.vmax is not None and di.vmin is not None:
        fixes["trig_level_out_of_range"] = f":TRIG:EDGE:LEV {(di.vmax + di.vmin) / 2:.3f}"

    if di.want_single and di.sweep.upper().startswith("AUTO"):
        hits.add("sweep_mode")
        fixes["sweep_mode"] = [":TRIG:SWE NORM", ":SING"]

    # A ratio, sweep or level error scales or misses a real signal; none of them makes a LIVE trace sit
    # at 0 V. Seen on the scope 2026-10-07: CH1 1x after a restart, AUTO sweep, nothing on the pin.
    live = di.trig_status.upper() in ("AUTO", "RUN") or di.sweep.upper().startswith("AUTO")
    m["live_flat_near_zero"] = bool(
        m.get("flat") and live and abs((di.vmax + di.vmin) / 2) < c["flat_vpp_v"])
    also = []
    if m["live_flat_near_zero"]:
        for k in ("probe_ratio", "sweep_mode", "trig_level_out_of_range"):
            if k in hits:
                hits.discard(k)
                also.append(k)
    elif "probe_ratio" in hits and "trig_level_out_of_range" in hits:
        # a wrong ratio rescales every level, so the clamp is its symptom (replay: Jev picked the clamp at 0.94)
        hits.discard("trig_level_out_of_range")
        also.append("trig_level_out_of_range")

    causes = [k for k in ROOT_CAUSES if k in hits]
    if not causes:
        fixes["wiring"] = ("no live signal on the channel: check that the program runs (jev_flash_state) and "
                           "drives the pin, then ask the user to check probe tip/ground"
                           if m["live_flat_near_zero"] else
                           "no software cause found: ask the user to check probe tip/ground on the pin")
    return DiagResult(causes, m, fixes, also)
