"""Local MCP server (stdio) "jev-scope": one-call decisions for the GPIO lab workflow.

Each tool runs deterministic rules first and asks Jev only when the rules are not decisive.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Literal

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # allow running this file directly

from mcp.server.mcpserver import MCPServer  # noqa: E402

from jev_accel import tools  # noqa: E402

JevMode = Literal["auto", "always", "off"]

server = MCPServer(
    "jev-scope",
    instructions=(
        "Fast decision gates for the RIGOL MSO5104 + F280049C workflow. Before reading a scope screenshot, "
        "call jev_check_frame: only when ready=true take the screenshot (once). If it says next_fix, apply its "
        "scpi (or call again with apply=true). If a single shot is flat or never triggers, call "
        "jev_diagnose_capture before suspecting wiring. After gmake / edge_run.js, pass the output to "
        "jev_flash_state instead of re-reading the terminal. Never press MOFF blindly: use jev_menu_visible. "
        "jev_autoframe centers and scales a channel from measured VTOP/VBASE."
    ),
)


@server.tool()
def jev_check_frame(channel: str = "CHAN1", goal: str = "", notes: list[str] | None = None,
                    apply: bool = False, view: Literal["edge", "delay"] = "edge",
                    jev_mode: JevMode = "auto") -> dict:
    """A: decide whether the current frame is report-ready (centered, unclipped, trigger at 50%, probe 10x,
    menu hidden). Returns ready, next_fix (diagnose, fix_probe, hide_menu, fix_offset, change_vdiv,
    move_trigger, shift_timebase, clear_meas, rescreen, ok), the SCPI fix, and the measured metrics.
    notes: things you noticed that SCPI cannot see, e.g. "RTIM overlay visible". apply=true sends the fix.
    view=delay when the frame shows two events (e.g. GPIO0 edge and the delayed GPIO6 edge)."""
    return tools.check_frame(channel, jev_mode, goal, notes, apply=apply, view=view)


@server.tool()
def jev_diagnose_capture(channel: str = "CHAN1", trigger_level_set: float | None = None, pc: str | None = None,
                         build_stale: bool | None = None, want_single: bool = True,
                         jev_mode: JevMode = "auto") -> dict:
    """B: root cause of a flat / untriggered single shot: pc_in_bootrom, stale_build, probe_ratio,
    trig_level_out_of_range, sweep_mode, or wiring (only when nothing else fits). Pass the trigger level you
    requested (to detect clamping) and the PC from the flash output if you have them."""
    return tools.diagnose(channel, want_single, trigger_level_set, pc, build_stale, jev_mode)


@server.tool()
def jev_flash_state(output_text: str | None = None, output_path: str | None = None,
                    expected_min: float | None = None, expected_max: float | None = None,
                    measured: float | None = None, expectation: str = "", jev_mode: JevMode = "auto") -> dict:
    """C: classify gmake / run.bat edge_run.js / ccs-debug output: ok_running, waiting_go, at_bootrom, retry,
    fallback_dss, rebuild_needed, plus the next step. Give expected_min/max and measured (e.g. delay in s) to
    catch a stale build, or a free-text expectation for Jev to judge."""
    rng = (expected_min, expected_max) if expected_min is not None and expected_max is not None else None
    return tools.flash_state(output_text, output_path, rng, measured, expectation, jev_mode)


@server.tool()
def jev_menu_visible(hide: bool = False, jev_mode: JevMode = "auto") -> dict:
    """D: is the scope side menu open? hide=true presses MOFF only when it is open (MOFF toggles)."""
    return tools.menu(hide, jev_mode)


@server.tool()
def jev_autoframe(channel: str = "CHAN1", mode: Literal["edge", "delay"] = "edge", delay_s: float | None = None,
                  apply: bool = True) -> dict:
    """E: set probe 10x, V/div, offset, trigger level (50% of VBASE/VTOP) and timebase from live measurements.
    mode=edge: rise time spans >= 2 div (floor 5 ns/div). mode=delay: delay_s fits in 8 div, centered."""
    return tools.autoframe_apply(channel, mode, delay_s, apply)


if __name__ == "__main__":
    server.run()
