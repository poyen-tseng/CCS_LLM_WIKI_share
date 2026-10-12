"""Local MCP server (stdio) exposing a Keysight InfiniiVision DSO-X 4034A oscilloscope to Claude Code."""
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

from keysight import CAPTURES, DEMO_FUNCTIONS, DSOX4000, ScopeError, _resolve_resource, _stamp  # noqa: E402

server = MCPServer(
    "keysight",
    instructions=(
        "Controls a Keysight (IDN: Agilent) DSO-X 4034A oscilloscope (4 ch, 350 MHz) over LAN at 192.168.137.60. "
        "Typical flow: ks_status -> adjust with ks_set_* or ks_autoscale -> ks_measure / ks_markers / "
        "ks_capture / ks_screenshot. Channel offset is the voltage at screen CENTER (opposite sign to the RIGOL). "
        "Voltages are probe-corrected. There is no WaveGen; ks_demo drives the EDK training signals on the "
        "Demo 1 / Demo 2 terminals for self-tests. Screenshots are white-background PNGs (Ink Saver) and are "
        "saved with waveform CSVs under the captures folder. An unsupported query gets no reply; ks_scpi reports "
        "it with the error queue instead of hanging."
    ),
)

_lock = threading.Lock()
_scope: DSOX4000 | None = None

# commands that reset the scope, change LAN/system settings, touch storage or restore setups
_DANGEROUS = re.compile(
    r"^\s*(\*RST|\*RCL|\*SAV|:?SYST(EM)?:(PRES|LOCK|SET|DATE|TIME|PERS|SEC|LAN)|:?SAVE|:?REC(ALL)?|"
    r":?DISK|:?LAN|:?WGEN|:?HARD(COPY)?:STAR|:?SYST(EM)?:MENU)",
    re.IGNORECASE,
)


def _is_dangerous(command: str) -> bool:
    # check every ';'-separated part so ':RUN;*RST' can't slip through; plain queries are harmless
    return any(_DANGEROUS.search(p) and not p.strip().endswith("?") for p in command.split(";"))


def _get() -> DSOX4000:
    global _scope
    if _scope is None:
        _scope = DSOX4000()
    return _scope


def _call(fn):
    """Run fn(scope) under a lock; reconnect once if the socket went stale. A timeout means the scope may be
    blocked on a query waiting for a trigger: unblock it (device clear + forced trigger) and report it
    instead of retrying the same call. Expected failures become ToolError so the model sees the reason
    (any other exception reaches the client only as "Error executing tool")."""
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
                        "the scope did not answer (a waveform or measurement query blocks while the trigger waits); "
                        f"recovered with a VXI-11 device clear and a forced trigger in "
                        f"{(time.perf_counter() - t0) * 1000:.0f} ms. "
                        "Check ks_status run_state and the trigger level before retrying.") from None
        except Exception:
            pass
        if _scope is not None:  # stale socket or no connection yet: reconnect once
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
            raise ToolError(f"cannot reach the Keysight at {_resolve_resource(None)}: {type(e).__name__}: {e}") from None


@server.tool()
def ks_idn() -> str:
    """Return the identification string (*IDN?) and the installed options."""
    return _call(lambda s: f"{s.idn()}  options: {', '.join(s.options())}")


@server.tool()
def ks_status() -> dict:
    """Return channel, timebase, acquisition, trigger, demo and marker settings plus the run state
    (RUN, WAIT = armed and waiting for a trigger, STOP)."""
    return _call(lambda s: s.status())


@server.tool()
def ks_screenshot(white_background: bool = True) -> list:
    """Capture the screen as a PNG (white background by default, for reports; also saved to captures).
    white_background=false gives the normal black screen."""
    png = _call(lambda s: s.screenshot(white_background))
    path = CAPTURES / f"{_stamp()}_screen.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(png)
    return [Image(data=png, format="png"), f"saved: {path}"]


