"""Local MCP server (stdio) exposing a Tektronix MSO2014 oscilloscope (USB, analog channels) to Claude Code."""
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

from mso import CAPTURES, MSO2000, ScopeError, _resolve_resource, _stamp  # noqa: E402

server = MCPServer(
    "mso",
    instructions=(
        "Controls a Tektronix MSO2014 mixed-signal oscilloscope (4 analog ch, 100 MHz, 125 k / 1 M point "
        "records) over USB (USBTMC); the 16 digital channels are not handled. Typical flow: mso_status -> "
        "adjust with mso_set_* or mso_autoscale -> mso_measure / mso_capture / mso_screenshot. "
        "mso_set_channel offset_v_center puts that voltage at the center line (CH<n>:OFFSet). Voltages are "
        "probe-corrected: the probes have no ID pin, so check each channel's probe ratio in mso_status. "
        "There is no function generator; the front-panel PROBE COMP terminal (about 5 V, 1 kHz square) is "
        "the self-test signal. Screenshots are white-background PNGs over USB; they and waveform CSVs are "
        "saved under the captures folder. Never send AUTOSET through mso_scpi: a query "
        "that times out while it runs wedges the USB link until the cable is replugged."
    ),
)

_lock = threading.Lock()
_scope: MSO2000 | None = None

# commands that reset the scope, recall / save setups, calibrate, lock the panel or touch storage
_DANGEROUS = re.compile(
    r"^\s*(\*RST|\*RCL|\*SAV|\*PSC|\*CAL|FAC(TORY)?|REC(ALL)?|SAV(E)?\b|SAVE:|CAL(IBRATE)?|DIAG|LOC(K)?|"
    r"UNL(OCK)?|FILES(YSTEM)?|HARDC(OPY)?|SET(UP)?\s|SYST(EM)?:|USBD(EVICE)?|ETHER|DATE|TIME|"
    r"PASSW|TOTALU|AUXO)",
    re.IGNORECASE,
)
_AUTOSET = re.compile(r"^\s*AUTOS", re.IGNORECASE)


def _is_dangerous(command: str) -> bool:
    # check every ';'-separated part so 'ACQ:STATE RUN;*RST' can't slip through; plain queries are harmless
    return any(_DANGEROUS.search(p) and not p.strip().endswith("?") for p in command.split(";"))


def _get() -> MSO2000:
    global _scope
    if _scope is None:
        _scope = MSO2000()
    return _scope


