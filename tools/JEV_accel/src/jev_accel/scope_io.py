"""Short-lived SCPI connections to the lab scope: RIGOL MSO5104, Keysight DSO-X 4034A or Tektronix TDS2014B
(config scope.model; the TDS2014B is reached over USB through tools/MCP/scope-tek-tds2000b/tek.py).

The raw-socket helpers are reused from the MCP folders:
  RIGOL:    CCS_LLM_WIKI_share/tools/MCP/scope-rigol-mso5000/tools/scope_lan.py    (port 5555)
  Keysight: CCS_LLM_WIKI_share/tools/MCP/scope-keysight-dsox4000/tools/ks_lan.py   (port 5025)
Both bind to 192.168.137.1 so Windows does not route the scope subnet through Wi-Fi. Each tool call opens
and closes its own socket, so a long-lived scope MCP is not blocked for long.

The rules (rules/frame.py, rules/autoframe.py) use the RIGOL conventions: offset = -(screen-center volts),
trigger status words TD / WAIT / RUN / AUTO / STOP. A Dialect turns semantic reads and settings into the
model's SCPI and converts back, so the rules and their fixtures stay model independent.
"""
from __future__ import annotations

import contextlib
import importlib.util
import math
import os
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

    def cmd_offset(self, ch: str, offset: float, fmt: str = "g", vdiv: float | None = None) -> str:
        """offset in the rule convention (-center volts). vdiv (the V/div in effect when the command runs)
        is only needed by scopes that position in divisions (Tektronix)."""
        return f":{ch}:OFFS {offset:{fmt}}"

    def cmds_single(self) -> list[str]:
        """Arm one NORM single-shot capture."""
        return [":TRIG:SWE NORM", ":SING"]

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

    def cmd_offset(self, ch: str, offset: float, fmt: str = "g", vdiv: float | None = None) -> str:
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


def tek_channel(ch: str | int) -> str:
    """CHAN2 / chan2 / ch2 / 2 -> CH2 (TDS2014B source names); MATH, REFA ... pass through."""
    s = str(ch).upper()
    if s.isdigit():
        return f"CH{s}"
    if s.startswith("CHAN"):
        return f"CH{s[4:]}"
    return s


def same_channel(a: str, b: str) -> bool:
    """Trigger source vs measured channel across naming styles (CHAN2 == CH2)."""
    return tek_channel(a) == tek_channel(b)


def tek_tdiv(x: float) -> float:
    """TDS2014B timebases run 5 ns .. 50 s/div in a 1-2.5-5 sequence (the scope coerces 2e-4 to 2.5e-4,
    measured 2026-11-03); round up so the returned SCPI is what the readback shows."""
    dec = 10.0 ** math.floor(math.log10(x))
    for m in (1.0, 2.5, 5.0, 10.0):
        if m * dec >= x * (1 - 1e-9):
            return max(5e-9, min(50.0, round(m * dec, 12)))
    return 50.0


