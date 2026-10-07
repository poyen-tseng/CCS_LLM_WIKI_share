"""python -m jev_accel <command> ... ; every command prints one JSON object."""
from __future__ import annotations

import argparse
import json
import sys
import time

from . import tools, tools_ccs


def _ping() -> dict:
    g = tools.gate()
    if not g.available:
        return {"ok": False, "error": "TYPESAFE_API_KEY is not set in this process"}
    d = g.ask({"message": "The oscilloscope trace is pushed off the top of the screen."},
              {"fix": {"type": "choice", "instructions": "Which setting is wrong?",
                       "criteria": {"offset": "vertical offset", "timebase": "horizontal timebase"}}}, "ping")
    return {"ok": d.source == "jev", "model": d.model, "latency_ms": d.latency_ms, "answers": d.answers,
            "input_tokens": d.input_tokens, "error": d.error}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="jev_accel", description=__doc__)
    p.add_argument("--jev", choices=["auto", "always", "off"], default="auto", help="when to ask Jev")
    sub = p.add_subparsers(dest="cmd", required=True)

    f = sub.add_parser("check-frame", help="A: is the current frame report-ready, and what to fix next")
    f.add_argument("--channel", default="CHAN1")
    f.add_argument("--goal", default="")
    f.add_argument("--note", action="append", default=[], help="e.g. 'RTIM overlay visible'")
    f.add_argument("--no-menu", action="store_true", help="skip the menu screenshot")
    f.add_argument("--apply", action="store_true", help="send the suggested SCPI fix")
    f.add_argument("--view", choices=["edge", "delay"], default="edge",
                   help="delay: two events on screen, the edge need not be centered")

    d = sub.add_parser("diagnose", help="B: why the single shot is flat / did not trigger")
    d.add_argument("--channel", default="CHAN1")
    d.add_argument("--level-set", type=float, help="trigger level you asked for (detects clamping)")
    d.add_argument("--pc", help="PC from the flash output, e.g. 0x3FB02A")
    d.add_argument("--build-stale", action="store_true")
    d.add_argument("--not-single", action="store_true", help="the capture was not meant to be single-shot")

    fl = sub.add_parser("flash-state", help="C: classify gmake / edge_run.js / ccs-debug output")
    fl.add_argument("path", help="terminal log file, or - for stdin")
    fl.add_argument("--expected", nargs=2, type=float, metavar=("LO", "HI"))
    fl.add_argument("--measured", type=float)
    fl.add_argument("--expectation", default="", help="free text, e.g. 'QSEL=2 CTRL=255: delay tens of us'")

    m = sub.add_parser("menu", help="D: is the side menu open (optionally hide it)")
    m.add_argument("--hide", action="store_true")

    a = sub.add_parser("autoframe", help="E: center and scale the channel from VTOP/VBASE (no Jev)")
    a.add_argument("--channel", default="CHAN1")
    a.add_argument("--mode", choices=["edge", "delay"], default="edge")
    a.add_argument("--delay", type=float, help="seconds between the two events (delay mode)")
    a.add_argument("--dry-run", action="store_true")

    sub.add_parser("ping-jev", help="one tiny Jev call: checks the key, model and latency")

    sub.add_parser("ccs-env", help="CCS paths, XDS110 owner, daemon and project status in one call")

    b = sub.add_parser("ccs-build", help="gmake a project and classify the output")
    b.add_argument("project")
    b.add_argument("--clean", action="store_true")
    b.add_argument("--no-warm", action="store_true", help="do not start the debug daemon during the build")

    mp = sub.add_parser("ccs-map", help="check Debug/<project>.map against flash or ram rules")
    mp.add_argument("project")
    mp.add_argument("--mode", choices=["flash", "ram"])

    ld = sub.add_parser("ccs-load", help="load a program through the warm debug daemon")
    ld.add_argument("project", nargs="?", help="project name under projects_root")
    ld.add_argument("--program")
    ld.add_argument("--ccxml")
    ld.add_argument("--no-run", action="store_true")
    ld.add_argument("--no-verify", action="store_true")
    ld.add_argument("--no-check", action="store_true", help="skip the changed-source and .map checks")

    ct = sub.add_parser("ccs-ctl", help="run, halt, reset, restart, status, or read registers and memory")
    ct.add_argument("action", choices=["run", "halt", "reset", "restart", "status", "read_reg", "read_mem", "write_mem"])
    ct.add_argument("--name", action="append", default=[], help="register name (read_reg); repeatable")
    ct.add_argument("--addr")
    ct.add_argument("--count", type=int, default=1)
    ct.add_argument("--value", action="append", default=[], help="value to write (write_mem); repeatable")
    ct.add_argument("--bits", type=int)

    rel = sub.add_parser("ccs-release", help="disconnect the daemon so something else can use the XDS110")
    rel.add_argument("--shutdown", action="store_true", help="also stop the daemon")

    vf = sub.add_parser("ccs-verify", help="run the project's tools/verify_*.ps1")
    vf.add_argument("project")
    vf.add_argument("--port")
    vf.add_argument("--timeout", type=float, default=120)

    dr = sub.add_parser("ccs-drift", help="compare Debug makefile flags with the saved baseline")
    dr.add_argument("project")
    dr.add_argument("--set-baseline", action="store_true")

    ds = sub.add_parser("ccs-dss", help="classify a dss.bat / daemon log")
    ds.add_argument("path", help="log file, or - for stdin")
    probe = ds.add_mutually_exclusive_group()
    probe.add_argument("--probe-present", action="store_true", help="XDS110 is visible in Windows")
    probe.add_argument("--probe-absent", action="store_true")

    args = p.parse_args(argv)
    t0 = time.perf_counter()
    if args.cmd == "check-frame":
        out = tools.check_frame(args.channel, args.jev, args.goal, args.note, check_menu=not args.no_menu,
                                apply=args.apply, view=args.view)
    elif args.cmd == "diagnose":
        out = tools.diagnose(args.channel, not args.not_single, args.level_set, args.pc,
                             True if args.build_stale else None, args.jev)
    elif args.cmd == "flash-state":
        text = sys.stdin.read() if args.path == "-" else None
        out = tools.flash_state(text, None if text is not None else args.path,
                                tuple(args.expected) if args.expected else None, args.measured,
                                args.expectation, args.jev)
    elif args.cmd == "menu":
        out = tools.menu(args.hide, args.jev)
    elif args.cmd == "autoframe":
        out = tools.autoframe_apply(args.channel, args.mode, args.delay, apply=not args.dry_run)
    elif args.cmd == "ping-jev":
        out = _ping()
    elif args.cmd == "ccs-env":
        out = tools_ccs.ccs_env()
    elif args.cmd == "ccs-build":
        out = tools_ccs.ccs_build(args.project, args.clean, warm_daemon=not args.no_warm, jev_mode=args.jev)
    elif args.cmd == "ccs-map":
        out = tools_ccs.ccs_map_check(args.project, args.mode)
    elif args.cmd == "ccs-load":
        out = tools_ccs.ccs_load(args.project, args.program, args.ccxml, run=not args.no_run,
                                 verify=not args.no_verify, check=not args.no_check, jev_mode=args.jev)
    elif args.cmd == "ccs-ctl":
        out = tools_ccs.ccs_run_control(args.action, args.name or None, args.addr, args.count,
                                        args.value or None, args.bits)
    elif args.cmd == "ccs-release":
        out = tools_ccs.ccs_release(args.shutdown)
    elif args.cmd == "ccs-verify":
        out = tools_ccs.ccs_verify(args.project, args.port, args.timeout)
    elif args.cmd == "ccs-drift":
        out = tools_ccs.ccs_project_drift(args.project, args.set_baseline, args.jev)
    elif args.cmd == "ccs-dss":
        text = sys.stdin.read() if args.path == "-" else None
        present = True if args.probe_present else False if args.probe_absent else None
        out = tools_ccs.ccs_dss_state(text, None if text is not None else args.path, args.jev, present)
    else:
        p.error(f"unhandled command {args.cmd}")
    out["elapsed_ms"] = round((time.perf_counter() - t0) * 1000, 1)
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
