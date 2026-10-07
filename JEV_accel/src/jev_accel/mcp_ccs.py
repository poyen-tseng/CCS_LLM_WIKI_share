"""Local MCP server (stdio) "jev-ccs": one-call build, flash and probe decisions for the F280049C.

Each tool runs deterministic rules first and asks Jev only when the rules are not decisive.
The debug session stays warm in ccs_daemon so load / halt / read PC do not pay a fresh DebugServer start.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Literal

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # allow running this file directly

from mcp.server.mcpserver import MCPServer  # noqa: E402

from jev_accel import tools_ccs  # noqa: E402

JevMode = Literal["auto", "always", "off"]
RunAction = Literal["run", "halt", "reset", "restart", "status", "read_reg", "read_mem", "write_mem"]

server = MCPServer(
    "jev-ccs",
    instructions=(
        "One call for CCS / F280049C instead of searching paths, re-reading gmake logs, or starting dss.bat. "
        "Call ccs_env first; it already lists gmake, dss.bat, the compiler, ccxml, .out, the XDS110 and who "
        "holds the probe. Build with ccs_build (it checks the .map). Load and run with ccs_load and "
        "ccs_run_control; do not write a new dss.bat script per step. Call ccs_release before another tool "
        "or the IDE uses the XDS110. If a subagent dies, read results/ccs_runs.jsonl instead of re-scanning "
        "terminals. Pass an external dss.bat log to ccs_dss_state."
    ),
)


@server.tool()
def ccs_env() -> dict:
    """Paths, XDS110 PnP, COM ports, probe owner (free / daemon / ide / dss_script), daemon status and
    each project's ccxml, .out and sources changed since the last build. Do not search the disk for these."""
    return tools_ccs.ccs_env()


@server.tool()
def ccs_build(project: str, clean: bool = False, warm_daemon: bool = True, jev_mode: JevMode = "auto") -> dict:
    """gmake the project's Debug folder, classify the log, and on success check the .map.
    result: missing_compiler, slow_path, include_path, syntax_error, undefined_symbol, memory_placement,
    stale_build, other_error, ok. A stale build (gmake said up to date, sources differ) is touched and rebuilt once."""
    return tools_ccs.ccs_build(project, clean, warm_daemon, jev_mode)


@server.tool()
def ccs_map_check(project: str, mode: Literal["flash", "ram"] | None = None) -> dict:
    """Parse Debug/<project>.map: entry, codestart, .TI.ramfunc load/run, unplaced sections, memory use.
    flash requires codestart at 0x80000 and ramfunc loaded in flash but run in RAM."""
    return tools_ccs.ccs_map_check(project, mode)


@server.tool()
def ccs_load(project: str | None = None, program: str | None = None, ccxml: str | None = None,
             run: bool = True, verify: bool = True, check: bool = True, jev_mode: JevMode = "auto") -> dict:
    """Reset, loadProgram and verify through the warm daemon, then optionally run. Returns PC and step times.
    Refuses when sources changed since the last build or the .map does not match the project mode.
    Give a project name, or program + ccxml."""
    return tools_ccs.ccs_load(project, program, ccxml, run, verify, check, jev_mode)


@server.tool()
def ccs_run_control(action: RunAction, names: list[str] | None = None, addr: str | None = None,
                    count: int = 1, values: list[str] | None = None, bits: int | None = None) -> dict:
    """run, halt, reset, restart, status, read_reg (default PC), read_mem or write_mem on the warm session.
    Halt and register reads are well under a second once the daemon is connected."""
    return tools_ccs.ccs_run_control(action, names, addr, count, values, bits)


@server.tool()
def ccs_release(shutdown: bool = False) -> dict:
    """Disconnect so dss.bat or the CCS IDE can use the XDS110. shutdown=true also stops the daemon;
    the next ccs_load pays for initScripting again."""
    return tools_ccs.ccs_release(shutdown)


@server.tool()
def ccs_verify(project: str, port: str | None = None, timeout_s: float = 120) -> dict:
    """Run the project's tools/verify_*.ps1 and return each CHECK: PASS/FAIL plus OVERALL.
    Release the probe first when the script needs the COM port."""
    return tools_ccs.ccs_verify(project, port, timeout_s)


@server.tool()
def ccs_project_drift(project: str, set_baseline: bool = False, jev_mode: JevMode = "auto") -> dict:
    """Compare Debug/makefile and subdir_rules.mk with the saved baseline (_FLASH, linker cmd, entry point,
    include paths, compiler). The first call stores the baseline. Only non-key option changes are shown to Jev."""
    return tools_ccs.ccs_project_drift(project, set_baseline, jev_mode)


@server.tool()
def ccs_dss_state(output_text: str | None = None, output_path: str | None = None,
                  probe_present: bool | None = None, jev_mode: JevMode = "auto") -> dict:
    """Classify an external dss.bat or scripting log: flash_ok, connect_ok, no_probe, probe_busy, target_power,
    connect_fail, flash_fail, run_fail, timeout, other_error. Error -260 while the XDS110 is still in PnP is
    probe_busy, not an unplugged probe."""
    return tools_ccs.ccs_dss_state(output_text, output_path, jev_mode, probe_present)


if __name__ == "__main__":
    server.run()