class TekDialect(RigolDialect):
    """Tektronix TDS2014B (firmware FV:v22.01) over USBTMC. CH<n>:POSition is in DIVISIONS and the voltage
    at screen center is -position * V/div, so in the rule convention (offset = -center volts)
    offset = position * V/div and position = offset / V/div. Fine V/div values (0.6, 0.7) are accepted
    directly, so there is no vernier command. The trigger mode (AUTO / NORMAL) plays the role of the sweep,
    single = ACQ:STOPA SEQ + ACQ:STATE RUN. No SCPI closes a menu or message, and immediate measurements
    leave no overlay on screen."""

    name = "tek"
    idn_vendors = ("TEKTRONIX",)
    min_tdiv = 5e-9
    hide_menu = None
    clear_meas = None

    def cmd_probe(self, ch: str, ratio: float) -> str:
        return f"{tek_channel(ch)}:PRO {ratio:g}"

    def cmd_vernier(self, ch: str, on: bool) -> str:
        return ""  # callers drop empty commands

    def cmd_vdiv(self, ch: str, vdiv: float) -> str:
        return f"{tek_channel(ch)}:SCA {vdiv:g}"

    def cmd_offset(self, ch: str, offset: float, fmt: str = "g", vdiv: float | None = None) -> str:
        if not vdiv:
            raise ValueError("the TDS2014B positions in divisions: pass the V/div in effect (vdiv=...)")
        return f"{tek_channel(ch)}:POS {offset / vdiv + 0.0:{fmt}}"

    def cmd_trig_level(self, level: float, fmt: str = "g") -> str:
        return f"TRIG:MAI:LEV {level:{fmt}}"

    def cmd_tdiv(self, tdiv: float) -> str:
        return f"HOR:MAI:SCA {tek_tdiv(tdiv):g}"

    def cmd_t_offset(self, t: float, fmt: str = ".4g") -> str:
        return f"HOR:MAI:POS {t:{fmt}}"

    def cmds_single(self) -> list[str]:
        return ["TRIG:MAI:MOD NORM", "ACQ:STOPA SEQ", "ACQ:STATE RUN"]

    def probe(self, sc, ch: str) -> float:
        return sc.qf(f"{tek_channel(ch)}:PRO?")

    def vdiv(self, sc, ch: str) -> float:
        return sc.qf(f"{tek_channel(ch)}:SCA?")

    def offset(self, sc, ch: str) -> float:
        c = tek_channel(ch)
        return sc.qf(f"{c}:POS?") * sc.qf(f"{c}:SCA?") + 0.0

    def tdiv(self, sc) -> float:
        return sc.qf("HOR:MAI:SCA?")

    def t_offset(self, sc) -> float:
        return sc.qf("HOR:MAI:POS?")

    def trig_level(self, sc) -> float:
        return sc.qf("TRIG:MAI:LEV?")

    def trig_slope(self, sc) -> str:
        return "NEGATIVE" if sc.q("TRIG:MAI:EDGE:SLO?").upper().startswith("FALL") else "POSITIVE"

    def trig_source(self, sc) -> str:
        return tek_channel(sc.q("TRIG:MAI:EDGE:SOU?"))

    def trig_status(self, sc) -> str:
        """The state found by prepare_read() (before it touched the trigger mode), else live."""
        return getattr(sc, "state_before", None) or sc.run_state()

    def sweep(self, sc) -> str:
        found = getattr(sc, "sweep_before", None)
        if found:
            return found
        return "AUTO" if sc.q("TRIG:MAI:MOD?").upper().startswith("AUTO") else "NORM"

    def readback_queries(self, ch: str) -> tuple[str, ...]:
        c = tek_channel(ch)
        return (f"{c}:PRO?", f"{c}:SCA?", f"{c}:POS?", "TRIG:MAI:LEV?", "HOR:MAI:SCA?", "HOR:MAI:POS?")


RIGOL = RigolDialect()
KEYSIGHT = KeysightDialect()
TEK = TekDialect()
DIALECTS = {"rigol": RIGOL, "keysight": KEYSIGHT, "tek": TEK}

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
        if getattr(self, "consume_block_terminator", False) and self.dialect.name == "rigol":
            return self.lan.read_block(self.s, cmd, consume_terminator=True)
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


TEK_LEVELS_PER_DIV = 25  # CURVE? int8 codes: 25 per division, screen = +-100 (4 div)
TEK_SCREEN_EDGE = 99  # |code| >= 99 touches the top / bottom graticule line (0.04 div margin)
TEK_WAVEFORM_ITEMS = ("VTOP", "VBASE", "VMAX", "VMIN", "VPP")


