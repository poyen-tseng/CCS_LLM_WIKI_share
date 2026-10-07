"""Client for ccs_daemon (runs in the project venv). Starts the daemon detached when it is not running,
so Cursor, Claude Code and the CLI all share one warm debug session and never fight over the XDS110."""
from __future__ import annotations

import json
import os
import socket
import subprocess
import time
from pathlib import Path

from .config import RESULTS, load_config

DAEMON = Path(__file__).with_name("ccs_daemon.py")
LOG = RESULTS / "ccs_runs.jsonl"


def _cfg() -> dict:
    return load_config()["ccs"]


def call(req: dict, timeout_s: float | None = None) -> dict:
    """One request; raises ConnectionError when no daemon listens."""
    c = _cfg()["daemon"]
    timeout_s = timeout_s or c["timeout_ms"] / 1000 + 10
    try:
        with socket.create_connection(("127.0.0.1", c["port"]), timeout=2) as s:
            s.settimeout(timeout_s)
            s.sendall((json.dumps({**req, "client": os.environ.get("JEV_CLIENT", "jev-ccs")}) + "\n").encode())
            buf = b""
            while not buf.endswith(b"\n"):
                chunk = s.recv(65536)
                if not chunk:
                    break
                buf += chunk
    except OSError as e:
        raise ConnectionError(str(e)) from e
    return json.loads(buf or b'{"ok": false, "error": "empty reply"}')


def ping() -> dict | None:
    try:
        return call({"cmd": "ping"}, timeout_s=3)
    except ConnectionError:
        return None


def start(attach: bool = False) -> dict:
    """Spawn the daemon (if needed) and wait until it answers ping. initScripting runs in the background
    from that moment, so start it early (ccs_build does) to overlap the ~32 s cold start with gmake."""
    p = ping()
    if p:
        return {**p, "started": False}
    c = _cfg()
    RESULTS.mkdir(parents=True, exist_ok=True)
    args = [c["python"], str(DAEMON), "--port", str(c["daemon"]["port"]), "--ccs-root", c["root"],
            "--log", str(LOG), "--idle-s", str(c["daemon"]["idle_s"]), "--timeout-ms", str(c["daemon"]["timeout_ms"])]
    if attach:
        args.append("--attach")
    flags = 0x00000008 | 0x00000200 | 0x08000000  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW
    with open(RESULTS / "ccs_daemon.out", "ab") as out:
        subprocess.Popen(args, stdout=out, stderr=out, stdin=subprocess.DEVNULL, creationflags=flags, close_fds=True)
    t0 = time.time()
    while time.time() - t0 < c["daemon"]["start_wait_s"]:
        p = ping()
        if p:
            return {**p, "started": True}
        time.sleep(0.2)
    raise ConnectionError("ccs_daemon did not start; see results/ccs_daemon.out")


def request(req: dict, attach: bool = False) -> dict:
    """Call the daemon, starting it first when it is not running."""
    try:
        return call(req)
    except ConnectionError:
        start(attach)
        return call(req)


def recent_runs(n: int = 10) -> list[dict]:
    if not LOG.exists():
        return []
    lines = LOG.read_text(encoding="utf-8", errors="replace").splitlines()[-n:]
    return [json.loads(l) for l in lines if l.strip()]
