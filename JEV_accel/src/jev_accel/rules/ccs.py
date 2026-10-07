"""G: deterministic CCS facts: linker .map check, DSS / scripting output state, verify-script result,
who owns the XDS110, and build-file drift after the IDE regenerates a project.

Source of each rule: the Cursor sessions of 2026-10-06 (GPIO-EX1 f5de122c / 88daf93e / dbb394dd / 0c9d6c9f)
where these were checked by hand with Select-String, Get-Process and file diffs.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

FLASH_MIN = 0x80000   # F28004x flash bank 0 starts here; BEGIN (codestart) for boot-to-flash
APP_MAX = 0x3F0000    # boot ROM and above


# --- .map --------------------------------------------------------------------------------------
_ENTRY = re.compile(r'ENTRY POINT SYMBOL: "(\w+)"\s+address: ([0-9a-fA-F]+)')
_MEM = re.compile(r"^\s{2}(\w+)\s+([0-9a-f]{8})\s+([0-9a-f]{8})\s+([0-9a-f]{8})\s+([0-9a-f]{8})\s+\w+", re.M)
_SECTION_HDR = re.compile(r"^(?P<name>[.\w$]+)(?:[ \t]*\n\*)?[ \t]+\d+[ \t]+(?P<load>[0-9a-f]{8})[ \t]+(?P<size>[0-9a-f]{8})"
                          r"(?:[ \t]+(?:RUN ADDR = (?P<run>[0-9a-f]{8})|UNINITIALIZED))?", re.M)
_SYM = re.compile(r"^\d+\s+([0-9a-f]{8})\s+(_c_int00|_main|code_start)\s*$", re.M)
_UNPLACED = re.compile(r"UNPLACED|not allocated|run placement .* fails", re.I)


def parse_map(text: str) -> dict:
    out: dict = {"entry_symbol": None, "entry": None, "sections": {}, "memory": [], "symbols": {}, "unplaced": []}
    m = _ENTRY.search(text)
    if m:
        out["entry_symbol"], out["entry"] = m[1], int(m[2], 16)
    for m in _MEM.finditer(text):
        length, used = int(m[3], 16), int(m[4], 16)
        if used:
            out["memory"].append({"name": m[1], "origin": int(m[2], 16), "length": length, "used": used,
                                  "pct": round(100 * used / length, 1) if length else None})
    for m in _SECTION_HDR.finditer(text):
        out["sections"][m["name"]] = {"load": int(m["load"], 16), "size": int(m["size"], 16),
                                      "run": int(m["run"], 16) if m["run"] else None}
    for m in _SYM.finditer(text):
        out["symbols"][m[2]] = int(m[1], 16)
    out["unplaced"] = [l.strip()[:160] for l in text.splitlines() if _UNPLACED.search(l)][:5]
    return out


def check_map(text: str, mode: str = "flash") -> dict:
    """mode=flash: codestart at BEGIN 0x80000, entry and .text in flash, .TI.ramfunc loaded in flash but run in RAM.
    mode=ram: codestart and entry below 0x80000."""
    m = parse_map(text)
    problems: list[str] = []
    cs = m["sections"].get("codestart")
    if m["entry"] is None:
        problems.append("no ENTRY POINT line: the link failed or this is not a linker map")
    if cs is None:
        problems.append("no codestart section: the boot branch (f28004x_codestartbranch.asm) is not linked")
    if mode == "flash":
        if cs is not None and cs["load"] != FLASH_MIN:
            problems.append(f"codestart at {cs['load']:#x}, expected {FLASH_MIN:#x} (BEGIN) for boot-to-flash")
        if m["entry"] is not None and not FLASH_MIN <= m["entry"] < APP_MAX:
            problems.append(f"entry {m['entry']:#x} is not in flash: RAM linker .cmd or missing _FLASH build")
        rf = m["sections"].get(".TI.ramfunc")
        if rf is None:
            problems.append(".TI.ramfunc missing: InitFlash / F28x_usDelay will not be copied to RAM")
        elif not (rf["load"] >= FLASH_MIN and rf["run"] is not None and rf["run"] < FLASH_MIN):
            problems.append(".TI.ramfunc must load in flash and run in RAM (RUN ADDR)")
        t = m["sections"].get(".text")
        if t is not None and t["load"] < FLASH_MIN:
            problems.append(f".text at {t['load']:#x} is in RAM, expected flash")
    elif mode == "ram":
        if cs is not None and cs["load"] >= FLASH_MIN:
            problems.append(f"codestart at {cs['load']:#x} is in flash but the project is a RAM build")
        if m["entry"] is not None and m["entry"] >= FLASH_MIN:
            problems.append(f"entry {m['entry']:#x} is in flash but the project is a RAM build")
    if m["unplaced"]:
        problems.append("unplaced / unallocated sections: " + "; ".join(m["unplaced"]))
    # peripheral frames from the header .cmd and the 2-word BEGIN are always 100 %: only RAM / flash ranges count
    full = [x for x in m["memory"] if re.match(r"(RAM|FLASH)", x["name"]) and x["pct"] is not None and x["pct"] >= 95]
    hx = lambda v: f"{v:#x}" if isinstance(v, int) else v  # noqa: E731
    return {
        "ok": not problems, "mode": mode, "problems": problems,
        "entry": hx(m["entry"]), "entry_symbol": m["entry_symbol"],
        "codestart": hx(cs["load"]) if cs else None,
        "ramfunc": {k: hx(v) for k, v in m["sections"][".TI.ramfunc"].items()} if ".TI.ramfunc" in m["sections"] else None,
        "symbols": {k: hx(v) for k, v in m["symbols"].items()},
        "memory_used": [{**x, "origin": hx(x["origin"])} for x in m["memory"]],
        "nearly_full": [x["name"] for x in full],
    }


# --- DSS / CCS scripting output ----------------------------------------------------------------
DSS_ORDER = ("no_probe", "probe_busy", "target_power", "connect_fail", "flash_fail", "run_fail", "timeout",
             "other_error", "flash_ok", "connect_ok")

DSS_NEXT = {
    "flash_ok": "program written and verified; next: ccs_run_control run (or it already runs) / ccs_verify",
    "connect_ok": "the probe and the CPU answer; the board is ready for ccs_load",
    "no_probe": "Windows does not see the XDS110: check the USB cable (USB101 port), then ccs_env",
    "probe_busy": "another process holds the XDS110 (CCS IDE debug session, a dss.bat script or the daemon): "
                  "ccs_release / stop that session, then retry once",
    "target_power": "the probe answers but the CPU does not: board power / reset / JTAG (cJTAG) pins; ask the user to replug",
    "connect_fail": "connect failed for another reason: retry once; if it repeats, power-cycle the board",
    "flash_fail": "the flash write or verify failed: rebuild (ccs_build) and load again; check the .out is a FLASH build",
    "run_fail": "loaded but run/halt failed: ccs_run_control reset, then run",
    "timeout": "the scripting call timed out: ccs_release, then retry the same step once",
    "other_error": "unrecognized error text; read errors[]",
}

_DSS_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("no_probe", re.compile(r"no XDS110 is connected|(?:Error -260|-260 @)|could not find (?:the )?(?:XDS110|debug probe)"
                            r"|USB device not found", re.I)),
    ("probe_busy", re.compile(r"in use by another|already (?:in use|connected|open)|is busy|"
                              r"(?:Error -151|-151 @)|Unable to open (?:the )?(?:XDS110|USB)|Only one usage of each socket", re.I)),
    ("target_power", re.compile(r"(?:Error -(?:1135|2131|1170|2062|242)\b)|no power|target is not powered|"
                                r"Unable to access (?:the )?(?:DAP|device register)|cable break|power loss", re.I)),
    ("connect_fail", re.compile(r"CONNECT_FAIL|Error connecting to the target|Failed to connect|connect\(\) failed", re.I)),
    ("flash_fail", re.compile(r"FLASH_FAIL|File Loader: Verification failed|Program verification failed|"
                              r"Flash Programmer: Error|Error (?:erasing|programming) flash|loadProgram.*(?:failed|Error)|"
                              r"Trouble Writing Memory|Memory write failed", re.I)),
    ("run_fail", re.compile(r"RUN_FAIL|Target failed to run|Can't Run Target CPU", re.I)),
    ("timeout", re.compile(r"ScriptingTimeoutError|timed? ?out|timeout", re.I)),
]
_DSS_OK = re.compile(r"Program verification successful|^\s*(?:VERIFY_OK|FLASH_OK)\s*$", re.M)
_CONNECT_OK = re.compile(r"^\s*CONNECT_OK\s*$", re.M)
_DSS_ERR = re.compile(r"^.*\b(?:Error|Exception|SEVERE|Traceback|FAIL)\b.*$", re.M)


@dataclass
class DssResult:
    candidates: list[str]
    errors: list[str] = field(default_factory=list)
    exit_code: int | None = None

    @property
    def label(self) -> str:
        return self.candidates[0] if self.candidates else "other_error"

    @property
    def decisive(self) -> bool:
        return self.label != "other_error"

    def to_dict(self) -> dict:
        return {**asdict(self), "label": self.label, "decisive": self.decisive, "next_step": DSS_NEXT[self.label]}


def classify_dss(text: str) -> DssResult:
    # Cursor terminal files start with a `command: "..."` header that echoes the script source (and its
    # CONNECT_FAIL / FLASH_FAIL string literals): only the output counts
    lines = [l for l in text.splitlines() if "GEL" not in l and not l.startswith(("command: ", "title: "))]
    body = "\n".join(lines)
    ex = re.findall(r"exit_code:\s*(-?\d+)", body)
    exit_code = int(ex[-1]) if ex else None
    errs = [e.strip()[:240] for e in _DSS_ERR.findall(body) if not _DSS_OK.search(e)][:6]
    c = [lab for lab, pat in _DSS_PATTERNS if pat.search(body)]
    if "run_fail" in c and "flash_fail" not in c:
        c = [x for x in c if x != "flash_fail"]
    if not c:
        if _DSS_OK.search(body):
            c = ["flash_ok"]
        elif _CONNECT_OK.search(body):
            c = ["connect_ok"]
        elif errs or exit_code not in (0, None):
            c = ["other_error"]
    return DssResult([k for k in DSS_ORDER if k in c], errs, exit_code)


# --- verify_*.ps1 output -----------------------------------------------------------------------
_CHECK = re.compile(r"^\s*([A-Z][A-Z0-9_]+): (PASS|FAIL)\b", re.M)


def parse_verify(text: str) -> dict:
    checks: dict[str, bool] = {}
    for name, v in _CHECK.findall(text):
        checks[name] = v == "PASS"  # last one wins (the scripts print their own summary last)
    overall = checks.pop("OVERALL", None)
    if overall is None and checks:
        overall = all(checks.values())
    ex = re.findall(r"(?:EXIT_CODE|VERIFY_EXIT|exit_code)\s*[=:]\s*(-?\d+)", text)
    return {"overall": overall, "checks": checks, "failed": [k for k, v in checks.items() if not v],
            "exit_code": int(ex[-1]) if ex else None,
            "port_error": bool(re.search(r"Access to the port|denied|does not exist|is in use", text, re.I))}


# --- who holds the XDS110 ----------------------------------------------------------------------
def probe_owner(procs: list[dict], daemon_alive: bool, daemon_connected: bool) -> dict:
    """procs: [{name, pid, path}] for java/dss/DSLite/ccstudio/ccs-server and CCS's own node/python.
    java = a legacy dss.bat script. CCS node/python without a daemon = a run.bat script. The IDE's DSLite
    holds the probe only while a debug session is open, which a process list cannot tell: 'ide_maybe'."""
    n = lambda p: p["name"].lower()  # noqa: E731
    java = [p for p in procs if n(p) in ("java", "javaw", "dss")]
    ccs_node = [p for p in procs if n(p) in ("node", "python")]
    ide = any(n(p) in ("ccstudio", "ccs-server") for p in procs)
    if daemon_connected:
        owner = "daemon"
    elif java:
        owner = "dss_script"
    elif ccs_node and not daemon_alive:
        owner = "script_maybe"
    elif ide and any(n(p) == "dslite" for p in procs):
        owner = "ide_maybe"
    else:
        owner = "free"
    return {"owner": owner, "ide_open": ide, "daemon_alive": daemon_alive, "daemon_connected": daemon_connected,
            "scripts": [{k: p.get(k) for k in ("name", "pid")} for p in java + (ccs_node if not daemon_alive else [])]}


# --- build-file drift --------------------------------------------------------------------------
_CG_ROOT = re.compile(r"(?:CG_TOOL_ROOT\s*:=\s*|compiler[\\/])(\S*ti-cgt-c2000_[\w.]+)")
_DEFINE = re.compile(r"--define=(\S+)")
_INCLUDE = re.compile(r'--include_path="([^"]+)"')
_CMD = re.compile(r'"(\.\./[^"]+\.cmd)"')
_OPT = re.compile(r"(?<!\S)(--?[a-zA-Z][\w:-]*(?:=[^\s\"]+)?)")
KEY_FIELDS = ("compiler", "defines", "include_paths", "linker_cmds", "entry_point", "abi")


def build_flags(makefile: str, rules: str) -> dict:
    both = makefile + "\n" + rules
    cl = [l for l in both.splitlines() if "cl2000" in l]
    opts = sorted({o for l in cl for o in _OPT.findall(l)
                   if not o.startswith(("--include_path", "--define", "--preproc", "-i", "-l", "-m", "-o"))})
    ep = re.search(r"--entry_point=(\S+)", both)
    abi = re.search(r"--abi=(\w+)", both)
    return {
        "compiler": sorted(set(_CG_ROOT.findall(both))),
        "defines": sorted(set(_DEFINE.findall(both))),
        "include_paths": sorted(set(_INCLUDE.findall(both))),
        "linker_cmds": sorted(set(_CMD.findall(makefile))),
        "entry_point": ep[1] if ep else None,
        "abi": abi[1] if abi else None,
        "other_options": opts,
    }


def drift(baseline: dict, current: dict) -> dict:
    key = {k: {"baseline": baseline.get(k), "current": current.get(k)} for k in KEY_FIELDS
           if baseline.get(k) != current.get(k)}
    b, c = set(baseline.get("other_options", [])), set(current.get("other_options", []))
    other = {"added": sorted(c - b), "removed": sorted(b - c)}
    return {"key_changed": key, "other_changed": other if (other["added"] or other["removed"]) else None,
            "equivalent": None if (other["added"] or other["removed"]) and not key else not key}