@server.tool()
def ks_capture(
    channel: str = "CHAN1",
    mode: Literal["NORM", "RAW", "MAX"] = "NORM",
    max_points: int | None = None,
) -> dict:
    """Download a waveform and save it as CSV (time_s, volt_V); returns summary stats and the CSV path.

    channel: CHAN1-CHAN4 (or 1-4), MATH, FUNC, WMEM1/2.
    mode: NORM = screen-resolution data (default 1000 points, up to 62500; scope keeps running);
          RAW / MAX = acquisition memory (STOPS the scope; up to 4 Mpts; use max_points to limit size).
    """
    w = _call(lambda s: s.waveform(channel, mode, max_points))
    path = w.save_csv(CAPTURES / f"{_stamp()}_{w.channel}_{w.mode}.csv")
    return {**w.stats(), "csv": str(path)}


@server.tool()
def ks_measure(items: list[str], channel: str = "CHAN1", channel2: str = "CHAN2",
               clear_after: bool = False) -> dict:
    """Automatic measurements. RIGOL names work: ["FREQ","PER","VPP","VRMS","VAVG","VMAX","VMIN","VTOP",
    "VBASE","VAMP","RTIM","FTIM","PWID","NWID","PDUT","NDUT","OVER","PRES"], native Keysight headers too.
    "DEL" (delay) and "PHAS" (phase) are measured from channel to channel2.
    Invalid measurements (no signal) are reported as strings. clear_after removes the measurement
    readouts the queries leave in the side bar."""

    def run(s: DSOX4000) -> dict:
        s.ensure_data("ks_measure")
        out = {}
        for item in items:
            try:
                out[item.upper()] = s.measure(item, channel, channel2, check_live=False)
            except ScopeError as e:
                out[item.upper()] = f"invalid: {e}"
        if clear_after:
            s.clear_measurements()
        return out

    return _call(run)


@server.tool()
def ks_run_control(action: Literal["run", "stop", "single", "force"], wait_s: float = 0.0) -> dict:
    """Start/stop acquisition. 'single' arms one trigger; with wait_s>0 it waits for the capture to
    complete (STOP) and otherwise reports WAIT. 'force' forces a trigger. run_state uses the RIGOL words:
    TD (triggering), WAIT (armed, no trigger), AUTO (auto sweep without triggers), STOP."""

    def run(s: DSOX4000) -> dict:
        if action == "single":
            s.triggered_since_last_read()  # clear the trigger event latch
            s.single()
            state = s.wait_trigger(wait_s) if wait_s > 0 else s.run_bits()
            return {"run_state": state, "triggered": s.triggered_since_last_read()}
        {"run": s.run, "stop": s.stop, "force": s.force_trigger}[action]()
        state = s.run_state()
        return {"run_state": state, "triggered": state == "TD"}

    return _call(run)


@server.tool()
def ks_autoscale() -> dict:
    """Run AUToscale and return the resulting settings."""
    return _call(lambda s: (s.autoscale(), s.status())[1])


@server.tool()
def ks_set_channel(
    channel: int,
    display: bool | None = None,
    scale_v_per_div: float | None = None,
    offset_v_center: float | None = None,
    coupling: Literal["DC", "AC"] | None = None,
    probe_ratio: float | None = None,
    bandwidth_limit_25mhz: bool | None = None,
    impedance: Literal["ONEM", "FIFT"] | None = None,
    vernier: bool | None = None,
) -> dict:
    """Configure an analog channel (1-4). Only the given parameters are changed.
    offset_v_center is the voltage shown at the center line (to center a 0-3.3 V signal use +1.65).
    vernier=true allows fine V/div values such as 0.6."""

    def run(s: DSOX4000) -> dict:
        s.set_channel(channel, display, scale_v_per_div, offset_v_center, coupling, probe_ratio,
                      bandwidth_limit_25mhz, impedance, vernier)
        return s.status()["channels"][f"CHAN{channel}"]

    return _call(run)


@server.tool()
def ks_set_timebase(scale_s_per_div: float | None = None, position_s: float | None = None,
                    reference: Literal["LEFT", "CENT", "RIGH"] | None = None) -> dict:
    """Set horizontal scale (s/div), the trigger position (s from the trigger to the reference point)
    and the reference point on screen."""

    def run(s: DSOX4000) -> dict:
        s.set_timebase(scale_s_per_div, position_s, reference)
        return s.status()["timebase"]

    return _call(run)


