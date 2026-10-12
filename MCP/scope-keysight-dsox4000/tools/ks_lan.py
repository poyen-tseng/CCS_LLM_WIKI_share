"""Raw-socket SCPI helpers for the Keysight DSO-X 4034A (port 5025), standard library only.

Every IEEE block the scope sends (screenshots, waveforms) ends with a newline after the data;
read_block() consumes it, so the next query stays aligned.
An unknown query gets no reply at all: query() then raises socket.timeout.
"""
import json
import os
import pathlib
import socket
import time

HERE = pathlib.Path(__file__).resolve().parent
DEFAULT_ADDR = "192.168.137.60"
DEFAULT_PORT = 5025
DEFAULT_BIND = "192.168.137.1"
OPER_RUN = 1 << 3


def _config():
    cfg = HERE.parent / "config.json"
    return json.loads(cfg.read_text(encoding="utf-8")) if cfg.exists() else {}


def default_addr():
    return os.environ.get("KS_ADDR") or _config().get("addr") or DEFAULT_ADDR


def default_bind():
    if "KS_BIND" in os.environ:
        return os.environ["KS_BIND"]
    return _config().get("bind", DEFAULT_BIND)


def connect(addr=None, port=DEFAULT_PORT, bind=None, timeout=8):
    """bind="" skips binding; Windows may otherwise route 192.168.137.x through another adapter."""
    addr = addr or default_addr()
    bind = default_bind() if bind is None else bind
    s = socket.socket()
    s.settimeout(timeout)
    s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    if bind:
        s.bind((bind, 0))
    s.connect((addr, port))
    return s


def write(s, c):
    s.sendall((c + "\n").encode())


def query(s, c):
    s.sendall((c + "\n").encode())
    data = b""
    while not data.endswith(b"\n"):
        chunk = s.recv(65536)
        if not chunk:
            break
        data += chunk
    return data.decode(errors="replace").strip()


def errors(s):
    out = []
    for _ in range(10):
        e = query(s, ":SYST:ERR?")
        if e.startswith(("+0,", "0,")):
            break
        out.append(e)
    return out


def read_block(s, cmd):
    """Send cmd and read the IEEE block (#N<len><data>) it returns, including the trailing newline."""
    s.sendall((cmd + "\n").encode())
    buf = b""
    while len(buf) < 2:
        chunk = s.recv(4096)
        if not chunk:
            raise RuntimeError("no block header")
        buf += chunk
    if buf[:1] != b"#":
        raise RuntimeError(f"expected a block, got {buf[:40]!r}")
    nd = int(chr(buf[1]))
    while len(buf) < 2 + nd:
        buf += s.recv(4096)
    nbytes = int(buf[2 : 2 + nd].decode())
    rest = buf[2 + nd :]
    while len(rest) < nbytes + 1:  # data plus the newline terminator
        chunk = s.recv(max(4096, nbytes + 1 - len(rest)))
        if not chunk:
            break
        rest += chunk
    return rest[:nbytes]


def run_state(s, window_s=0.25):
    """RIGOL-style trigger status: STOP, AUTO (auto sweep), and in NORM sweep TD when a trigger arrives
    within window_s (the :TER? latch; the wait bit is unreliable, it even clears for a moment after a
    setting change), else WAIT. Clears :TER?. Never read a waveform or measurement in WAIT: the query
    blocks the scope until a trigger (recover with `python keysight.py recover`)."""
    cond = int(float(query(s, ":OPER:COND?")))
    if not cond & OPER_RUN:
        return "STOP"
    if query(s, ":TRIG:SWE?").upper().startswith("AUTO"):
        return "AUTO"
    query(s, ":TER?")  # drop a latch left from earlier
    end = time.time() + window_s
    while True:
        time.sleep(0.02)
        if query(s, ":TER?").lstrip("+") == "1":
            return "TD"
        if not int(float(query(s, ":OPER:COND?"))) & OPER_RUN:
            return "STOP"
        if time.time() >= end:
            return "WAIT"


def screenshot(s, white=True):
    """PNG of the screen; white=True uses Ink Saver and restores the previous setting afterwards."""
    old = query(s, ":HARD:INKS?") == "1"
    if old != white:
        write(s, f":HARD:INKS {1 if white else 0}")
    try:
        return read_block(s, ":DISP:DATA? PNG,COL")
    finally:
        if old != white:
            write(s, f":HARD:INKS {1 if old else 0}")


def waveform_raw(s, source="CHAN1", points=1000):
    """Screen-resolution (NORM) waveform: (times, volts, raw bytes 0..255)."""
    write(s, f":WAV:SOUR {source}")
    write(s, ":WAV:FORM BYTE")
    write(s, ":WAV:UNS 1")
    write(s, ":WAV:POIN:MODE NORM")
    write(s, f":WAV:POIN {points}")
    pre = [float(x) for x in query(s, ":WAV:PRE?").split(",")]
    _fmt, _typ, _points, _cnt, xinc, xorig, xref, yinc, yorig, yref = pre
    raw = read_block(s, ":WAV:DATA?")
    vals = [(b - yref) * yinc + yorig for b in raw]
    times = [xorig + (i - xref) * xinc for i in range(len(vals))]
    return times, vals, raw


def waveform(s, source="CHAN1", points=1000):
    times, vals, _raw = waveform_raw(s, source, points)
    return times, vals