def _call(fn):
    """Run fn(scope) under a lock; reconnect once if the USB session went stale. A timeout means a reply
    is stuck (or the query is unsupported): reopen the session and report it instead of retrying the same
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
                    _scope.idn()
                except Exception:
                    pass  # scope gone or link wedged: fall through to the reconnect below
                else:
                    raise ToolError(
                        "the scope did not answer in time; recovered by reopening the USB session in "
                        f"{(time.perf_counter() - t0) * 1000:.0f} ms. Check mso_status before retrying.") from None
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
            raise ToolError(
                f"cannot reach the MSO2014 at {_resolve_resource(None)}: {type(e).__name__}: {e}. If the "
                "device is listed but every call times out, the USB link is wedged: ask the user to unplug "
                "and replug the scope's USB cable.") from None


@server.tool()
def mso_idn() -> str:
    """Return the identification string (*IDN?)."""
    return _call(lambda s: s.idn())


@server.tool()
def mso_status() -> dict:
    """Return channel (incl. probe ratio and units), timebase, acquisition and trigger settings plus the
    run state (TD = triggering, WAIT = armed in NORM mode without triggers, AUTO = auto mode, STOP)."""
    return _call(lambda s: s.status())


@server.tool()
def mso_screenshot(white_background: bool = True) -> list:
    """Capture the screen as a PNG over USB (480 x 234, about 2.5 s; white background by default, for
    reports; also saved to captures). white_background=false gives the normal black screen."""
    png = _call(lambda s: s.screenshot(white_background))
    path = CAPTURES / f"{_stamp()}_screen.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(png)
    return [Image(data=png, format="png"), f"saved: {path}"]


@server.tool()
def mso_capture(
    channel: str = "CH1",
    mode: Literal["SCREEN", "FULL"] = "SCREEN",
    max_points: int | None = None,
) -> dict:
    """Download a waveform and save it as CSV (time_s, volt_V); returns summary stats and the CSV path.
    channel: CH1-CH4 (or 1-4), MATH, REF1/REF2; the channel must be displayed.
    mode: SCREEN = reduced record (about 5000 points); FULL = the whole record (125 k or 1 M points,
    about 0.5 s per 125 k), max_points keeps only the first max_points.
    The scope keeps running; stop it first for a record that matches a frozen screen."""
    w = _call(lambda s: s.waveform(channel, mode, max_points))
    path = w.save_csv(CAPTURES / f"{_stamp()}_{w.channel}_{w.mode}.csv")
    return {**w.stats(), "csv": str(path)}


@server.tool()
def mso_measure(items: list[str], channel: str = "CH1", channel2: str = "CH2") -> dict:
    """Automatic measurements (immediate, not shown on screen; about 60-100 ms each). RIGOL names work:
    ["FREQ","PER","VPP","VRMS","VAVG","VMAX","VMIN","VTOP","VBASE","VAMP","RTIM","FTIM","PWID","NWID",
    "PDUT","NDUT","OVER","DEL","PHAS"], native Tek types (PK2P, AMP, HIGH, LOW, POV, NOV, CRMS, AREA,
    PEDGECOUNT, ...) too. "DEL" (delay) and "PHAS" (phase) are measured from channel to channel2.
    Invalid measurements (no signal) are reported as strings; scope warnings such as "Low signal amplitude"
    (trace too small: raise the V/div gain) are listed under "warnings" next to a value that is still
    returned."""

    def run(s: MSO2000) -> dict:
        s.ensure_data("mso_measure")
        out, warnings = {}, {}
        for item in items:
            try:
                out[item.upper()] = s.measure(item, channel, channel2, check_live=False)
            except ScopeError as e:
                out[item.upper()] = f"invalid: {e}"
            if s.warnings:
                warnings[item.upper()] = "; ".join(s.warnings)
        if warnings:
            out["warnings"] = warnings
        return out

    return _call(run)


@server.tool()
def mso_run_control(action: Literal["run", "stop", "single", "force"], wait_s: float = 0.0) -> dict:
    """Start/stop acquisition. 'single' arms one sequence; with wait_s>0 it waits for the capture to
    complete (STOP) and otherwise reports the current state. 'force' forces a trigger. run_state uses the
    RIGOL words: TD (triggering), WAIT (armed, no trigger), AUTO (auto mode), STOP."""

    def run(s: MSO2000) -> dict:
        if action == "single":
            n0 = s.num_acq()
            s.single()
            state = s.wait_trigger(wait_s) if wait_s > 0 else ("WAIT" if s.acquiring() else "STOP")
            return {"run_state": state, "triggered": state == "STOP" and s.num_acq() != n0}
        n0 = s.num_acq()
        {"run": s.run, "stop": s.stop, "force": s.force_trigger}[action]()
        if action == "run":
            s.settle()
        state = s.run_state()
        # a forced trigger acquires one record, then NORM mode waits again: count it from ACQ:NUMACQ?
        return {"run_state": state, "triggered": state == "TD" or (action == "force" and s.num_acq() != n0)}

    return _call(run)


@server.tool()
def mso_autoscale() -> dict:
    """Run AUTOSET (several seconds; the scope ignores USB meanwhile) and return the resulting settings.
    Autoset stacks the displayed channels at coarse V/div; set the gain afterwards for accurate values."""
    return _call(lambda s: (s.autoscale(), s.status())[1])


@server.tool()
def mso_set_channel(
    channel: int,
    display: bool | None = None,
    scale_v_per_div: float | None = None,
    position_div: float | None = None,
    offset_v_center: float | None = None,
    coupling: Literal["DC", "AC", "GND"] | None = None,
    probe_ratio: float | None = None,
    bandwidth_limit_20mhz: bool | None = None,
    invert: bool | None = None,
    units: Literal["V", "A"] | None = None,
) -> dict:
    """Configure an analog channel (1-4). Only the given parameters are changed.
    offset_v_center puts that voltage at the center line (CH<n>:OFFSet, position reset to 0 div; to center
    a 0-3.3 V signal use +1.65). position_div moves the trace in divisions (+ = up).
    probe_ratio is the attenuation (10 for a 10:1 probe); these probes are not detected automatically."""

    def run(s: MSO2000) -> dict:
        s.set_channel(channel, display, scale_v_per_div, position_div, offset_v_center, coupling,
                      probe_ratio, bandwidth_limit_20mhz, invert, units)
        s.settle()  # so the next measurement does not use an acquisition taken with the old setting
        return s.channel_settings(channel)

    return _call(run)


@server.tool()
def mso_set_timebase(
    scale_s_per_div: float | None = None,
    position_pct: float | None = None,
    delay_s: float | None = None,
    record_length: Literal[125000, 1000000] | None = None,
) -> dict:
    """Set the horizontal scale (s/div), where the trigger sits on screen (position_pct, 0-100 %, turns
    delay mode off) or the time from the trigger to the screen center (delay_s, turns delay mode on), and
    the record length (125 k or 1 M points)."""

    def run(s: MSO2000) -> dict:
        s.set_timebase(scale_s_per_div, position_pct, delay_s, record_length)
        s.settle()
        return s.timebase_settings()

    return _call(run)


@server.tool()
def mso_set_trigger(
    trigger_type: Literal["EDGE", "PULSE"] = "EDGE",
    source: str | None = None,
    level_v: float | None = None,
    slope: Literal["RIS", "FALL"] | None = None,
    mode: Literal["AUTO", "NORM"] | None = None,
    coupling: Literal["DC", "HFR", "LFR", "NOISE"] | None = None,
    holdoff_s: float | None = None,
    pulse_polarity: Literal["POS", "NEG"] | None = None,
    pulse_when: Literal["LESS", "MORE", "EQ", "UNEQ"] | None = None,
    pulse_width_s: float | None = None,
) -> dict:
    """Configure the trigger. EDGE: source (CH1-4, LINE), level, slope, coupling (no AC on this scope).
    PULSE (pulse width, the GLITCH equivalent): pulse_when LESS / MORE = narrower / wider than
    pulse_width_s, EQ / UNEQ = within / outside a tolerance around it; pulse_polarity POS = positive pulses.
    The level is stored per source channel. mode NORM waits for a real trigger (use it for single shots);
    AUTO free-runs."""

    def run(s: MSO2000) -> dict:
        if trigger_type == "PULSE":
            s.set_trigger_pulse(source, level_v, pulse_polarity, pulse_when, pulse_width_s, mode, holdoff_s)
        else:
            s.set_trigger_edge(source, level_v, slope, mode, coupling, holdoff_s)
        s.settle()
        return s.trigger_settings()

    return _call(run)


@server.tool()
def mso_scpi(command: str, allow_dangerous: bool = False) -> str:
    """Send a raw SCPI command; if it ends with '?' the response is returned. Commands that reset the
    scope, recall/save setups, calibrate, lock the front panel, print, touch storage or change USB / network
    settings are refused unless allow_dangerous=true (only set that when the user explicitly asked).
    AUTOSET is refused here (use mso_autoscale). An unsupported query gets no reply; it is reported with
    the event queue after 2 s."""
    if any(_AUTOSET.search(p) for p in command.split(";")):
        return "refused: use mso_autoscale; a short-timeout query while AUTOSET runs wedges the USB link."
    if _is_dangerous(command) and not allow_dangerous:
        return f"refused: '{command}' is a potentially destructive command; ask the user first."

    def run(s: MSO2000) -> str:
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
