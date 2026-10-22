"""Local MCP server (stdio) exposing a Tektronix TDS2014B oscilloscope (USB) to Claude Code."""
from __future__ import annotations

import re
import sys
import threading
import time
from pathlib import Path
from typing import Literal

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pyvisa  # noqa: E402
from mcp.server.mcpserver import Image, MCPServer  # noqa: E402
from mcp.server.mcpserver.exceptions import ToolError  # noqa: E402

from tek import CAPTURES, TDS2000B, ScopeError, _resolve_resource, _stamp  # noqa: E402

server = MCPServer(
    "tek",
    instructions=(
        "Controls a Tektronix TDS2014B oscilloscope (4 ch, 100 MHz, 2500-point records) over USB (USBTMC). "
        "Typical flow: tek_status -> adjust with tek_set_* or tek_autoscale -> tek_measure / tek_capture / "
        "tek_screenshot. Channel position is in divisions (Tek convention); tek_set_channel also takes "
        "offset_v_center, the voltage at screen center. Voltages are probe-corrected. There is no function "
        "generator; the front-panel PROBE COMP terminal (5 V, 1 kHz square) is the self-test signal. "
        "Screenshots are white-background PNGs (Ink Saver) and are saved with waveform CSVs under the "
        "captures folder. The USB link is slow (each query takes milliseconds), so prefer one tek_status "
        "over many tek_scpi queries."
    ),
)

_lock = threading.Lock()
_scope: TDS2000B | None = None

# commands that reset the scope, recall / save setups, calibrate, lock the panel or touch storage
_DANGEROUS = re.compile(
    r"^\s*(\*RST|\*RCL|\*SAV|\*PSC|\*CAL|FAC(TORY)?|REC(ALL)?|SAV(E)?\b|SAVE:|CAL(IBRATE)?|DIAG|LOC(K)?|"
    r"UNL(OCK)?|FILES(YSTEM)?|HARDC(OPY)?|SET(UP)?\s|SYST(EM)?:|RS232|USBTMC|DATE|TIME)",
    re.IGNORECASE,
)


def _is_dangerous(command: str) -> bool:
    # check every ';'-separated part so 'ACQ:STATE RUN;*RST' can't slip through; plain queries are harmless
    return any(_DANGEROUS.search(p) and not p.strip().endswith("?") for p in command.split(";"))


def _get() -> TDS2000B:
    global _scope
    if _scope is None:
        _scope = TDS2000B()
    return _scope


def _call(fn):
    """Run fn(scope) under a lock; reconnect once if the USB session went stale. A timeout means a reply
    is stuck (or the query is unsupported): clear the device and report it instead of retrying the same
    call. Expected failures become ToolError so the model sees the reason."""
    global _scope
    with _lock:
        try:
            return fn(_get())
        except ScopeError as e:
            raise ToolError(str(e)) from None
        except pyvisa.errors.VisaIOError as e:
            if e.error_code == pyvisa.constants.StatusCode.error_timeout and _scope is not None:
                t0 = time.perf_counter()
                try:
                    _scope.recover()
                except Exception:
                    pass  # scope gone: fall through to the reconnect below
                else:
                    raise ToolError(
                        "the scope did not answer in time (an unsupported query costs ~5 s more while pyvisa-py "
                        "aborts the USB read); recovered by reopening the USB session in "
                        f"{(time.perf_counter() - t0) * 1000:.0f} ms. Check tek_status before retrying.") from None
        except Exception:
            pass
        if _scope is not None:  # stale session or no connection yet: reconnect once
            try:
                _scope.close()
            except Exception:
                pass
        _scope = None
        try:
            return fn(_get())
        except ScopeError as e:
            raise ToolError(str(e)) from None
        except Exception as e:
            raise ToolError(f"cannot reach the TDS2014B at {_resolve_resource(None)}: {type(e).__name__}: {e}") from None


