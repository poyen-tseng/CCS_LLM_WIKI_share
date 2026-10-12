"""Short-lived SCPI connections to the lab scope: RIGOL MSO5104 or Keysight DSO-X 4034A (config scope.model).

The raw-socket helpers are reused from the MCP folders:
  RIGOL:    CCS_LLM_WIKI_share/MCP/scope-rigol-mso5000/tools/scope_lan.py    (port 5555)
  Keysight: CCS_LLM_WIKI_share/MCP/scope-keysight-dsox4000/tools/ks_lan.py   (port 5025)
Both bind to 192.168.137.1 so Windows does not route the scope subnet through Wi-Fi. Each tool call opens
and closes its own socket, so a long-lived scope MCP is not blocked for long.

The rules (rules/frame.py, rules/autoframe.py) use the RIGOL conventions: offset = -(screen-center volts),
trigger status words TD / WAIT / RUN / AUTO / STOP. A Dialect turns semantic reads and settings into the
model's SCPI and converts back, so the rules and their fixtures stay model independent.
"""
from __future__ import annotations

import contextlib
import importlib.util
import sys
import time
from pathlib import Path

import numpy as np

from .config import load_config


class RigolDialect:
    """RIGOL MSO5000 SCPI (the default: test doubles without a `dialect` attribute speak RIGOL)."""

    name = "rigol"
    idn_vendors = ("RIGOL",)
    min_tdiv = 5e-9  # MSO5104 fastest timebase
    hide_menu: str | None = ":SYST:KEY:PRES MOFF"  # toggles: only send when the menu is known to be open
    clear_meas = ":MEAS:CLE ALL"

    # settings -> SCPI
    def cmd_probe(self, ch: str, ratio: float) -> str:
        return f":{ch}:PROB {ratio:g}"

    def cmd_vernier(self, ch: str, on: bool) -> str:
        return f":{ch}:VERN {'ON' if on else 'OFF'}"

    def cmd_vdiv(self, ch: str, vdiv: float) -> str:
        return f":{ch}:SCAL {vdiv:g}"

    def cmd_offset(self, ch: str, offset: float, fmt: str = "g") -> str:
        """offset in the rule convention (-center volts)."""
        return f":{ch}:OFFS {offset:{fmt}}"

    def cmd_trig_level(self, level: float, fmt: str = "g") -> str:
        return f":TRIG:EDGE:LEV {level:{fmt}}"

    def cmd_tdiv(self, tdiv: float) -> str:
        return f":TIM:MAIN:SCAL {tdiv:g}"

    def cmd_t_offset(self, t: float, fmt: str = ".4g") -> str:
        return f":TIM:MAIN:OFFS {t:{fmt}}"

    # reads (sc: an open scope with q / qf)
    def probe(self, sc, ch: str) -> float:
        return sc.qf(f":{ch}:PROB?")

    def vdiv(self, sc, ch: str) -> float:
        return sc.qf(f":{ch}:SCAL?")

    def offset(self, sc, ch: str) -> float:
        return sc.qf(f":{ch}:OFFS?")

    def tdiv(self, sc) -> float:
        return sc.qf(":TIM:MAIN:SCAL?")

    def t_offset(self, sc) -> float:
        return sc.qf(":TIM:MAIN:OFFS?")

    def trig_level(self, sc) -> float:
        return sc.qf(":TRIG:EDGE:LEV?")

    def trig_slope(self, sc) -> str:
        return sc.q(":TRIG:EDGE:SLOP?").upper()

    def trig_source(self, sc) -> str:
        return sc.q(":TRIG:EDGE:SOUR?").upper()

    def trig_status(self, sc) -> str:
        return sc.q(":TRIG:STAT?").upper()

    def sweep(self, sc) -> str:
        return sc.q(":TRIG:SWE?").upper()

    def readback_queries(self, ch: str) -> tuple[str, ...]:
        return (f":{ch}:PROB?", f":{ch}:SCAL?", f":{ch}:OFFS?", ":TRIG:EDGE:LEV?", ":TIM:MAIN:SCAL?",
                ":TIM:MAIN:OFFS?")


class KeysightDialect(RigolDialect):
    """Keysight InfiniiVision DSO-X 4000. :CHANn:OFFSet is the voltage at screen center (the RIGOL value
    negated); the timebase is :TIMebase:SCALe / :POSition; no SCPI closes a dialog or menu."""

    name = "keysight"
    idn_vendors = ("KEYSIGHT", "AGILENT")
    min_tdiv = 2e-9  # DSO-X 4034A (350 MHz): 1 ns/div is rejected with -222 (measured 2026-10-12)
    hide_menu = None
    clear_meas = ":MEAS:CLE"

    def cmd_offset(self, ch: str, offset: float, fmt: str = "g") -> str:
        return f":{ch}:OFFS {-offset + 0.0:{fmt}}"

    def cmd_tdiv(self, tdiv: float) -> str:
        return f":TIM:SCAL {tdiv:g}"

    def cmd_t_offset(self, t: float, fmt: str = ".4g") -> str:
        return f":TIM:POS {t:{fmt}}"

    def offset(self, sc, ch: str) -> float:
        return -sc.qf(f":{ch}:OFFS?")

    def tdiv(self, sc) -> float:
        return sc.qf(":TIM:SCAL?")

    def t_offset(self, sc) -> float:
        return sc.qf(":TIM:POS?")

    def trig_status(self, sc) -> str:
        """The state before prepare_read() touched the sweep, else live (TD / WAIT / AUTO / STOP)."""
        return getattr(sc, "state_before", None) or sc.lan.run_state(sc.s)

    def sweep(self, sc) -> str:
        return getattr(sc, "sweep_before", None) or sc.q(":TRIG:SWE?").upper()

    def readback_queries(self, ch: str) -> tuple[str, ...]:
        return (f":{ch}:PROB?", f":{ch}:SCAL?", f":{ch}:OFFS?", ":TRIG:EDGE:LEV?", ":TIM:SCAL?", ":TIM:POS?")