def tek_raw_to_u8(raw: np.ndarray) -> np.ndarray:
    """int8 CURVE? codes -> the 0..255 BYTE scale the rules use (rules/frame.py: clipped = <=3 or >=252).
    Measured 2026-11-03 on F280049C GPIO0 (0-3.3 V, 1 V/div): centred -41..43; 0 V half a division below
    the screen read -112 with correct volts (the ADC spans +-5.1 div, beyond the +-4 div screen), and a
    level beyond +5.1 div saturates at +127. code + 128 alone would flag only ADC saturation, so codes that
    reach the screen edge are mapped to 0 / 255 too: "clipped" keeps meaning "cut off in the screenshot"."""
    r = np.asarray(raw, dtype=np.int16)
    u = r + 128
    u[r >= TEK_SCREEN_EDGE] = 255
    u[r <= -TEK_SCREEN_EDGE] = 0
    return u.astype(np.uint8)


_TEK_BOOL = {"ON": "1", "OFF": "0", "RUN": "1", "STOP": "0"}


def tek_setting_matches(head: str, arg: str, reply: str) -> bool:
    """Does a TDS2014B readback already hold the argument? Numbers equal to 1 ppm, except channel position
    and trigger level within 0.021 (their 0.04-div / 0.02-div steps: CH2:POS -1.65 reads -1.64); quoted
    strings unquoted, booleans as 1/0 (SEL:CH2 ON -> 1, ACQ:STATE RUN -> 1), keywords by prefix
    (SAM -> SAMPLE, RIS -> RISE, NORM -> NORMAL)."""
    a, r = arg.strip().strip('"').upper(), reply.strip().strip('"').upper()
    h = head.upper()
    stepped = (h.startswith("CH") and h.endswith(":POS")) or h == "TRIG:MAI:LEV"
    try:
        return math.isclose(float(a), float(r), rel_tol=1e-6, abs_tol=0.021 if stepped else 1e-12)
    except ValueError:
        pass
    if a in _TEK_BOOL and r in ("0", "1"):
        return _TEK_BOOL[a] == r
    return bool(a) and r.startswith(a)


def levels_from_waveform(v: np.ndarray, min_swing: float) -> tuple[float | None, float | None]:
    """VTOP / VBASE (the TDS2014B firmware has no HIGH / LOW measurement): the medians of the samples
    above / below the midpoint of the extremes, which ignores overshoot and ringing like a histogram
    top / base. None for a flat trace (swing below min_swing), as the RIGOL reports an invalid value."""
    if v.size == 0:
        return None, None
    hi, lo = float(v.max()), float(v.min())
    if hi - lo < min_swing:
        return None, None
    mid = (hi + lo) / 2
    return float(np.median(v[v >= mid])), float(np.median(v[v < mid]))