@server.tool()
def tek_idn() -> str:
    """Return the identification string (*IDN?)."""
    return _call(lambda s: s.idn())


@server.tool()
def tek_status() -> dict:
    """Return channel, timebase, acquisition and trigger settings plus the run state
    (TD = triggering, WAIT = armed in NORM mode without triggers, AUTO = auto mode, STOP)."""
    return _call(lambda s: s.status())


@server.tool()
def tek_screenshot(white_background: bool = True) -> list:
    """Capture the screen as a PNG (white background by default, for reports; also saved to captures).
    white_background=false gives the normal black screen. Takes a few seconds over USB."""
    png = _call(lambda s: s.screenshot(white_background))
    path = CAPTURES / f"{_stamp()}_screen.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(png)
    return [Image(data=png, format="png"), f"saved: {path}"]


@server.tool()
def tek_capture(channel: str = "CH1") -> dict:
    """Download the 2500-point waveform record and save it as CSV (time_s, volt_V); returns summary stats
    and the CSV path. channel: CH1-CH4 (or 1-4), MATH, REFA-REFD; the channel must be displayed.
    The scope keeps running; stop it first for a record that matches a frozen screen."""
    w = _call(lambda s: s.waveform(channel))
    path = w.save_csv(CAPTURES / f"{_stamp()}_{w.channel}.csv")
    return {**w.stats(), "csv": str(path)}


@server.tool()
def tek_measure(items: list[str], channel: str = "CH1") -> dict:
    """Automatic measurements (immediate, not shown on screen; about 1 s each). RIGOL names work:
    ["FREQ","PER","VPP","VRMS","VAVG","VMAX","VMIN","RTIM","FTIM","PWID","NWID","PDUT","NDUT"], native Tek
    types (PK2, RMS, CRMS, MEAN, ...) too. PDUT / NDUT are computed from width / period (the firmware has
    no duty, amplitude, overshoot, delay or phase). Invalid measurements (no signal) are reported as
    strings; scope warnings such as "Low signal amplitude" (trace too small: raise the V/div gain) are
    listed under "warnings" next to a value that is still returned."""

    def run(s: TDS2000B) -> dict:
        s.ensure_data("tek_measure")
        out, warnings = {}, {}
        for item in items:
            try:
                out[item.upper()] = s.measure(item, channel, check_live=False)
            except ScopeError as e:
                out[item.upper()] = f"invalid: {e}"
            if s.warnings:
                warnings[item.upper()] = "; ".join(s.warnings)
        if warnings:
            out["warnings"] = warnings
        return out

    return _call(run)


@server.tool()
def tek_run_control(action: Literal["run", "stop", "single", "force"], wait_s: float = 0.0) -> dict:
    """Start/stop acquisition. 'single' arms one sequence; with wait_s>0 it waits for the capture to
    complete (STOP) and otherwise reports the current state. 'force' forces a trigger. run_state uses the
    RIGOL words: TD (triggering), WAIT (armed, no trigger), AUTO (auto mode), STOP."""

    def run(s: TDS2000B) -> dict:
        if action == "single":
            n0 = s.num_acq()
            s.single()
            state = s.wait_trigger(wait_s) if wait_s > 0 else ("WAIT" if s.acquiring() else "STOP")
            return {"run_state": state, "triggered": state == "STOP" and s.num_acq() != n0}
        n0 = s.num_acq()
        {"run": s.run, "stop": s.stop, "force": s.force_trigger}[action]()
        state = s.run_state()
        # a forced trigger acquires one record, then NORM mode waits again: count it from ACQ:NUMACQ?
        return {"run_state": state, "triggered": state == "TD" or (action == "force" and s.num_acq() != n0)}

    return _call(run)


@server.tool()
def tek_autoscale() -> dict:
    """Run AUTOSET and return the resulting settings."""
    return _call(lambda s: (s.autoscale(), s.status())[1])