RIGOL = RigolDialect()
KEYSIGHT = KeysightDialect()
DIALECTS = {"rigol": RIGOL, "keysight": KEYSIGHT}

# RIGOL item names (what the rules and tools ask for) -> Keysight :MEASure header
KS_MEAS = {"VTOP": "VTOP", "VBASE": "VBAS", "VMAX": "VMAX", "VMIN": "VMIN", "RTIM": "RIS", "FTIM": "FALL",
           "VPP": "VPP", "FREQ": "FREQ", "PER": "PER", "VAMP": "VAMP", "PWID": "PWID", "NWID": "NWID"}


def dialect_of(sc) -> RigolDialect:
    return getattr(sc, "dialect", RIGOL)


def prepare_read(sc, peek: bool) -> None:
    """Call before reading levels or the waveform. Only the Keysight needs it (see KeysightScope)."""
    fn = getattr(sc, "prepare_read", None)
    if fn is not None:
        fn(peek)


def _load_module(name: str, path: Path, cfg_key: str):
    if not path.exists():
        raise FileNotFoundError(f"{path.name} not found at {path}; fix {cfg_key} in config.json")
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault(name, mod)
    spec.loader.exec_module(mod)
    return mod


class Scope:
    """RIGOL MSO5104 over scope_lan.py."""

    dialect: RigolDialect = RIGOL

    def __init__(self, cfg: dict | None = None):
        self.cfg = cfg or load_config()
        self.lan = self._load_lan()
        sc = self.cfg["scope"]
        try:
            self.s = self.lan.connect(sc["addr"], sc["port"], sc["bind"], timeout=sc["timeout_s"])
        except OSError:
            if not sc["bind"]:
                raise
            # the bind address is not on this PC (different NIC/IP): connect unbound
            self.s = self.lan.connect(sc["addr"], sc["port"], "", timeout=sc["timeout_s"])

    def _load_lan(self):
        return _load_module("scope_lan", Path(self.cfg["rigol_mso_dir"]) / "tools" / "scope_lan.py", "rigol_mso_dir")

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


class KeysightScope(Scope):
    """Keysight DSO-X 4034A over ks_lan.py. Same interface as Scope. On screen the raw bytes span 8..248 and
    clipped samples read 1 / 255 (measured 2026-10-12), so the RIGOL clip rule (<=3 / >=252) still holds."""

    dialect = KEYSIGHT
    state_before: str | None = None
    sweep_before: str | None = None
    blocked = False
    _restore_sweep: str | None = None

    def prepare_read(self, peek: bool) -> None:
        """While the trigger is armed in NORM sweep and nothing triggers, every waveform or measurement
        query blocks the scope until a trigger arrives (measured 2026-10-12). peek=False (check_frame)
        then skips those reads, so an armed single shot is never spoiled; peek=True (diagnose, autoframe)
        switches to AUTO sweep for the reads and restores NORM on close. trig_status and sweep keep
        reporting the state found here."""
        if self.state_before is None:
            self.sweep_before = self.q(":TRIG:SWE?").upper()
            self.state_before = self.lan.run_state(self.s)
        if self.state_before != "WAIT" or self._restore_sweep:
            return
        if peek:
            self.w(":TRIG:SWE AUTO")
            self._restore_sweep = ":TRIG:SWE NORM"
            self.blocked = False
            time.sleep(0.4)
        else:
            self.blocked = True

    def close(self) -> None:
        if self._restore_sweep:
            with contextlib.suppress(OSError):
                self.w(self._restore_sweep)
        super().close()

    def _load_lan(self):
        return _load_module("ks_lan", Path(self.cfg["keysight_dsox_dir"]) / "tools" / "ks_lan.py", "keysight_dsox_dir")

    def q(self, cmd: str) -> str:
        try:
            return self.lan.query(self.s, cmd)
        except TimeoutError:
            raise TimeoutError(
                f"{cmd}: no reply. The scope may be blocked on a query waiting for a trigger; unblock it with "
                f"{Path(self.cfg['keysight_dsox_dir']) / 'keysight.py'} recover") from None

    def block(self, cmd: str) -> bytes:
        return self.lan.read_block(self.s, cmd)  # ks_lan already consumes the trailing newline

    def measure(self, item: str, source: str = "CHAN1") -> float | None:
        if self.blocked:
            return None
        name = KS_MEAS.get(item.upper(), item.upper())
        try:
            v = self.qf(f":MEAS:{name}? {source}")
        except ValueError:
            return None
        return None if abs(v) >= 9.9e37 else v

    def waveform_raw(self, source: str = "CHAN1") -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Screen-resolution (NORM, up to 1000 pt) waveform: (t, volts, raw bytes); empty while blocked."""
        if self.blocked:
            return np.array([]), np.array([]), np.array([], dtype=np.uint8)
        t, v, raw = self.lan.waveform_raw(self.s, source, 1000)
        return np.asarray(t), np.asarray(v), np.frombuffer(raw, dtype=np.uint8)

    def screenshot_bmp(self, white: bool = False) -> bytes:
        return self.lan.screenshot(self.s, white)  # PNG; menu.bmp_to_array decodes it


@contextlib.contextmanager
def open_scope(cfg: dict | None = None):
    cfg = cfg or load_config()
    s = KeysightScope(cfg) if cfg["scope"].get("model", "rigol") == "keysight" else Scope(cfg)
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
