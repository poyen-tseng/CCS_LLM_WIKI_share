"""Local MCP server (stdio) exposing a RIGOL MSO5000 oscilloscope to Claude Code."""
from __future__ import annotations

import re
import sys
import threading
from pathlib import Path
from typing import Literal

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mcp.server.mcpserver import Image, MCPServer  # noqa: E402

from rigol import CAPTURES, MSO5000, ScopeError, _stamp  # noqa: E402

server = MCPServer(
    "scope",
    instructions=(
        "Controls a RIGOL MSO5104 oscilloscope (4 ch, 100 MHz) over LAN. "
        "Typical flow: scope_status -> adjust with scope_set_* or scope_autoscale -> "
        "scope_measure / scope_capture / scope_screenshot. Voltages are probe-corrected, so check the "
        "channel probe ratio. Waveform CSVs and screenshots are saved under the captures folder."
    ),
)

_lock = threading.Lock()
_scope: MSO5000 | None = None

# SCPI commands that can wipe settings, change networking, touch storage or firmware.
_DANGEROUS = re.compile(
    r"^\s*(\*RST|\*RCL|\*SAV|:?SYST(EM)?:(RES|SET|LAN|IP|UPD|UPGR|FIRM|POW|LOCK|KEY|OPT)|"
    r":?LAN:|:?SAVE:|:?LOAD:|:?REC(ALL)?:|:?(FILE|DISK|MMEM)|:?SOUR(CE)?\d?:)",
    re.IGNORECASE,
)


def _is_dangerous(command: str) -> bool:
    # check every ';'-separated part so ':RUN;*RST' can't slip through
    return any(_DANGEROUS.search(part) for part in command.split(";"))


def _get() -> MSO5000:
    global _scope
    if _scope is None:
        _scope = MSO5000()
    return _scope


def _call(fn):
    """Run fn(scope) under a lock; reconnect once if the socket went stale."""
    global _scope
    with _lock:
        try:
            return fn(_get())
        except ScopeError:
            raise
        except Exception:
            if _scope is not None:
                try:
                    _scope.close()
                except Exception:
                    pass
            _scope = None
            return fn(_get())


@server.tool()
def scope_idn() -> str:
    """Return the oscilloscope identification string (*IDN?)."""
    return _call(lambda s: s.idn())


@server.tool()
def scope_status() -> dict:
    """Return all channel, timebase, acquisition and trigger settings plus the trigger state."""
    return _call(lambda s: s.status())


@server.tool()
def scope_screenshot() -> list:
    """Capture the scope screen as a PNG image (also saved to the captures folder)."""
    png = _call(lambda s: s.screenshot())
    path = CAPTURES / f"{_stamp()}_screen.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(png)
    return [Image(data=png, format="png"), f"saved: {path}"]


@server.tool()
def scope_capture(
    channel: str = "CHAN1",
    mode: Literal["NORM", "RAW"] = "NORM",
    max_points: int | None = None,
) -> dict:
    """Download a waveform and save it as CSV (time_s, volt_V); returns summary stats and the CSV path.

    channel: CHAN1-CHAN4 (or 1-4), MATH1-MATH4.
    mode: NORM = the 1000 on-screen points (scope keeps running);
          RAW = full acquisition memory (STOPS the scope; use max_points to limit size;
                reading many millions of points takes a while).
    """
    w = _call(lambda s: s.waveform(channel, mode, max_points))
    path = w.save_csv(CAPTURES / f"{_stamp()}_{w.channel}_{w.mode}.csv")
    return {**w.stats(), "csv": str(path)}


@server.tool()
def scope_measure(items: list[str], channel: str = "CHAN1") -> dict:
    """Read automatic measurements from the scope, e.g. ["FREQ","VPP","VRMS","VAVG","PER",
    "RTIM","FTIM","PWID","NWID","PDUT","VMAX","VMIN","VTOP","VBASE","VAMP","OVER","PRES"].
    Invalid measurements (no signal) are reported as strings."""

    def run(s: MSO5000) -> dict:
        out = {}
        for item in items:
            try:
                out[item.upper()] = s.measure(item, channel)
            except ScopeError as e:
                out[item.upper()] = f"invalid: {e}"
        return out

    return _call(run)


@server.tool()
def scope_run_control(action: Literal["run", "stop", "single", "force"], wait_s: float = 0.0) -> str:
    """Start/stop acquisition. 'single' arms one trigger; with wait_s>0 it waits for the capture
    to complete. 'force' forces a trigger. Returns the trigger state (TD, WAIT, RUN, AUTO, STOP)."""

    def run(s: MSO5000) -> str:
        {"run": s.run, "stop": s.stop, "single": s.single, "force": s.force_trigger}[action]()
        if action == "single" and wait_s > 0:
            return s.wait_trigger(wait_s)
        return s.trigger_status()

    return _call(run)


@server.tool()
def scope_autoscale() -> dict:
    """Run AUTO (autoscale) and return the resulting settings."""
    return _call(lambda s: (s.autoscale(), s.status())[1])


@server.tool()
def scope_set_channel(
    channel: int,
    display: bool | None = None,
    scale_v_per_div: float | None = None,
    offset_v: float | None = None,
    coupling: Literal["DC", "AC", "GND"] | None = None,
    probe_ratio: float | None = None,
    bandwidth_limit: Literal["OFF", "20M"] | None = None,
) -> dict:
    """Configure an analog channel (1-4). Only the given parameters are changed."""

    def run(s: MSO5000) -> dict:
        s.set_channel(channel, display, scale_v_per_div, offset_v, coupling, probe_ratio, bandwidth_limit)
        return s.status()["channels"][f"CHAN{channel}"]

    return _call(run)


@server.tool()
def scope_set_timebase(scale_s_per_div: float | None = None, offset_s: float | None = None) -> dict:
    """Set horizontal scale (s/div) and/or trigger position offset (s)."""

    def run(s: MSO5000) -> dict:
        s.set_timebase(scale_s_per_div, offset_s)
        return s.status()["timebase"]

    return _call(run)


@server.tool()
def scope_set_trigger(
    source: str | None = None,
    level_v: float | None = None,
    slope: Literal["POS", "NEG", "RFAL"] | None = None,
    sweep: Literal["AUTO", "NORM", "SING"] | None = None,
) -> dict:
    """Configure the edge trigger. source: CHAN1-CHAN4, D0-D15, EXT, ACL."""

    def run(s: MSO5000) -> dict:
        s.set_trigger_edge(source, level_v, slope, sweep)
        return s.status()["trigger"]

    return _call(run)


@server.tool()
def scope_scpi(command: str, allow_dangerous: bool = False) -> str:
    """Send a raw SCPI command; if it ends with '?' the response is returned. Commands that reset the
    scope, change LAN/system settings, touch storage/firmware or drive the built-in generator are
    refused unless allow_dangerous=true (only set that when the user explicitly asked)."""
    if _is_dangerous(command) and not allow_dangerous:
        return f"refused: '{command}' is a potentially destructive command; ask the user first."

    def run(s: MSO5000) -> str:
        if command.strip().endswith("?"):
            return s.query(command)
        s.write(command)
        return "ok"

    return _call(run)


if __name__ == "__main__":
    server.run()
