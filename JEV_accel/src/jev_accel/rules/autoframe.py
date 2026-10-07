"""E: compute V/div, offset, trigger level and timebase from measured levels. Pure functions, no Jev.

Rules come from LLM_WIKI/rigol-scope.md and the accepted Ex1/Ex2 captures:
  * V/div fits (VMAX-VMIN)*1.15 into 8 div, rounded up to one significant digit (0.528 -> 0.6, VERN on)
  * offset = -(VTOP+VBASE)/2 (RIGOL: positive offset moves the trace up)
  * trigger level = (VTOP+VBASE)/2, not the nominal 1.65 V
  * edge: rise time spans >= 2 div, floor 5 ns/div;  delay: delay fits in 8 div, offset = delay/2
"""
from __future__ import annotations

import math

MIN_TDIV = 5e-9  # MSO5104 fastest timebase
STD_MANTISSAS = (1.0, 2.0, 5.0)


def _decade(x: float) -> float:
    return 10.0 ** math.floor(math.log10(x))


def is_std_step(x: float) -> bool:
    m = x / _decade(x)
    return any(math.isclose(m, s, rel_tol=1e-6) for s in STD_MANTISSAS) or math.isclose(m, 10.0, rel_tol=1e-6)


def round_125(x: float, up: bool = True) -> float:
    """Round to the 1-2-5 sequence (up or down)."""
    dec = _decade(x)
    steps = [s * dec for s in (1.0, 2.0, 5.0, 10.0)]
    if up:
        return next(s for s in steps if s >= x * (1 - 1e-9))
    return max(s for s in [0.5 * dec, *steps] if s <= x * (1 + 1e-9))


def vdiv_for(vmax: float, vmin: float, margin: float = 1.15) -> float:
    need = max((vmax - vmin) * margin / 8.0, 1e-3)
    fine = _decade(need)  # one significant digit: readable values like the accepted 0.6 V/div
    v = math.ceil(need / fine - 1e-9) * fine
    return round(v, 6)


def tdiv_for_edge(rise_s: float | None) -> float:
    if not rise_s or rise_s <= 0:
        return MIN_TDIV
    return max(MIN_TDIV, round_125(rise_s / 2.0, up=False))


def tdiv_for_delay(delay_s: float) -> float:
    return max(MIN_TDIV, round_125(abs(delay_s) / 8.0, up=True))


def plan(vtop: float, vbase: float, vmax: float | None = None, vmin: float | None = None,
         mode: str = "edge", rise_s: float | None = None, delay_s: float | None = None) -> dict:
    """Return the settings a centered, unclipped report frame needs."""
    vmax = vtop if vmax is None else vmax
    vmin = vbase if vmin is None else vmin
    mid = (vtop + vbase) / 2.0
    vdiv = vdiv_for(vmax, vmin)
    out = {
        "vdiv": vdiv,
        "vernier": not is_std_step(vdiv),
        "offset": round(-mid, 3),
        "trigger_level": round(mid, 3),
    }
    if mode == "delay" and delay_s:
        out["tdiv"] = tdiv_for_delay(delay_s)
        out["t_offset"] = delay_s / 2.0
    else:
        out["tdiv"] = tdiv_for_edge(rise_s)
        out["t_offset"] = 0.0
    return out