@server.tool()
def ks_set_trigger(
    mode: Literal["EDGE", "GLITCH"] = "EDGE",
    source: str | None = None,
    level_v: float | None = None,
    slope: Literal["POS", "NEG", "EITH", "ALT"] | None = None,
    sweep: Literal["AUTO", "NORM"] | None = None,
    coupling: Literal["DC", "AC", "LFR"] | None = None,
    noise_reject: bool | None = None,
    holdoff_s: float | None = None,
    glitch_polarity: Literal["POS", "NEG"] | None = None,
    glitch_qualifier: Literal["LESS", "GRE", "RANG"] | None = None,
    glitch_width_s: float | None = None,
    glitch_width_max_s: float | None = None,
) -> dict:
    """Configure the trigger. EDGE: source (CHAN1-4, EXT, LINE), level, slope, coupling.
    GLITCH (pulse width): triggers on pulses narrower (LESS) / wider (GRE) than glitch_width_s, or between
    glitch_width_s and glitch_width_max_s (RANG); glitch_polarity POS = positive pulses.
    sweep NORM waits for a real trigger (use it for single shots); AUTO free-runs."""

    def run(s: DSOX4000) -> dict:
        if mode == "GLITCH":
            s.set_trigger_glitch(source, level_v, glitch_polarity, glitch_qualifier, glitch_width_s,
                                 glitch_width_max_s, sweep, noise_reject, holdoff_s)
        else:
            s.set_trigger_edge(source, level_v, slope, sweep, coupling, noise_reject, holdoff_s)
        return s.trigger_settings()

    return _call(run)


@server.tool()
def ks_markers(
    auto: Literal["rise_10_90", "fall_90_10", "swing"] | None = None,
    mode: Literal["MAN", "WAV", "MEAS", "OFF"] | None = None,
    channel: str = "CHAN1",
    x1_s: float | None = None,
    x2_s: float | None = None,
    y1_v: float | None = None,
    y2_v: float | None = None,
) -> dict:
    """Cursors (markers). auto computes positions from the on-screen waveform of `channel`:
    rise_10_90 / fall_90_10 put waveform-tracking X markers on the 10 % and 90 % points of the edge nearest
    the trigger; swing puts Y markers on the low and high levels and X at the 50 % point.
    Without auto, set mode and positions directly (MAN = free, WAV = Y follows the waveform, OFF = hide).
    Returns X1, X2, dX, 1/dX, Y1, Y2, dY as read back from the scope."""

    def run(s: DSOX4000) -> dict:
        if auto:
            return s.auto_markers(auto, channel)
        s.set_markers(mode, x1_s, x2_s, y1_v, y2_v, channel if mode not in (None, "OFF") else None,
                      channel if mode not in (None, "OFF") else None)
        return {"readback": s.markers_readback()}

    return _call(run)


DemoFunction = Literal[DEMO_FUNCTIONS]  # type: ignore[valid-type]


@server.tool()
def ks_demo(function: DemoFunction | None = None, output: bool | None = None) -> dict:
    """Built-in training signals on the front-panel Demo 1 / Demo 2 terminals (self-test source; this scope
    has no WaveGen). Wire CH1 probe -> Demo 1, CH2 probe -> Demo 2.
    Useful functions: CLK (clean ~3.6 MHz clock on Demo 1), GLIT (clock with occasional glitch, for the
    GLITCH trigger), RUNT, PHAS (two phase-shifted sines on Demo 1 and 2, for DEL/PHAS), SING (single-shot
    burst), BURS, SIN, NOIS, RING, AM, TRAN, SHOL. The scope shows a demo-mode banner while output is on."""
    return _call(lambda s: s.demo(function, output))


@server.tool()
def ks_scpi(command: str, allow_dangerous: bool = False) -> str:
    """Send a raw SCPI command; if it ends with '?' the response is returned. Commands that reset the
    scope, recall/save setups, change LAN/system settings or touch storage are refused unless
    allow_dangerous=true (only set that when the user explicitly asked). An unsupported query never gets a
    reply; it is reported with the error queue after 2 s."""
    if _is_dangerous(command) and not allow_dangerous:
        return f"refused: '{command}' is a potentially destructive command; ask the user first."

    def run(s: DSOX4000) -> str:
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
