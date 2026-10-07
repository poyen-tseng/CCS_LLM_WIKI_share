"""CCS side: one call -> facts + L0 verdict (+ Jev only for unrecognized error text) + next step.

Shared by the CLI and the jev-ccs MCP server. Same contract as tools.py: a decisive rule answer always
wins; Jev is asked only for error text the rules do not recognize (it reads text well, numbers badly).
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
from pathlib import Path

from . import ccs_client
from . import questions as Q
from .config import RESULTS, load_config
from .rules import build as build_rules
from .rules import ccs as ccs_rules
from .tools import _resolve

SRC_EXT = (".c", ".h", ".asm", ".cmd")
STATE_DIR = RESULTS / "ccs_state"


def _cfg() -> dict:
    return load_config()["ccs"]


def _decode(b: bytes) -> str:
    try:
        return b.decode("utf-8")
    except UnicodeDecodeError:
        return b.decode("cp950", errors="replace")  # cmd.exe DEL / CreateProcess messages on this PC are Big5


def project_dir(project: str) -> Path:
    p = Path(project)
    return p if p.is_absolute() else Path(_cfg()["projects_root"]) / project


def _proj_mode(pd: Path) -> str:
    c = _cfg()["projects"].get(pd.name, {})
    if "mode" in c:
        return c["mode"]
    mk = pd / "Debug" / "subdir_rules.mk"
    return "flash" if mk.exists() and "--define=_FLASH" in mk.read_text(encoding="utf-8", errors="replace") else "ram"


def _paths(pd: Path) -> dict:
    ccxml = next(iter(sorted((pd / "targetConfigs").glob("*.ccxml"))), None)
    return {"dir": pd, "debug": pd / "Debug", "out": pd / "Debug" / f"{pd.name}.out",
            "map": pd / "Debug" / f"{pd.name}.map", "ccxml": ccxml}


def _sources(pd: Path) -> list[Path]:
    return sorted(p for p in pd.iterdir() if p.is_file() and p.suffix.lower() in SRC_EXT)


def _hashes(pd: Path) -> dict[str, str]:
    return {p.name: hashlib.sha1(p.read_bytes()).hexdigest() for p in _sources(pd)}


def _state_file(pd: Path) -> Path:
    return STATE_DIR / f"{pd.name}.json"


def _load_state(pd: Path) -> dict:
    f = _state_file(pd)
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}


def _save_state(pd: Path, **kw) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    st = {**_load_state(pd), **kw}
    _state_file(pd).write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")


def changed_sources(pd: Path) -> dict:
    """Sources that differ from the last successful build. Content hashes, not mtimes: copying a file with
    an old mtime made gmake say 'up to date' and the board kept running the old QSEL (c8f002db L655)."""
    out = _paths(pd)["out"]
    rec = _load_state(pd).get("built_hashes")
    if rec is None:  # never built through ccs_build: fall back to mtimes
        if not out.exists():
            return {"basis": "no .out", "changed": [p.name for p in _sources(pd)]}
        t = out.stat().st_mtime
        return {"basis": "mtime", "changed": [p.name for p in _sources(pd) if p.stat().st_mtime > t]}
    cur = _hashes(pd)
    return {"basis": "hash", "changed": sorted(k for k in cur if rec.get(k) != cur[k])
            + sorted(k for k in rec if k not in cur)}


# --- environment / probe -----------------------------------------------------------------------
_PS_FACTS = r"""
$ErrorActionPreference='SilentlyContinue'
$pnp = @(Get-PnpDevice -PresentOnly | Where-Object { $_.FriendlyName -match 'XDS110' } | ForEach-Object { @{name=$_.FriendlyName; status="$($_.Status)"} })
$pr = @(Get-Process | Where-Object { $_.ProcessName -match '^(java|javaw|dss|DSLite|ccstudio|ccs-server|node|python)$' } | ForEach-Object { @{name=$_.ProcessName; pid=$_.Id; path=$_.Path} })
@{pnp=$pnp; procs=$pr} | ConvertTo-Json -Depth 4 -Compress
"""


def host_facts() -> dict:
    """XDS110 PnP entries and the processes that can hold the probe, in one PowerShell call (~1 s)."""
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-Command", _PS_FACTS], capture_output=True, timeout=30)
        d = json.loads(_decode(r.stdout) or "{}")
    except (subprocess.SubprocessError, json.JSONDecodeError, OSError) as e:
        return {"error": str(e), "pnp": [], "procs": []}
    pnp = d.get("pnp") or []
    pnp = [pnp] if isinstance(pnp, dict) else pnp
    procs = d.get("procs") or []
    procs = [procs] if isinstance(procs, dict) else procs
    root = _cfg()["root"].replace("/", "\\").lower()
    # node / python only matter when they belong to the CCS install (CloudAgent, run.bat, the daemon)
    procs = [p for p in procs if p["name"].lower() not in ("node", "python")
             or root in (p.get("path") or "").lower()]
    com = sorted({n.split("(")[-1].rstrip(")") for n in (x["name"] for x in pnp) if "(COM" in n})
    return {"pnp": pnp, "probe_present": any("Debug Probe" in x["name"] and x["status"] == "OK" for x in pnp),
            "com_ports": com, "procs": procs}


def ccs_env() -> dict:
    """Every path an agent used to search for, checked in one call, plus probe / daemon / project status."""
    c = _cfg()
    root = Path(c["root"])
    tools = {
        "gmake": root / "utils/bin/gmake.exe",
        "dss_bat": root / "ccs_base/scripting/bin/dss.bat",
        "run_bat_js": root / "scripting/run.bat",
        "run_bat_py": root / "scripting/python/run.bat",
        "ccs_python": Path(c["python"]),
        "ccstudio": root / "theia/ccstudio.exe",
        "ccs_server_cli": root / "eclipse/ccs-server-cli.bat",
        "xdsdfu": root / "ccs_base/common/uscif/xds110/xdsdfu.exe",
        "dbgjtag": root / "ccs_base/common/uscif/dbgjtag.exe",
        "cl2000": Path(c["compiler"]) / "bin/cl2000.exe",
        "c2000ware": Path(c["c2000ware"]),
        "scripting_docs": root / "scripting/docs/index.html",
    }
    hf = host_facts()
    ping = ccs_client.ping()
    owner = ccs_rules.probe_owner(hf["procs"], ping is not None, bool(ping and ping.get("connected")))
    projects = {}
    for pd in sorted(Path(c["projects_root"]).iterdir()):
        if not (pd / "Debug" / "makefile").exists():
            continue
        p = _paths(pd)
        projects[pd.name] = {"mode": _proj_mode(pd), "ccxml": str(p["ccxml"]) if p["ccxml"] else None,
                             "out": str(p["out"]) if p["out"].exists() else None,
                             "out_mtime": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(p["out"].stat().st_mtime))
                             if p["out"].exists() else None,
                             "changed_since_build": changed_sources(pd)["changed"],
                             "verify": c["projects"].get(pd.name, {}).get("verify")}
    return {"tools": {k: {"path": str(v), "exists": v.exists()} for k, v in tools.items()},
            "probe_present": hf["probe_present"], "com_ports": hf["com_ports"], "pnp": hf["pnp"],
            "probe": owner, "daemon": ping, "projects": projects,
            "recent_runs": ccs_client.recent_runs(5), "host_error": hf.get("error")}


# --- build -------------------------------------------------------------------------------------
def _gmake(debug: Path, target: str, timeout_s: float) -> tuple[str, float]:
    gm = Path(_cfg()["root"]) / "utils/bin/gmake.exe"
    t0 = time.perf_counter()
    try:
        r = subprocess.run([str(gm), "-k", "-j", target], cwd=debug, capture_output=True, timeout=timeout_s)
        text = _decode(r.stdout + r.stderr) + f"\nexit_code: {r.returncode}\n"
    except subprocess.TimeoutExpired as e:
        text = _decode((e.stdout or b"") + (e.stderr or b"")) + f"\ngmake timed out after {timeout_s} s\nexit_code: -1\n"
    return text, round(time.perf_counter() - t0, 2)


def decide_build(text: str, changed: list[str] | None = None, project_dir_s: str = "", elapsed_s: float | None = None,
                 jev_mode: str = "auto") -> dict:
    p = build_rules.parse(text)
    r = build_rules.classify(p, changed, project_dir_s, elapsed_s)
    err_ctx = [l for l in text.splitlines() if "error" in l.lower() or "warning" in l.lower() or "fail" in l.lower()]
    state = {"error_lines": "\n".join(l[:300] for l in err_ctx if "cl2000\"" not in l)[-2000:],
             "tail": "\n".join(text.splitlines()[-25:])[-1500:],
             "sources_changed_since_last_build": changed or [], "elapsed_s": elapsed_s,
             "project_dir": project_dir_s}
    label, source, d = _resolve(r.label, r.decisive, jev_mode, state, Q.build_questions(), "build_error", "build")
    return {"result": label, "source": source, "next_step": build_rules.NEXT_STEPS[label],
            "errors": p.errors[:5], "link_errors": p.link_errors[:5], "undefined": p.undefined,
            "warnings": len(p.warnings), "missing_tool": p.missing_tool, "built": p.built,
            "up_to_date": p.up_to_date, "l0": r.to_dict()["candidates"], "jev": d.to_dict() if d else None}


def ccs_build(project: str, clean: bool = False, warm_daemon: bool = True, jev_mode: str = "auto") -> dict:
    pd = project_dir(project)
    paths = _paths(pd)
    if not (paths["debug"] / "makefile").exists():
        return {"result": "other_error", "next_step": f"no Debug/makefile in {pd}", "source": "l0"}
    daemon = None
    if warm_daemon:  # start initScripting now so it overlaps with gmake
        try:
            daemon = ccs_client.start()
        except ConnectionError as e:
            daemon = {"error": str(e)}
    timeout = _cfg()["build_timeout_s"]
    changed = changed_sources(pd)
    logs = []
    if clean:
        t, _ = _gmake(paths["debug"], "clean", timeout)
        logs.append(t)
    text, el = _gmake(paths["debug"], "all", timeout)
    out = decide_build(text, changed["changed"], str(pd), el, jev_mode)
    auto = None
    if out["result"] == "stale_build":  # touch what changed and build once more
        now = time.time()
        for n in changed["changed"]:
            if (pd / n).exists():
                os.utime(pd / n, (now, now))
        text, el2 = _gmake(paths["debug"], "all", timeout)
        el += el2
        out = decide_build(text, [], str(pd), el, jev_mode)
        auto = {"touched": changed["changed"], "result_after": out["result"]}
    out.update(project=pd.name, elapsed_s=el, changed_before=changed, auto_fixed_stale=auto,
               daemon_warming=bool(daemon and not daemon.get("error")))
    if out["result"] == "ok":
        _save_state(pd, built_hashes=_hashes(pd), built_at=time.strftime("%Y-%m-%dT%H:%M:%S"))
        out["map"] = ccs_map_check(pd.name)
    out["log_tail"] = "\n".join(text.splitlines()[-12:])[-1200:]
    return out


def ccs_map_check(project: str, mode: str | None = None) -> dict:
    pd = project_dir(project)
    m = _paths(pd)["map"]
    if not m.exists():
        return {"ok": False, "problems": [f"{m} not found: build first"], "mode": mode}
    return ccs_rules.check_map(m.read_text(encoding="utf-8", errors="replace"), mode or _proj_mode(pd))


# --- debugger (daemon) -------------------------------------------------------------------------
def decide_dss(text: str, probe_present: bool | None = None, owner: str | None = None, jev_mode: str = "auto") -> dict:
    """probe_present / owner are facts the text cannot carry: with another session on the XDS110, dss.bat prints
    'Error -260 ... no XDS110 is connected', the same words as an unplugged probe (measured 2026-10-07)."""
    r = ccs_rules.classify_dss(text)
    cands = list(r.candidates)
    if "no_probe" in cands and probe_present:
        cands = ["probe_busy"] + [c for c in cands if c not in ("no_probe", "probe_busy", "connect_fail")]
    if not cands and owner in ("daemon", "dss_script") and r.errors:
        cands = ["probe_busy"]
    r = ccs_rules.DssResult(cands or r.candidates, r.errors, r.exit_code)
    state = {"output": "\n".join(l for l in text.splitlines() if "GEL" not in l)[-2000:],
             "probe_visible_to_windows": probe_present, "other_probe_user": owner}
    label, source, d = _resolve(r.label, r.decisive, jev_mode, state, Q.dss_questions(), "dss_state", "dss")
    return {"state": label, "source": source, "next_step": ccs_rules.DSS_NEXT[label], "errors": r.errors,
            "l0": r.candidates, "jev": d.to_dict() if d else None}


def ccs_dss_state(text: str | None = None, path: str | None = None, jev_mode: str = "auto",
                  probe_present: bool | None = None) -> dict:
    if text is None:
        text = _decode(Path(path).read_bytes())
    if probe_present is None:
        probe_present = host_facts()["probe_present"]
    return decide_dss(text, probe_present, None, jev_mode)


def _daemon(req: dict) -> dict:
    t0 = time.perf_counter()
    try:
        r = ccs_client.request(req)
    except ConnectionError as e:
        r = {"ok": False, "error": f"daemon unreachable: {e}"}
    r["client_s"] = round(time.perf_counter() - t0, 3)
    return r


def ccs_load(project: str | None = None, program: str | None = None, ccxml: str | None = None, run: bool = True,
             verify: bool = True, check: bool = True, jev_mode: str = "auto") -> dict:
    pre: dict = {}
    if project:
        pd = project_dir(project)
        p = _paths(pd)
        program = program or str(p["out"])
        ccxml = ccxml or (str(p["ccxml"]) if p["ccxml"] else None)
        if check:
            ch = changed_sources(pd)
            pre["changed_since_build"] = ch["changed"]
            if ch["changed"]:
                return {"state": "rebuild_needed", "source": "l0", "pre": pre,
                        "next_step": f"sources changed since the last build ({', '.join(ch['changed'][:5])}): ccs_build first"}
            mc = ccs_map_check(pd.name)
            pre["map_ok"] = mc["ok"]
            if not mc["ok"]:
                return {"state": "bad_image", "source": "l0", "pre": pre, "map": mc,
                        "next_step": "the .map does not match the project mode: " + "; ".join(mc["problems"])}
    if not program or not ccxml:
        raise ValueError("give a project, or program + ccxml")
    r = _daemon({"cmd": "load", "program": program.replace("\\", "/"), "ccxml": ccxml.replace("\\", "/"),
                 "run": run, "verify": verify})
    if r.get("ok"):
        return {"state": "flash_ok", "source": "l0", "pc_after_load": r.get("pc_after_load"), "running": r.get("running"),
                "elapsed_s": r.get("elapsed_s"), "steps_s": r.get("steps_s"), "program_mtime": r.get("program_mtime"),
                "pre": pre, "next_step": ccs_rules.DSS_NEXT["flash_ok"]}
    hf = host_facts()
    out = decide_dss(f"{r.get('error')}\n{r.get('trace', '')}", hf["probe_present"], None, jev_mode)
    return {**out, "daemon_error": r.get("error"), "pre": pre, "client_s": r.get("client_s")}


def ccs_run_control(action: str, names: list[str] | None = None, addr: str | None = None, count: int = 1,
                    values: list[str] | None = None, bits: int | None = None) -> dict:
    req: dict = {"cmd": action}
    if action == "read_reg":
        req["names"] = names or ["PC"]
    elif action in ("read_mem", "write_mem"):
        req.update(addr=addr, count=count, bits=bits)
        if action == "write_mem":
            req["values"] = values or []
    r = _daemon(req)
    if not r.get("ok") and r.get("error"):
        r["diagnosis"] = decide_dss(f"{r['error']}\n{r.get('trace', '')}", host_facts()["probe_present"], None, "off")
    return r


def ccs_release(shutdown: bool = False) -> dict:
    """Disconnect from the CPU so dss.bat / the IDE can use the XDS110 (measured: dss.bat connects right after).
    shutdown=True also stops the daemon (next ccs_load pays the cold start again)."""
    if ccs_client.ping() is None:
        return {"ok": True, "note": "no daemon running; the probe is not held by it"}
    return _daemon({"cmd": "shutdown" if shutdown else "release"})


def ccs_verify(project: str, port: str | None = None, timeout_s: float = 120) -> dict:
    pd = project_dir(project)
    rel = _cfg()["projects"].get(pd.name, {}).get("verify")
    script = pd / rel if rel else next(iter(sorted((pd / "tools").glob("verify_*.ps1"))), None)
    if script is None or not script.exists():
        return {"overall": None, "note": f"no tools/verify_*.ps1 in {pd}"}
    t0 = time.perf_counter()
    r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script),
                        "-PortName", port or _cfg()["com_port"]], capture_output=True, timeout=timeout_s)
    text = _decode(r.stdout + r.stderr) + f"\nEXIT_CODE={r.returncode}\n"
    out = ccs_rules.parse_verify(text)
    out.update(script=str(script), elapsed_s=round(time.perf_counter() - t0, 2), tail="\n".join(text.splitlines()[-10:]))
    if out["port_error"]:
        out["next_step"] = "the COM port is busy (Serial Plotter page / a terminal open?): close it and rerun"
    return out


# --- drift -------------------------------------------------------------------------------------
def ccs_project_drift(project: str, set_baseline: bool = False, jev_mode: str = "auto") -> dict:
    pd = project_dir(project)
    mk, rules = pd / "Debug" / "makefile", pd / "Debug" / "subdir_rules.mk"
    cur = ccs_rules.build_flags(mk.read_text(encoding="utf-8", errors="replace"),
                                rules.read_text(encoding="utf-8", errors="replace") if rules.exists() else "")
    st = _load_state(pd)
    if set_baseline or "baseline_flags" not in st:
        _save_state(pd, baseline_flags=cur, baseline_at=time.strftime("%Y-%m-%dT%H:%M:%S"))
        return {"equivalent": True, "source": "l0", "baseline_set": True, "flags": cur}
    dr = ccs_rules.drift(st["baseline_flags"], cur)
    out = {**dr, "source": "l0", "baseline_at": st.get("baseline_at")}
    if dr["equivalent"] is None:  # only non-key options changed: Jev reads which kind of option it is
        decisive = jev_mode == "off"
        state = {"added_options": dr["other_changed"]["added"], "removed_options": dr["other_changed"]["removed"]}
        d = None
        if not decisive:
            from .tools import gate
            d = gate().ask(state, Q.drift_questions(), "drift")
            j = gate().confident_noul(d, "drift_equivalent")
            if j is not None:
                out.update(equivalent=j, source="jev")
        if out["equivalent"] is None:
            out.update(equivalent=False, source="l0_fallback")  # unknown option change: treat as a real change
        out["jev"] = d.to_dict() if d else None
    out["next_step"] = ("build files changed meaning: review key_changed, rebuild, and set_baseline=true once accepted"
                        if not out["equivalent"] else "no meaningful change; nothing to do")
    return out
