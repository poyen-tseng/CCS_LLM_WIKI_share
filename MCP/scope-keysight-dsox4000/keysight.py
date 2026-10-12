"""Keysight (Agilent) InfiniiVision DSO-X 4000 driver over LAN (pyvisa + pyvisa-py, raw SCPI socket 5025).

Tested on a DSO-X 4034A, firmware 07.30. Differences from the RIGOL driver that matter:
  * :CHANn:OFFSet is the voltage at screen center (RIGOL: the opposite sign).
  * waveform volts = (raw - yref) * yinc + yorigin.
  * an unknown query gets no reply at all (it times out); the error queue then holds -113.
  * there is no run-state query; RUN / WAIT / STOP comes from :OPERegister:CONDition? bits.

CLI usage (python -I keysight.py <cmd> ...):
    idn | status | shot [out.png] [black] | wave <ch> [norm|raw|max] [points] | meas <item> <ch> [ch2]
    demo <function> [on|off] | mark <rise_10_90|fall_90_10|swing|off> [ch] | recover
    q "<SCPI query>" | w "<SCPI command>"
"""
from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pyvisa

HERE = Path(__file__).resolve().parent
CAPTURES = HERE / "captures"
DEFAULT_ADDR = "192.168.137.60"
INVALID = 9.9e37  # value the scope returns when a measurement cannot be made

# OPERation status register bits (:OPER:COND?)
OPER_RUN = 1 << 3
OPER_WAIT_TRIG = 1 << 5

# EDK training signals this firmware accepts (probed 2026-10-12; MSO, serial buses and SQU are rejected)
DEMO_FUNCTIONS = ("SIN", "NOIS", "PHAS", "RING", "SING", "AM", "CLK", "GLIT", "BURS", "RUNT", "TRAN",
                  "RFB", "SHOL", "LFS", "FMB", "HARM", "COUP", "ETE")

# RIGOL-style item names -> Keysight :MEASure header. Native headers pass through unchanged.
MEAS_ALIASES = {
    "FREQ": "FREQ", "PER": "PER", "VPP": "VPP", "VMAX": "VMAX", "VMIN": "VMIN", "VTOP": "VTOP",
    "VBASE": "VBAS", "VBAS": "VBAS", "VAMP": "VAMP", "VAVG": "VAV", "VAV": "VAV", "VRMS": "VRMS",
    "RTIM": "RIS", "RIS": "RIS", "FTIM": "FALL", "FALL": "FALL", "PWID": "PWID", "NWID": "NWID",
    "PDUT": "DUTY", "DUTY": "DUTY", "NDUT": "NDUT", "OVER": "OVER", "PRES": "PRES",
    "DEL": "DEL", "DELAY": "DEL", "PHAS": "PHAS", "PHASE": "PHAS",
}
TWO_SOURCE = {"DEL", "PHAS"}
# items whose query takes an interval (and type) before the source
MEAS_PREFIX = {"VAV": "DISP,", "VRMS": "DISP,DC,"}


def load_config() -> dict:
    cfg = {"addr": DEFAULT_ADDR, "bind": "192.168.137.1"}
    path = HERE / "config.json"
    if path.exists():
        cfg.update(json.loads(path.read_text(encoding="utf-8")))
    if os.environ.get("KS_ADDR"):
        cfg["addr"] = os.environ["KS_ADDR"]
    if "KS_BIND" in os.environ:
        cfg["bind"] = os.environ["KS_BIND"]
    return cfg


def _resolve_resource(addr: str | None) -> str:
    addr = addr or load_config()["addr"]
    return addr if "::" in addr else f"TCPIP0::{addr}::5025::SOCKET"


class ScopeError(RuntimeError):
    pass


