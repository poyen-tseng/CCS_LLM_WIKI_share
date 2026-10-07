"""Long-lived CCS debug session for the F280049C, shared by every agent on this PC.

Runs under the Python that ships with CCS 21 (the scripting package needs >= 3.12), not the project venv:
    C:/ti/ccs2101/ccs/ccs_base/DebugServer/ca-modules/tools/python3.14/python.exe ccs_daemon.py --port 47011

Why: every dss.bat / run.bat call pays ~32 s for initScripting (CloudAgent start) plus ~6 s configure+connect
before any work (measured 2026-10-07). Kept warm, a flash load is ~12 s and halt / read PC / run are < 0.1 s.

Protocol: one JSON object per line over 127.0.0.1 TCP, one JSON reply per line.
    {"cmd": "ping"} | {"cmd": "load", "program": ".../x.out", "ccxml": ".../x.ccxml", "run": true} | ...
Only standard library + CCS's own site-packages are imported here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import socketserver
import sys
import threading
import time
import traceback
from pathlib import Path

CORE = "C28xx_CPU1"


class State:
    def __init__(self, args):
        self.args = args
        self.lock = threading.RLock()   # one scripting call at a time
        self.ready = threading.Event()  # initScripting finished (or failed)
        self.ds = None
        self.session = None
        self.ccxml = None
        self.ccxml_hash = None
        self.connected = False
        self.init_error = None
        self.init_s = None
        self.op = None
        self.last = None
        self.started = time.time()
        self.last_cmd = time.time()


S: State


def _log(rec: dict) -> None:
    try:
        with open(S.args.log, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
    except OSError:
        pass


def _init() -> None:
    t0 = time.perf_counter()
    try:
        site = Path(S.args.ccs_root) / "scripting" / "python" / "site-packages"
        sys.path.insert(0, str(site))
        from scripting import initScripting  # noqa: PLC0415
        opts = {"suppressMessages": True, "timeout": S.args.timeout_ms}
        if S.args.attach:
            opts["attach"] = "auto"  # share the open CCS IDE's debugger instead of starting a second one
        S.ds = initScripting(**opts)
    except Exception as e:  # noqa: BLE001
        S.init_error = f"{type(e).__name__}: {e}"
    S.init_s = round(time.perf_counter() - t0, 2)
    S.ready.set()
    _log({"ts": _ts(), "cmd": "_init", "ok": S.init_error is None, "error": S.init_error, "elapsed_s": S.init_s,
          "attach": S.args.attach})


def _ts() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _hash(path: str) -> str:
    return hashlib.sha1(Path(path).read_bytes()).hexdigest()


def _need_ds():
    if not S.ready.wait(S.args.timeout_ms / 1000):
        raise TimeoutError("initScripting is still running")
    if S.init_error:
        raise RuntimeError(f"initScripting failed: {S.init_error}")
    return S.ds


def _connect(ccxml: str | None) -> dict:
    ds = _need_ds()
    ccxml = ccxml or S.ccxml or S.args.ccxml
    if not ccxml:
        raise ValueError("no ccxml given and none configured yet")
    h = _hash(ccxml)
    out = {"reused": False}
    if S.session is not None and h == S.ccxml_hash and S.connected:
        out["reused"] = True
        return out
    if S.session is not None and h != S.ccxml_hash:  # a different board description: start a new session
        _disconnect()
        try:
            S.session.terminate()
        except Exception:  # noqa: BLE001
            pass
        S.session = None
    if S.session is None:
        ds.configure(ccxml)
        S.session = ds.openSession(CORE)
        S.ccxml, S.ccxml_hash = ccxml, h
    S.session.target.connect()
    S.connected = True
    return out


def _disconnect() -> None:
    if S.session is not None and S.connected:
        try:
            S.session.target.disconnect()
        finally:
            S.connected = False


def _pc() -> str | None:
    try:
        return hex(int(S.session.registers.read("PC")))
    except Exception:  # noqa: BLE001  (running target: PC not readable)
        return None


def _halted() -> bool | None:
    try:
        return bool(S.session.target.isHalted())
    except Exception:  # noqa: BLE001
        return None


def _steps(fns: list[tuple[str, callable]]) -> dict:
    t = {}
    for name, fn in fns:
        t0 = time.perf_counter()
        fn()
        t[name] = round(time.perf_counter() - t0, 3)
    return t


def do(req: dict) -> dict:
    cmd = req.get("cmd")
    if cmd == "ping":  # never takes the lock: answers while a load is running
        return {"ok": True, "pid": os.getpid(), "port": S.args.port, "ready": S.ready.is_set(), "init_s": S.init_s,
                "init_error": S.init_error, "connected": S.connected, "ccxml": S.ccxml, "busy": S.op,
                "attach": S.args.attach, "uptime_s": round(time.time() - S.started),
                "idle_s": round(time.time() - S.last_cmd), "last": S.last}
    with S.lock:
        S.op, S.last_cmd = cmd, time.time()
        try:
            if cmd == "connect":
                r = _connect(req.get("ccxml"))
                return {"ok": True, **r, "halted": _halted(), "pc": _pc()}
            if cmd == "load":
                prog = req["program"]
                if not Path(prog).exists():
                    raise FileNotFoundError(prog)
                t0 = time.perf_counter()
                c = _connect(req.get("ccxml"))
                steps = []
                if req.get("reset", True):
                    steps.append(("reset", lambda: S.session.target.reset()))
                steps.append(("load", lambda: S.session.memory.loadProgram(prog)))
                if req.get("verify", True):
                    steps.append(("verify", lambda: S.session.memory.verifyProgram(prog)))
                t = _steps(steps)
                pc = _pc()
                if req.get("run"):
                    S.session.target.run(False)
                out = {"ok": True, "verified": req.get("verify", True), "pc_after_load": pc, "running": bool(req.get("run")),
                       "steps_s": t, "connect_reused": c["reused"], "elapsed_s": round(time.perf_counter() - t0, 2),
                       "program": prog, "program_mtime": time.strftime("%Y-%m-%dT%H:%M:%S",
                                                                       time.localtime(Path(prog).stat().st_mtime))}
                S.last = {"cmd": "load", "program": prog, "pc": pc, "ts": _ts(), "ok": True}
                return out
            if cmd in ("run", "halt", "reset", "restart"):
                _connect(req.get("ccxml"))
                t0 = time.perf_counter()
                tgt = S.session.target
                {"run": lambda: tgt.run(False), "halt": tgt.halt, "reset": tgt.reset, "restart": tgt.restart}[cmd]()
                dt = round(time.perf_counter() - t0, 3)
                if cmd == "halt" or cmd == "reset":
                    time.sleep(0.05)
                return {"ok": True, "elapsed_s": dt, "halted": _halted(), "pc": _pc() if cmd != "run" else None}
            if cmd == "status":
                return {"ok": True, "connected": S.connected, "halted": _halted() if S.connected else None,
                        "pc": _pc() if S.connected else None, "last": S.last}
            if cmd == "read_reg":
                _connect(req.get("ccxml"))
                return {"ok": True, "values": {n: _fmt(S.session.registers.read(n)) for n in req.get("names", ["PC"])}}
            if cmd == "read_mem":
                _connect(req.get("ccxml"))
                vals = S.session.memory.read(int(str(req["addr"]), 0), int(req.get("count", 1)), req.get("bits"))
                return {"ok": True, "addr": hex(int(str(req["addr"]), 0)), "values": [_fmt(v) for v in vals]}
            if cmd == "write_mem":
                _connect(req.get("ccxml"))
                S.session.memory.write(int(str(req["addr"]), 0), [int(str(v), 0) for v in req["values"]], req.get("bits"))
                return {"ok": True}
            if cmd == "release":  # free the XDS110 for dss.bat / the IDE; the warm CloudAgent stays
                _disconnect()
                return {"ok": True, "connected": False}
            if cmd == "shutdown":
                _disconnect()
                threading.Thread(target=_exit, daemon=True).start()
                return {"ok": True, "exiting": True}
            raise ValueError(f"unknown cmd {cmd!r}")
        except Exception as e:  # noqa: BLE001
            S.last = {"cmd": cmd, "ts": _ts(), "ok": False, "error": f"{type(e).__name__}: {e}"}
            return {"ok": False, "error": f"{type(e).__name__}: {e}", "error_type": type(e).__name__,
                    "trace": traceback.format_exc(limit=3)[-1500:]}
        finally:
            S.op, S.last_cmd = None, time.time()


def _fmt(v):
    return hex(v) if isinstance(v, int) else v


def _exit() -> None:
    time.sleep(0.2)
    try:
        if S.ds is not None:
            S.ds.shutdown()
    finally:
        _log({"ts": _ts(), "cmd": "_exit", "uptime_s": round(time.time() - S.started)})
        os._exit(0)


def _watchdog() -> None:
    while True:
        time.sleep(15)
        if S.op is None and time.time() - S.last_cmd > S.args.idle_s:
            with S.lock:
                _disconnect()
            _log({"ts": _ts(), "cmd": "_idle_exit", "idle_s": S.args.idle_s})
            _exit()


class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        for line in self.rfile:
            if not line.strip():
                continue
            t0 = time.perf_counter()
            try:
                req = json.loads(line)
                out = do(req)
            except Exception as e:  # noqa: BLE001
                req, out = {}, {"ok": False, "error": f"bad request: {e}"}
            out["daemon_ms"] = round((time.perf_counter() - t0) * 1000, 1)
            if req.get("cmd") != "ping":
                _log({"ts": _ts(), "cmd": req.get("cmd"), "req": {k: v for k, v in req.items() if k != "cmd"},
                      "ok": out.get("ok"), "error": out.get("error"), "pc": out.get("pc") or out.get("pc_after_load"),
                      "elapsed_ms": out["daemon_ms"], "client": req.get("client")})
            self.wfile.write((json.dumps(out, default=str) + "\n").encode())
            self.wfile.flush()


class Server(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = False  # a second daemon on the same port must fail, not share it


def main() -> None:
    global S
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=47011)
    p.add_argument("--ccs-root", default="C:/ti/ccs2101/ccs")
    p.add_argument("--ccxml", default=None)
    p.add_argument("--log", default=str(Path(__file__).resolve().parents[2] / "results" / "ccs_runs.jsonl"))
    p.add_argument("--idle-s", type=float, default=600)
    p.add_argument("--timeout-ms", type=int, default=180000)
    p.add_argument("--attach", action="store_true")
    S = State(p.parse_args())
    srv = Server(("127.0.0.1", S.args.port), Handler)  # bind first: a duplicate daemon exits here
    Path(S.args.log).parent.mkdir(parents=True, exist_ok=True)
    _log({"ts": _ts(), "cmd": "_start", "pid": os.getpid(), "port": S.args.port, "attach": S.args.attach})
    threading.Thread(target=_init, daemon=True).start()
    threading.Thread(target=_watchdog, daemon=True).start()
    srv.serve_forever()


if __name__ == "__main__":
    main()