@server.tool()
def tek_set_channel(
    channel: int,
    display: bool | None = None,
    scale_v_per_div: float | None = None,
    position_div: float | None = None,
    offset_v_center: float | None = None,
    coupling: Literal["DC", "AC", "GND"] | None = None,
    probe_ratio: Literal[1, 10, 20, 50, 100, 500, 1000] | None = None,
    bandwidth_limit_20mhz: bool | None = None,
    invert: bool | None = None,
    units: Literal["V", "A"] | None = None,
) -> dict:
    """Configure an analog channel (1-4). Only the given parameters are changed.
    position_div moves the trace in divisions (+ = up). offset_v_center instead sets the voltage shown at the
    center line (to center a 0-3.3 V signal use +1.65); it is converted to divisions with the new scale.
    Scales follow the 1-2-5 sequence (2 mV to 5 V/div at 1x probe). units "A" is for current probes; a
    voltage probe needs units "V" (tek_status shows a channel left in "A")."""

    def run(s: TDS2000B) -> dict:
        s.set_channel(channel, display, scale_v_per_div, position_div, offset_v_center, coupling,
                      probe_ratio, bandwidth_limit_20mhz, invert, units)
        return s.channel_settings(channel)

    return _call(run)


@server.tool()
def tek_set_timebase(scale_s_per_div: float | None = None, position_s: float | None = None) -> dict:
    """Set horizontal scale (s/div, 1-2.5-5 sequence, 5 ns to 50 s) and the trigger position (s; the time
    of the screen center relative to the trigger)."""

    def run(s: TDS2000B) -> dict:
        s.set_timebase(scale_s_per_div, position_s)
        return s.timebase_settings()

    return _call(run)


@server.tool()
def tek_set_trigger(
    trigger_type: Literal["EDGE", "PULSE"] = "EDGE",
    source: str | None = None,
    level_v: float | None = None,
    slope: Literal["RIS", "FALL"] | None = None,
    mode: Literal["AUTO", "NORM"] | None = None,
    coupling: Literal["DC", "AC", "HFR", "LFR", "NOISE"] | None = None,
    holdoff_s: float | None = None,
    pulse_polarity: Literal["POS", "NEG"] | None = None,
    pulse_when: Literal["EQ", "NOTE", "INS", "OUT"] | None = None,
    pulse_width_s: float | None = None,
) -> dict:
    """Configure the trigger. EDGE: source (CH1-4, EXT, EXT5, LINE), level, slope, coupling.
    PULSE (pulse width, the GLITCH equivalent): pulse_when compares the pulse with pulse_width_s:
    EQ / NOTE = within / outside +-5 %, INS = narrower, OUT = wider; pulse_polarity POS = positive pulses.
    mode NORM waits for a real trigger (use it for single shots); AUTO free-runs."""

    def run(s: TDS2000B) -> dict:
        if trigger_type == "PULSE":
            s.set_trigger_pulse(source, level_v, pulse_polarity, pulse_when, pulse_width_s, mode, holdoff_s)
        else:
            s.set_trigger_edge(source, level_v, slope, mode, coupling, holdoff_s)
        return s.trigger_settings()

    return _call(run)


@server.tool()
def tek_scpi(command: str, allow_dangerous: bool = False) -> str:
    """Send a raw SCPI command; if it ends with '?' the response is returned. Commands that reset the
    scope, recall/save setups, calibrate, lock the front panel, print hardcopies or touch storage are
    refused unless allow_dangerous=true (only set that when the user explicitly asked). An unsupported
    query gets no reply; it is reported with the event queue after 2 s."""
    if _is_dangerous(command) and not allow_dangerous:
        return f"refused: '{command}' is a potentially destructive command; ask the user first."

    def run(s: TDS2000B) -> str:
        try:
            if command.strip().endswith("?"):
                return s.query_checked(command)
            s.write(command)
            return "ok"
        except ScopeError as e:
            return f"error: {e}"

    return _call(run)


if __name__ == "__main__":
    server.run()