@dataclass
class Waveform:
    channel: str
    mode: str
    t: np.ndarray
    v: np.ndarray
    xinc: float
    raw: np.ndarray | None = None

    @property
    def sample_rate(self) -> float:
        return 1.0 / self.xinc if self.xinc else 0.0

    def stats(self) -> dict:
        v = self.v
        return {
            "channel": self.channel,
            "mode": self.mode,
            "points": int(v.size),
            "sample_interval_s": self.xinc,
            "sample_rate_Sa_s": self.sample_rate,
            "t_start_s": float(self.t[0]) if v.size else None,
            "t_end_s": float(self.t[-1]) if v.size else None,
            "v_min": float(v.min()) if v.size else None,
            "v_max": float(v.max()) if v.size else None,
            "v_mean": float(v.mean()) if v.size else None,
            "v_rms": float(np.sqrt(np.mean(v**2))) if v.size else None,
            "v_pp": float(v.max() - v.min()) if v.size else None,
        }

    def save_csv(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        np.savetxt(path, np.column_stack([self.t, self.v]), delimiter=",",
                   header="time_s,volt_V", comments="", fmt="%.9e")
        return path


def levels(v: np.ndarray, bins: int = 64) -> tuple[float, float]:
    """Low and high logic levels: the fullest histogram bin below / above the median."""
    hist, edges = np.histogram(v, bins=bins)
    centers = (edges[:-1] + edges[1:]) / 2
    med = float(np.median(v))
    lo_mask, hi_mask = centers <= med, centers > med
    lo = float(centers[lo_mask][np.argmax(hist[lo_mask])]) if lo_mask.any() else float(v.min())
    hi = float(centers[hi_mask][np.argmax(hist[hi_mask])]) if hi_mask.any() else float(v.max())
    return lo, hi


def crossings(t: np.ndarray, v: np.ndarray, level: float, rising: bool = True) -> np.ndarray:
    """All crossings of `level` on the given slope, linearly interpolated."""
    above = v >= level if rising else v <= level
    i = np.flatnonzero(~above[:-1] & above[1:])
    dv = v[i + 1] - v[i]
    frac = np.divide(level - v[i], dv, out=np.zeros_like(dv), where=dv != 0)
    return t[i] + frac * (t[i + 1] - t[i])


def edge_points(t: np.ndarray, v: np.ndarray, rising: bool = True) -> dict | None:
    """10/50/90 % times of the edge nearest the trigger point (t=0), from locally measured levels.
    The 10 % (rising) point is the last crossing before the 50 % point, the 90 % point the first after it,
    so a neighbouring edge is never picked."""
    lo, hi = levels(v)
    amp = hi - lo
    if amp <= 0:
        return None
    l10, l50, l90 = (lo + f * amp for f in (0.1, 0.5, 0.9))
    c50 = crossings(t, v, l50, rising)
    if c50.size == 0:
        return None
    t50 = float(c50[np.argmin(np.abs(c50))])
    first, last = (l10, l90) if rising else (l90, l10)
    before = crossings(t, v, first, rising)
    after = crossings(t, v, last, rising)
    before, after = before[before <= t50], after[after >= t50]
    t_first = float(before[-1]) if before.size else None
    t_last = float(after[0]) if after.size else None
    if rising:
        return {"t10": t_first, "t50": t50, "t90": t_last, "low": lo, "high": hi}
    return {"t90": t_first, "t50": t50, "t10": t_last, "low": lo, "high": hi}


class DSOX4000:
    def __init__(self, addr: str | None = None, timeout_ms: int = 5000):
        self.resource = _resolve_resource(addr)
        self._rm = pyvisa.ResourceManager("@py")
        self.inst = self._rm.open_resource(
            self.resource, read_termination="\n", write_termination="\n", timeout=timeout_ms
        )

    def close(self) -> None:
        try:
            self.inst.close()
        finally:
            self._rm.close()

    def __enter__(self) -> "DSOX4000":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # --- basic I/O -------------------------------------------------------
    def query(self, cmd: str, timeout_ms: int | None = None) -> str:
        if timeout_ms is None:
            return self.inst.query(cmd).strip()
        old = self.inst.timeout
        self.inst.timeout = timeout_ms
        try:
            return self.inst.query(cmd).strip()
        finally:
            self.inst.timeout = old

    def qf(self, cmd: str) -> float:
        return float(self.query(cmd))

    def write(self, cmd: str, check: bool = True) -> None:
        self.inst.write(cmd)
        if check:
            self.check_error(cmd)

    def errors(self) -> list[str]:
        out = []
        for _ in range(10):
            err = self.query(":SYST:ERR?")
            if err.startswith(("+0,", "0,")):
                break
            out.append(err)
        return out

    def check_error(self, context: str = "") -> None:
        errors = self.errors()
        if errors:
            raise ScopeError(f"{context}: {'; '.join(errors)}")

    def query_checked(self, cmd: str, timeout_ms: int = 2000) -> str:
        """A query that may be unsupported: the scope never answers those, so use a short timeout
        and report the error queue instead of hanging."""
        try:
            return self.query(cmd, timeout_ms)
        except pyvisa.errors.VisaIOError as e:
            if e.error_code != pyvisa.constants.StatusCode.error_timeout:
                raise
            errs = self.errors()
            raise ScopeError(f"{cmd}: no reply within {timeout_ms} ms (unsupported query?) "
                             f"{'; '.join(errs) or 'error queue empty'}") from None

    def recover(self) -> None:
        """Unblock the scope after a query that waits for a trigger that never comes (in NORM sweep a
        waveform or measurement query blocks the whole SCPI parser, on every connection, until a
        trigger). A VXI-11 device clear plus a forced trigger releases it; then reconnect the socket."""
        host = self.resource.split("::")[1]
        inst = self._rm.open_resource(f"TCPIP0::{host}::inst0::INSTR", timeout=4000)
        try:
            inst.clear()
            inst.write(":TRIG:FORC")
            time.sleep(0.2)
        finally:
            inst.close()
        timeout = self.inst.timeout
        try:
            self.inst.close()
        except Exception:
            pass
        self.inst = self._rm.open_resource(self.resource, read_termination="\n", write_termination="\n",
                                           timeout=timeout)
        self.errors()  # drop the -109 "No Data For Operation" left by the aborted query

    def ensure_data(self, what: str = "waveform / measurement") -> None:
        """Refuse a data query while the trigger is armed but not triggering: it would block the scope."""
        if self.run_state() == "WAIT":
            raise ScopeError(
                f"{what} refused: the trigger is armed in NORM sweep and no trigger is arriving, so the query "
                "would block the scope until one does. Stop (ks_run_control stop) to read the last "
                "acquisition, force a trigger, fix the trigger level, or use sweep AUTO.")

    def idn(self) -> str:
        return self.query("*IDN?")

    def options(self) -> list[str]:
        return [o for o in self.query("*OPT?").split(",") if o and o != "0"]

    # --- acquisition control ---------------------------------------------
    def run(self) -> None:
        self.write(":RUN")

    def stop(self) -> None:
        self.write(":STOP")

    def single(self) -> None:
        self.write(":SING")

    def force_trigger(self) -> None:
        self.write(":TRIG:FORC")

    def autoscale(self) -> None:
        self.write(":AUT", check=False)
        self.query("*OPC?", timeout_ms=20000)
        self.check_error(":AUT")

    def oper_condition(self) -> int:
        return int(float(self.query(":OPER:COND?")))

    def run_bits(self) -> str:
        """RUN / WAIT / STOP from the condition register alone. WAIT only means the trigger is armed:
        in NORM sweep the bit stays set between triggers even when triggers keep coming."""
        cond = self.oper_condition()
        if not cond & OPER_RUN:
            return "STOP"
        return "WAIT" if cond & OPER_WAIT_TRIG else "RUN"

    def run_state(self, window_s: float = 0.25) -> str:
        """RIGOL-style trigger status: STOP; AUTO (auto sweep: auto-triggers also set :TER?, so real and
        forced triggers cannot be told apart); in NORM sweep TD when a trigger arrives within window_s,
        else WAIT. The wait bit alone is not enough: measured 2026-10-12 it read 0x18 while triggering at
        one setup and stayed 0x38 at another while :TER? latched every read. Clears the :TER? latch."""
        cond = self.oper_condition()
        if not cond & OPER_RUN:
            return "STOP"
        if self.query(":TRIG:SWE?").upper().startswith("AUTO"):
            return "AUTO"
        # the wait bit is not used: it also clears for a moment after a setting change (seen 2026-10-12:
        # TD reported, then a measurement blocked), so only a trigger latched inside the window counts
        self.triggered_since_last_read()  # drop a latch left from earlier
        end = time.time() + window_s
        while True:
            time.sleep(0.02)
            if self.triggered_since_last_read():
                return "TD"
            if not self.oper_condition() & OPER_RUN:
                return "STOP"  # a single shot completed
            if time.time() >= end:
                return "WAIT"

    def triggered_since_last_read(self) -> bool:
        """:TER? is cleared by reading it."""
        return self.query(":TER?").lstrip("+") == "1"

    def wait_trigger(self, timeout_s: float = 10.0) -> str:
        """After single(): poll until the acquisition completes (STOP) or timeout (then WAIT)."""
        end = time.time() + timeout_s
        st = self.run_bits()
        while st != "STOP" and time.time() < end:
            time.sleep(0.05)
            st = self.run_bits()
        return "STOP" if st == "STOP" else "WAIT"

    # --- settings ---------------------------------------------------------
    def set_channel(self, ch: int, display: bool | None = None, scale: float | None = None,
                    offset: float | None = None, coupling: str | None = None,
                    probe: float | None = None, bwlimit: bool | None = None,
                    impedance: str | None = None, vernier: bool | None = None) -> None:
        """offset is the voltage at screen center (Keysight convention)."""
        p = f":CHAN{ch}"
        if display is not None:
            self.write(f"{p}:DISP {1 if display else 0}")
        if probe is not None:  # probe ratio first: scale and offset are in probe-corrected volts
            self.write(f"{p}:PROB {probe:g}")
        if impedance is not None:
            self.write(f"{p}:IMP {impedance.upper()}")
        if coupling is not None:
            self.write(f"{p}:COUP {coupling.upper()}")
        if bwlimit is not None:
            self.write(f"{p}:BWL {1 if bwlimit else 0}")
        if vernier is not None:
            self.write(f"{p}:VERN {1 if vernier else 0}")
        if scale is not None:
            self.write(f"{p}:SCAL {scale:g}")
        if offset is not None:
            self.write(f"{p}:OFFS {offset:g}")

    def set_timebase(self, scale: float | None = None, position: float | None = None,
                     reference: str | None = None) -> None:
        if scale is not None:
            self.write(f":TIM:SCAL {scale:g}")
        if position is not None:
            self.write(f":TIM:POS {position:g}")
        if reference is not None:
            self.write(f":TIM:REF {reference.upper()}")

    def set_trigger_edge(self, source: str | None = None, level: float | None = None,
                         slope: str | None = None, sweep: str | None = None, coupling: str | None = None,
                         noise_reject: bool | None = None, holdoff: float | None = None) -> None:
        self.write(":TRIG:MODE EDGE")
        if source is not None:
            self.write(f":TRIG:EDGE:SOUR {_source(source)}")
        if slope is not None:
            self.write(f":TRIG:EDGE:SLOP {slope.upper()}")
        if level is not None:
            self.write(f":TRIG:EDGE:LEV {level:g}")
        if coupling is not None:
            self.write(f":TRIG:EDGE:COUP {coupling.upper()}")
        self._trigger_common(sweep, noise_reject, holdoff)

    def set_trigger_glitch(self, source: str | None = None, level: float | None = None,
                           polarity: str | None = None, qualifier: str | None = None,
                           width: float | None = None, width_max: float | None = None,
                           sweep: str | None = None, noise_reject: bool | None = None,
                           holdoff: float | None = None) -> None:
        """Pulse-width trigger. qualifier LESS: pulses narrower than width; GRE: wider than width;
        RANG: between width and width_max."""
        self.write(":TRIG:MODE GLIT")
        if source is not None:
            self.write(f":TRIG:GLIT:SOUR {_source(source)}")
        if polarity is not None:
            self.write(f":TRIG:GLIT:POL {polarity.upper()}")
        if level is not None:
            self.write(f":TRIG:GLIT:LEV {level:g}")
        if qualifier is not None:
            self.write(f":TRIG:GLIT:QUAL {qualifier.upper()}")
        q = (qualifier or self.query(":TRIG:GLIT:QUAL?")).upper()
        if width is not None:
            if q.startswith("RANG"):
                hi = width_max if width_max is not None else width * 2
                self.write(f":TRIG:GLIT:RANG {hi:g},{width:g}")
            elif q.startswith("GRE"):
                self.write(f":TRIG:GLIT:GRE {width:g}")
            else:
                self.write(f":TRIG:GLIT:LESS {width:g}")
        self._trigger_common(sweep, noise_reject, holdoff)

    def _trigger_common(self, sweep, noise_reject, holdoff) -> None:
        if sweep is not None:
            self.write(f":TRIG:SWE {sweep.upper()}")
        if noise_reject is not None:
            self.write(f":TRIG:NREJ {1 if noise_reject else 0}")
        if holdoff is not None:
            self.write(f":TRIG:HOLD {holdoff:g}")

    def trigger_settings(self) -> dict:
        q = self.query
        mode = q(":TRIG:MODE?")
        out = {"mode": mode, "sweep": q(":TRIG:SWE?"), "holdoff_s": float(q(":TRIG:HOLD?")),
               "noise_reject": q(":TRIG:NREJ?") == "1", "run_state": self.run_state()}
        if mode.startswith("GLIT"):
            out.update(glitch_source=q(":TRIG:GLIT:SOUR?"), glitch_polarity=q(":TRIG:GLIT:POL?"),
                       glitch_qualifier=q(":TRIG:GLIT:QUAL?"), glitch_less_s=float(q(":TRIG:GLIT:LESS?")),
                       glitch_greater_s=float(q(":TRIG:GLIT:GRE?")), glitch_level_V=float(q(":TRIG:GLIT:LEV?")))
        else:
            out.update(edge_source=q(":TRIG:EDGE:SOUR?"), edge_slope=q(":TRIG:EDGE:SLOP?"),
                       edge_level_V=float(q(":TRIG:EDGE:LEV?")), edge_coupling=q(":TRIG:EDGE:COUP?"))
        return out

    def status(self) -> dict:
        q = self.query
        chans = {}
        for ch in range(1, 5):
            p = f":CHAN{ch}"
            chans[f"CHAN{ch}"] = {
                "display": q(f"{p}:DISP?") == "1",
                "scale_V_div": float(q(f"{p}:SCAL?")),
                "offset_V_center": float(q(f"{p}:OFFS?")),
                "coupling": q(f"{p}:COUP?"),
                "impedance": q(f"{p}:IMP?"),
                "probe": float(q(f"{p}:PROB?")),
                "bwlimit": q(f"{p}:BWL?") == "1",
                "vernier": q(f"{p}:VERN?") == "1",
            }
        trigger = self.trigger_settings()
        return {
            "idn": self.idn(),
            "run_state": trigger["run_state"],
            "timebase": {"scale_s_div": float(q(":TIM:SCAL?")), "position_s": float(q(":TIM:POS?")),
                         "reference": q(":TIM:REF?"), "mode": q(":TIM:MODE?")},
            "acquire": {"sample_rate_Sa_s": float(q(":ACQ:SRAT?")), "points": int(float(q(":ACQ:POIN?"))),
                        "type": q(":ACQ:TYPE?")},
            "trigger": trigger,
            "channels": chans,
            "demo": {"function": q(":DEMO:FUNC?"), "output": q(":DEMO:OUTP?") == "1"},
            "markers": self.markers_readback(),
        }

    # --- demo (EDK training signals on the Demo 1 / Demo 2 terminals) ------
    def demo(self, function: str | None = None, output: bool | None = None) -> dict:
        if function is not None:
            f = function.upper()
            if f not in DEMO_FUNCTIONS:
                raise ScopeError(f"demo function {function} not supported; use one of {', '.join(DEMO_FUNCTIONS)}")
            self.write(f":DEMO:FUNC {f}")
        if output is not None:
            self.write(f":DEMO:OUTP {1 if output else 0}")
        return {"function": self.query(":DEMO:FUNC?"), "output": self.query(":DEMO:OUTP?") == "1"}

    # --- markers (cursors) --------------------------------------------------
    def set_markers(self, mode: str | None = None, x1: float | None = None, x2: float | None = None,
                    y1: float | None = None, y2: float | None = None,
                    source1: str | None = None, source2: str | None = None) -> None:
        if mode is not None:
            self.write(f":MARK:MODE {mode.upper()}")
        if source1 is not None:
            self.write(f":MARK:X1Y1 {_source(source1)}")
        if source2 is not None:
            self.write(f":MARK:X2Y2 {_source(source2)}")
        if x1 is not None:
            self.write(f":MARK:X1P {x1:g}")
        if x2 is not None:
            self.write(f":MARK:X2P {x2:g}")
        if y1 is not None:
            self.write(f":MARK:Y1P {y1:g}")
        if y2 is not None:
            self.write(f":MARK:Y2P {y2:g}")

    def markers_readback(self) -> dict:
        q = self.query
        mode = q(":MARK:MODE?")
        out = {"mode": mode}
        if mode.upper().startswith("OFF"):
            return out
        vals = {"x1_s": ":MARK:X1P?", "x2_s": ":MARK:X2P?", "y1_V": ":MARK:Y1P?", "y2_V": ":MARK:Y2P?",
                "dx_s": ":MARK:XDEL?", "dy_V": ":MARK:YDEL?"}
        for k, cmd in vals.items():
            v = float(q(cmd))
            out[k] = None if abs(v) >= INVALID else v
        out["inv_dx_Hz"] = 1 / out["dx_s"] if out.get("dx_s") else None
        out["source1"], out["source2"] = q(":MARK:X1Y1?"), q(":MARK:X2Y2?")
        return out

    def auto_markers(self, kind: str, source: str | int = "CHAN1") -> dict:
        """Place waveform-tracking markers from the on-screen waveform:
        rise_10_90 / fall_90_10 on the edge nearest the trigger, or swing = X at the 50 % point,
        Y markers on the low / high levels."""
        src = _source(source)
        w = self.waveform(src, "NORM", 62500)
        rising = kind != "fall_90_10"
        pts = edge_points(w.t, w.v, rising)
        if pts is None or pts.get("t10") is None or pts.get("t90") is None:
            raise ScopeError(f"no complete {'rising' if rising else 'falling'} edge on screen for {src}")
        if kind == "swing":
            self.set_markers("MAN", x1=pts["t50"], x2=pts["t50"], y1=pts["low"], y2=pts["high"],
                             source1=src, source2=src)
        else:
            a, b = (pts["t10"], pts["t90"]) if rising else (pts["t90"], pts["t10"])
            self.set_markers("WAV", x1=a, x2=b, source1=src, source2=src)
        return {"computed": pts, "readback": self.markers_readback()}

    # --- data -------------------------------------------------------------
    def measure(self, item: str, source: str | int = "CHAN1", source2: str | int | None = None,
                check_live: bool = True) -> float:
        """check_live=False skips the WAIT guard (the caller already ran ensure_data())."""
        if check_live:
            self.ensure_data(f"measurement {item}")
        name = MEAS_ALIASES.get(item.upper(), item.upper())
        src = _source(source)
        if name in TWO_SOURCE:
            src = f"{src},{_source(source2 or 'CHAN2')}"
        val = float(self.query_checked(f":MEAS:{name}? {MEAS_PREFIX.get(name, '')}{src}", 5000))
        if abs(val) >= INVALID:
            raise ScopeError(f"measurement {item} on {src} invalid (no signal / out of range)")
        return val

    def clear_measurements(self) -> None:
        self.write(":MEAS:CLE")

    def screenshot(self, white: bool = True) -> bytes:
        """PNG of the screen. white=True uses Ink Saver (white background) for reports; the previous
        Ink Saver setting is restored afterwards."""
        old = self.query(":HARD:INKS?") == "1"
        if old != white:
            self.write(f":HARD:INKS {1 if white else 0}")
        try:
            return self.inst.query_binary_values(":DISP:DATA? PNG,COL", datatype="B", container=bytes)
        finally:
            if old != white:
                self.write(f":HARD:INKS {1 if old else 0}")

    def waveform(self, source: str | int = "CHAN1", mode: str = "NORM", max_points: int | None = None) -> Waveform:
        """NORM: screen-resolution data (default 1000 points, max 62500; works while running, refused while
        the trigger is armed without triggers because the query would block).
        RAW / MAX: acquisition memory, STOPS the scope first (up to 4 Mpts with MEMUP)."""
        src = _source(source)
        mode = mode.upper()
        if mode in ("RAW", "MAX"):
            self.stop()
        else:
            self.ensure_data("waveform")
        self.write(f":WAV:SOUR {src}")
        self.write(":WAV:FORM BYTE")
        self.write(":WAV:UNS 1")
        self.write(f":WAV:POIN:MODE {mode}")
        if mode == "NORM":
            self.write(f":WAV:POIN {int(max_points or 1000)}")
        else:
            self.write(f":WAV:POIN {int(max_points) if max_points else 'MAX'}")
        pre = [float(x) for x in self.query(":WAV:PRE?").split(",")]
        _fmt, _typ, _points, _cnt, xinc, xorig, xref, yinc, yorig, yref = pre
        old_timeout = self.inst.timeout
        self.inst.timeout = max(old_timeout, 60000)
        try:
            raw = self.inst.query_binary_values(":WAV:DATA?", datatype="B", container=np.array)
        finally:
            self.inst.timeout = old_timeout
        raw = np.asarray(raw, dtype=np.uint8)
        v = (raw.astype(np.float64) - yref) * yinc + yorig
        t = (np.arange(raw.size) - xref) * xinc + xorig
        return Waveform(src, mode, t, v, xinc, raw)


def _source(source: str | int) -> str:
    """Accept 1, "1", "chan1", "CHAN1", "MATH", "FUNC", "WMEM1", ... and return the SCPI source name."""
    src = str(source).upper()
    return f"CHAN{src}" if src.isdigit() else src


def _stamp() -> str:
    return time.strftime("%Y%m%d_%H%M%S")


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 1
    cmd, *args = argv
    with DSOX4000() as s:
        if cmd == "idn":
            print(s.idn())
        elif cmd == "status":
            print(json.dumps(s.status(), indent=2, ensure_ascii=False))
        elif cmd == "shot":
            white = not (len(args) > 1 and args[1].lower() == "black")
            out = Path(args[0]) if args and args[0] != "-" else CAPTURES / f"{_stamp()}_screen.png"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(s.screenshot(white))
            print(out)
        elif cmd == "wave":
            ch = args[0] if args else "CHAN1"
            mode = args[1] if len(args) > 1 else "NORM"
            maxp = int(args[2]) if len(args) > 2 else None
            w = s.waveform(ch, mode, maxp)
            path = w.save_csv(CAPTURES / f"{_stamp()}_{w.channel}_{w.mode}.csv")
            print(json.dumps({**w.stats(), "csv": str(path)}, indent=2))
        elif cmd == "meas":
            print(s.measure(args[0], args[1] if len(args) > 1 else "CHAN1", args[2] if len(args) > 2 else None))
        elif cmd == "demo":
            out = None if len(args) < 2 else args[1].lower() in ("on", "1", "true")
            print(json.dumps(s.demo(args[0] if args else None, out)))
        elif cmd == "mark":
            kind = args[0] if args else "rise_10_90"
            if kind == "off":
                s.set_markers("OFF")
                print("ok")
            else:
                print(json.dumps(s.auto_markers(kind, args[1] if len(args) > 1 else "CHAN1"), indent=2))
        elif cmd == "recover":
            s.recover()
            print("recovered:", s.idn(), s.run_state())
        elif cmd == "q":
            print(s.query_checked(args[0]))
        elif cmd == "w":
            s.write(args[0])
            print("ok")
        else:
            print(__doc__)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
