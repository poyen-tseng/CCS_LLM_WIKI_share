"""Short-lived SCPI connection to the MSO5104, reusing CCS_LLM_WIKI_share/MCP/rigol-mso/tools/scope_lan.py.

scope_lan binds to 192.168.137.1 so Windows does not route the scope subnet through Wi-Fi. Each tool
call opens and closes its own socket, so the long-lived `scope` MCP is not blocked for long.
"""
from __future__ import annotations

import contextlib
import importlib.util
import sys
import time
from pathlib import Path

import numpy as np

from .config import load_config


def _load_scope_lan(cfg: dict):
    path = Path(cfg["rigol_mso_dir"]) / "tools" / "scope_lan.py"
    if not path.exists():
        raise FileNotFoundError(f"scope_lan.py not found at {path}; fix rigol_mso_dir in config.json")
    spec = importlib.util.spec_from_file_location("scope_lan", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("scope_lan", mod)
    spec.loader.exec_module(mod)
    return mod


class Scope:
    def __init__(self, cfg: dict | None = None):
        self.cfg = cfg or load_config()
        self.lan = _load_scope_lan(self.cfg)
        sc = self.cfg["scope"]
        try:
            self.s = self.lan.connect(sc["addr"], sc["port"], sc["bind"], timeout=sc["timeout_s"])
        except OSError:
            if not sc["bind"]:
                raise
            # the bind address is not on this PC (different NIC/IP): connect unbound
            self.s = self.lan.connect(sc["addr"], sc["port"], "", timeout=sc["timeout_s"])

    def close(self) -> None:
        with contextlib.suppress(OSError):
            self.s.close()

    def w(self, cmd: str) -> None:
        self.lan.write(self.s, cmd)

    def q(self, cmd: str) -> str:
        return self.lan.query(self.s, cmd)

    def qf(self, cmd: str) -> float:
        return float(self.q(cmd))

    def block(self, cmd: str) -> bytes:
        data = self.lan.read_block(self.s, cmd)
        self.lan.drain(self.s, restore=self.cfg["scope"]["timeout_s"])  # else later queries read one reply behind
        return data

    def measure(self, item: str, source: str = "CHAN1") -> float | None:
        try:
            v = self.qf(f":MEAS:ITEM? {item},{source}")
        except ValueError:
            return None
        return None if abs(v) >= 9.9e37 else v

    def waveform_raw(self, source: str = "CHAN1") -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """On-screen (NORM, 1000 pt) waveform: (t, volts, raw bytes)."""
        self.w(f":WAV:SOUR {source}")
        self.w(":WAV:MODE NORM")
        self.w(":WAV:FORM BYTE")
        pre = [float(x) for x in self.q(":WAV:PRE?").split(",")]
        _fmt, _typ, _pts, _cnt, xinc, xorig, xref, yinc, yorig, yref = pre
        raw = np.frombuffer(self.block(":WAV:DATA?"), dtype=np.uint8)
        v = (raw.astype(np.float64) - yorig - yref) * yinc
        t = (np.arange(raw.size) - xref) * xinc + xorig
        return t, v, raw

    def screenshot_bmp(self, white: bool = False) -> bytes:
        return self.block(f":DISP:DATA? ON,{'ON' if white else 'OFF'},PNG")  # the MSO5000 answers with a BMP

    def settle(self, seconds: float) -> None:
        time.sleep(seconds)


@contextlib.contextmanager
def open_scope(cfg: dict | None = None):
    s = Scope(cfg)
    try:
        yield s
    finally:
        s.close()


def first_cross(t: np.ndarray, v: np.ndarray, level: float, rising: bool = True) -> float | None:
    """First crossing of `level` on the given slope, linearly interpolated."""
    above = v >= level if rising else v <= level
    idx = np.flatnonzero(~above[:-1] & above[1:])
    if idx.size == 0:
        return None
    i = int(idx[0])
    dv = v[i + 1] - v[i]
    frac = (level - v[i]) / dv if dv else 0.0
    return float(t[i] + frac * (t[i + 1] - t[i]))