class TekScope:
    """Tektronix TDS2014B over USB, reusing tools/MCP/scope-tek-tds2000b/tek.py (pyvisa-py, WinUSB).
    Same interface as Scope. Differences that matter:
      * w() does not wait for an error check (like the RIGOL socket); call errors() at checkpoints.
      * VTOP / VBASE / VMAX / VMIN / VPP come from the 2500-point record (one CURVE? read, about 0.5 s,
        cached until the next w()) instead of one MEASU:IMM:VAL? (~0.65-1.1 s) each; the firmware lacks
        VTOP / VBASE anyway. FREQ / PER / PWID / NWID / RTIM / FTIM are scope measurements.
      * prepare_read(): while NORM mode waits for a trigger the record is stale, so peek=False (check_frame)
        reads nothing and peek=True (diagnose, autoframe) switches the trigger mode to AUTO and restores
        NORM on close, like the Keysight backend; at >= 100 ms/div (where AUTO rolls in SCAN mode) it
        forces one NORM acquisition (TRIG FORC) instead.
      * Only one process can hold the USB device: close the tek MCP session first if opening fails."""

    dialect: TekDialect = TEK
    state_before: str | None = None
    sweep_before: str | None = None
    blocked = False
    _restore_mode: str | None = None
    _forced = False

    def __init__(self, cfg: dict | None = None):
        self.cfg = cfg or load_config()
        self.mod = _load_module("tek", Path(self.cfg["tek_tds_dir"]) / "tek.py", "tek_tds_dir")
        sc = self.cfg["scope"]
        resource = os.environ.get("TEK_RESOURCE") or sc.get("resource", "auto")
        self.tek = self.mod.TDS2000B(resource, int(sc.get("timeout_ms", 5000)))
        self._wave: dict[str, tuple] = {}
        self._meas_src: str | None = None
        self._dat_src: str | None = None

    # --- I/O --------------------------------------------------------------------------------------
    def close(self) -> None:
        try:
            if self._restore_mode:
                self.tek.inst.write(self._restore_mode)
        except Exception:
            pass
        finally:
            self.tek.close()

    def w(self, cmd: str) -> None:
        if not cmd:
            return
        self._wave.clear()  # settings or acquisition may change: the cached record is no longer current
        self.tek.inst.write(cmd)

    def q(self, cmd: str) -> str:
        return self.tek.query(cmd)

    def qf(self, cmd: str) -> float:
        return float(self.q(cmd))

    def block(self, cmd: str) -> bytes:
        self.tek.inst.write(cmd)
        return self.tek.inst.read_raw()

    def errors(self) -> list[str]:
        return self.tek.errors()

    def ensure(self, cmds) -> list[str]:
        """Send only the settings whose readback differs. A TDS2014B write costs 0.08-0.64 s even when the
        value does not change (CH2:COUP DC 0.64 s, TRIG:MAI:EDGE:COUP DC 0.54 s; 2026-11-03), a query
        ~0.06 s. Do not concatenate many commands into one message instead: an 18-command message wedged
        the USB link until a USBTMC INITIATE_CLEAR. Returns the commands actually written, in order."""
        sent = []
        for cmd in cmds:
            head, _, arg = cmd.partition(" ")
            if arg and not head.endswith("?") and tek_setting_matches(head, arg, self.q(f"{head}?")):
                continue
            self.w(cmd)
            sent.append(cmd)
        return sent

    def settle(self, seconds: float) -> None:
        time.sleep(seconds)

    # --- state ------------------------------------------------------------------------------------
    def _record_s(self) -> float:
        return 10 * self.dialect.tdiv(self)

    def run_state(self) -> str:
        """STOP / AUTO / TD / WAIT. In NORM mode a trigger shows as ACQ:NUMACQ? increasing; at slow
        timebases one acquisition takes the whole record (1 s at 100 ms/div), so the window grows with
        it (2 records + 0.25 s, capped at 3 s), and it is never shorter than 0.6 s: the 2.5 Hz Timer0
        square triggers only every 0.4 s, which a 0.25 s window would report as WAIT."""
        return self.tek.run_state(min(3.0, max(0.6, 2 * self._record_s() + 0.25)))

    def prepare_read(self, peek: bool) -> None:
        if self.state_before is None:
            self.sweep_before = "AUTO" if self.q("TRIG:MAI:MOD?").upper().startswith("AUTO") else "NORM"
            self.state_before = self.run_state()
        if self.state_before != "WAIT" or self._restore_mode or self._forced:
            return
        if peek and self._record_s() >= 1.0:
            # >= 100 ms/div: AUTO rolls (SCAN) and the half-filled record read VMAX/VMIN 3.36 / -3.48 V on
            # a 0-3.3 V square (2026-11-03). Force one full NORM acquisition instead; nothing to restore.
            n0 = self.tek.num_acq()
            self.tek.inst.write("TRIG FORC")
            end = time.time() + 1.5 * self._record_s() + 1.0
            while time.time() < end and self.tek.num_acq() == n0 and self.tek.acquiring():
                time.sleep(0.1)
            self._wave.clear()
            self._forced, self.blocked = True, False
        elif peek:
            self.w("TRIG:MAI:MOD AUTO")
            self._restore_mode = "TRIG:MAI:MOD NORM"
            self.blocked = False
            time.sleep(min(6.0, max(0.4, 1.2 * self._record_s() + 0.2)))  # let a free-running record fill
        else:
            self.blocked = True

    # --- data -------------------------------------------------------------------------------------
    def waveform_raw(self, source: str = "CH1") -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """The 2500-point record (10 div): (t, volts, raw on the 0..255 rule scale, see tek_raw_to_u8)."""
        if self.blocked:
            return np.array([]), np.array([]), np.array([], dtype=np.uint8)
        src = tek_channel(source)
        if src in self._wave:
            return self._wave[src][:3]
        inst = self.tek.inst
        if self._dat_src != src:
            for cmd in (f"DAT:SOU {src}", "DAT:ENC RIB", "DAT:WID 1", "DAT:STAR 1", f"DAT:STOP {self.mod.RECORD}"):
                inst.write(cmd)
            self._dat_src = src
        q = self.qf
        xinc, pt_off, xzero = q("WFMP:XIN?"), q("WFMP:PT_O?"), q("WFMP:XZE?")
        ymult, yoff, yzero = q("WFMP:YMU?"), q("WFMP:YOF?"), q("WFMP:YZE?")
        old = inst.timeout
        inst.timeout = max(old, 20000)
        try:
            codes = np.asarray(inst.query_binary_values("CURV?", datatype="b", container=np.array), dtype=np.int8)
        finally:
            inst.timeout = old
        v = (codes.astype(np.float64) - yoff) * ymult + yzero
        t = (np.arange(codes.size) - pt_off) * xinc + xzero
        raw = tek_raw_to_u8(codes)
        self._wave[src] = (t, v, raw, ymult)
        return t, v, raw

    def measure(self, item: str, source: str = "CH1") -> float | None:
        if self.blocked:
            return None
        key, src = item.upper(), tek_channel(source)
        if key in TEK_WAVEFORM_ITEMS:
            _, v, _ = self.waveform_raw(src)
            if not v.size:
                return None
            if key == "VMAX":
                return float(v.max())
            if key == "VMIN":
                return float(v.min())
            if key == "VPP":
                return float(v.max() - v.min())
            top, base = levels_from_waveform(v, 5 * self._wave[src][3])  # 5 codes = 0.2 div
            return top if key == "VTOP" else base
        if key in self.mod.DERIVED_DUTY:
            width, period = self.measure(self.mod.DERIVED_DUTY[key], src), self.measure("PER", src)
            return None if width is None or not period else width / period * 100  # percent, unlike the RIGOL
        name = self.mod.MEAS_ALIASES.get(key, key)
        if self._meas_src != src:
            self.tek.inst.write(f"MEASU:IMM:SOU {src}")
            self._meas_src = src
        self.tek.inst.write(f"MEASU:IMM:TYP {name}")
        try:
            val = float(self.tek.query_checked("MEASU:IMM:VAL?", 5000))
        except ValueError:
            return None
        return None if abs(val) >= self.mod.INVALID else val

    def screenshot_bmp(self, white: bool = True) -> bytes:
        """PNG (320x240) of the screen; white=True (default) uses native HARDC:INKS ON white background.
        A hardcopy right after another in the same session can time out (seen 2026-11-03): reopen and retry once."""
        try:
            return self.tek.screenshot(white)
        except Exception as exc:  # pyvisa timeout or a ScopeError raised while restoring HARDC settings
            if "Timeout" not in f"{type(exc).__name__}{exc}" and "VI_ERROR_TMO" not in str(exc):
                raise
            self.tek.recover()
            time.sleep(1.0)
            return self.tek.screenshot(white)


@contextlib.contextmanager
def open_scope(cfg: dict | None = None):
    cfg = cfg or load_config()
    model = cfg["scope"].get("model", "rigol")
    s = KeysightScope(cfg) if model == "keysight" else TekScope(cfg) if model == "tek" else Scope(cfg)
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
