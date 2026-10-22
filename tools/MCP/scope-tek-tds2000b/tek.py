"""Tektronix TDS2000B (TDS2014B) driver over USB (pyvisa + pyvisa-py USBTMC on a WinUSB-bound device).

Differences from the RIGOL / Keysight drivers that matter:
  * CH<n>:POSition is in divisions; the voltage at screen center is -position * scale.
  * errors come from *ESR? + ALLEV? (there is no :SYST:ERR?); headers are switched off on connect.
  * the run state comes from ACQ:STATE? and TRIG:STATE?; in NORM mode a trigger is detected from
    ACQ:NUMACQ? increasing.
  * waveforms are 2500-point records (CURVE?), volts = (raw - YOFF) * YMULT + YZERO.
  * there is no function generator; PROBE COMP (5 V, 1 kHz) is the self-test signal.

CLI usage (python -I tek.py <cmd> ...):
    list | idn | status | shot [out.png] [black] | wave <ch> | meas <item> <ch> | recover
    q "<SCPI query>" | w "<SCPI command>"
"""
from __future__ import annotations

import io
import json
import os
import sys
import time
import warnings
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pyvisa

# pyvisa-py's TCPIP discovery nags about psutil / zeroconf; only USB is used here
warnings.filterwarnings("ignore", module="pyvisa_py")

HERE = Path(__file__).resolve().parent
CAPTURES = HERE / "captures"
TEK_VID, TDS2014B_PID = 0x0699, 0x0368
INVALID = 9.9e37  # value the scope returns when a measurement cannot be made
RECORD = 2500  # points per waveform record

# RIGOL-style item names -> MEASU:IMM:TYP argument. Native types pass through unchanged.
# Firmware FV:v22.01 accepts only CRMS, FALL, FREQ, MAXI, MEAN, MINI, NWI, PERI, PK2, PWI, RIS, RMS
# (probed 2026-10-22); amplitude, high/low, overshoot, duty, delay and phase are rejected with error 102.
MEAS_ALIASES = {
    "FREQ": "FREQ", "PER": "PERI", "PERI": "PERI", "VPP": "PK2", "PK2": "PK2", "VMAX": "MAXI",
    "MAXI": "MAXI", "VMIN": "MINI", "MINI": "MINI", "VAVG": "MEAN", "MEAN": "MEAN", "VRMS": "RMS",
    "RMS": "RMS", "CRMS": "CRMS", "CRM": "CRMS", "RTIM": "RIS", "RIS": "RIS", "FTIM": "FALL",
    "FALL": "FALL", "PWID": "PWI", "PWI": "PWI", "NWID": "NWI", "NWI": "NWI",
}
# items the firmware lacks, computed as width / period in percent
DERIVED_DUTY = {"PDUT": "PWI", "NDUT": "NWI"}


def load_config() -> dict:
    cfg = {"resource": "auto"}
    for name in ("config.json", "config.local.json"):
        path = HERE / name
        if path.exists():
            cfg.update(json.loads(path.read_text(encoding="utf-8")))
    if os.environ.get("TEK_RESOURCE"):
        cfg["resource"] = os.environ["TEK_RESOURCE"]
    return cfg


def _is_tds(resource: str) -> bool:
    parts = resource.split("::")
    try:
        return int(parts[1], 0) == TEK_VID and int(parts[2], 0) == TDS2014B_PID
    except (IndexError, ValueError):
        return False


def _resolve_resource(rm: pyvisa.ResourceManager | None, resource: str | None = None) -> str:
    resource = resource or load_config()["resource"]
    if resource != "auto":
        return resource
    if rm is None:
        return "auto (USB VID 0x0699 PID 0x0368)"
    found = [r for r in rm.list_resources("USB?*INSTR") if _is_tds(r)]
    if not found:
        raise ScopeError("no TDS2014B on USB (VID 0x0699 PID 0x0368): check the cable, the power and that "
                         "WinUSB is bound to it (Zadig); Device Manager must not show a missing driver")
    return found[0]


class ScopeError(RuntimeError):
    pass


@dataclass
class Waveform:
    channel: str
    mode: str
    t: np.ndarray
    v: np.ndarray
    xinc: float
    raw: np.ndarray | None = None

    @property
    def sample_rate(self) -> float:
        return 1.0 / self.xinc if self.xinc else 0.0

    def stats(self) -> dict:
        v = self.v
        return {
            "channel": self.channel,
            "mode": self.mode,
            "points": int(v.size),
            "sample_interval_s": self.xinc,
            "sample_rate_Sa_s": self.sample_rate,
            "t_start_s": float(self.t[0]) if v.size else None,
            "t_end_s": float(self.t[-1]) if v.size else None,
            "v_min": float(v.min()) if v.size else None,
            "v_max": float(v.max()) if v.size else None,
            "v_mean": float(v.mean()) if v.size else None,
            "v_rms": float(np.sqrt(np.mean(v**2))) if v.size else None,
            "v_pp": float(v.max() - v.min()) if v.size else None,
        }

    def save_csv(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        np.savetxt(path, np.column_stack([self.t, self.v]), delimiter=",",
                   header="time_s,volt_V", comments="", fmt="%.9e")
        return path


class TDS2000B:
    def __init__(self, resource: str | None = None, timeout_ms: int = 5000):
        self._rm = pyvisa.ResourceManager("@py")
        self.warnings: list[str] = []  # 5xx warning events collected by errors()
        try:
            self.resource = _resolve_resource(self._rm, resource)
            self.inst = self._rm.open_resource(
                self.resource, read_termination="\n", write_termination="\n", timeout=timeout_ms
            )
        except Exception:
            self._rm.close()
            raise
        self.inst.write("HEAD OFF")
        self.errors()  # drop events left from an earlier session

    def close(self) -> None:
        try:
            self.inst.close()
        finally:
            self._rm.close()

    def __enter__(self) -> "TDS2000B":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # --- basic I/O -------------------------------------------------------
    def query(self, cmd: str, timeout_ms: int | None = None) -> str:
        if timeout_ms is None:
            return self.inst.query(cmd).strip()
        old = self.inst.timeout
        self.inst.timeout = timeout_ms
        try:
            return self.inst.query(cmd).strip()
        finally:
            self.inst.timeout = old

    def qf(self, cmd: str) -> float:
        return float(self.query(cmd))

    def write(self, cmd: str, check: bool = True) -> None:
        self.inst.write(cmd)
        if check:
            self.check_error(cmd)

    def errors(self) -> list[str]:
        """Command / execution / device errors (event codes 100-399) and lost queries (410 interrupted,
        420 unterminated, 430 deadlocked) since the last read. Warnings (5xx, e.g. 541 "low signal
        amplitude" after a measurement) do not count as errors; they are appended to self.warnings.
        *ESR? moves the pending events into the queue that ALLEV? reads."""
        esr = int(self.query("*ESR?"))
        if not esr & 0x3C:  # CME | EXE | DDE | QYE
            return []
        out = []
        events = self.query("ALLEV?")
        parsed = _split_events(events)
        for ev in parsed:
            code = int(ev.split(",", 1)[0])
            if 100 <= code < 400 or code in (410, 420, 430):
                out.append(ev)
            elif code >= 500:
                self.warnings.append(ev)
        return out if parsed else [f"*ESR? {esr}: {events}"]

    def check_error(self, context: str = "") -> None:
        errors = self.errors()
        if errors:
            raise ScopeError(f"{context}: {'; '.join(errors)}")

    def query_checked(self, cmd: str, timeout_ms: int = 2000) -> str:
        """A query that may be unsupported: the scope does not answer those, so use a short timeout
        and report the event queue instead of hanging."""
        try:
            return self.query(cmd, timeout_ms)
        except pyvisa.errors.VisaIOError as e:
            if e.error_code != pyvisa.constants.StatusCode.error_timeout:
                raise
            errs = self.errors()
            raise ScopeError(f"{cmd}: no reply within {timeout_ms} ms (unsupported query?) "
                             f"{'; '.join(errs) or 'no error event'}") from None

    def recover(self) -> None:
        """Reopen the USB session after a timeout (drops a half-read reply). pyvisa-py has no USBTMC
        device clear (inst.clear() raises), so reconnecting is the reset."""
        timeout = self.inst.timeout
        try:
            self.inst.close()
        except Exception:
            pass
        self.inst = self._rm.open_resource(self.resource, read_termination="\n", write_termination="\n",
                                           timeout=timeout)
        self.inst.write("HEAD OFF")
        self.errors()

    def idn(self) -> str:
        return self.query("*IDN?")

    # --- acquisition control ---------------------------------------------
    def run(self) -> None:
        self.write("ACQ:STOPA RUNST")
        self.write("ACQ:STATE RUN")

    def stop(self) -> None:
        self.write("ACQ:STATE STOP")

    def single(self) -> None:
        self.write("ACQ:STOPA SEQ")
        self.write("ACQ:STATE RUN")

    def force_trigger(self) -> None:
        self.write("TRIG FORC")

    def autoscale(self) -> None:
        self.write("AUTOS EXEC", check=False)
        self.wait_idle(20.0)
        self.check_error("AUTOS EXEC")

    def wait_idle(self, timeout_s: float = 10.0) -> None:
        """Wait until the scope finishes a long operation (autoset): *OPC? blocks until then."""
        self.query("*OPC?", timeout_ms=int(timeout_s * 1000))

    def acquiring(self) -> bool:
        return self.query("ACQ:STATE?") not in ("0", "STOP")

    def num_acq(self) -> int:
        return int(float(self.query("ACQ:NUMAC?")))

    def run_state(self, window_s: float = 0.25) -> str:
        """RIGOL-style trigger status: STOP; AUTO (auto mode, free-running); in NORM mode TD when an
        acquisition completes within window_s (ACQ:NUMACQ? increases), else WAIT."""
        if not self.acquiring():
            return "STOP"
        if self.query("TRIG:MAI:MOD?").upper().startswith("AUTO"):
            return "AUTO"
        n0 = self.num_acq()
        end = time.time() + window_s
        while True:
            time.sleep(0.03)
            if self.num_acq() != n0:
                return "TD"
            if not self.acquiring():
                return "STOP"  # a single sequence completed
            if time.time() >= end:
                return "WAIT"

    def wait_trigger(self, timeout_s: float = 10.0) -> str:
        """After single(): poll until the acquisition completes (STOP) or timeout (then WAIT)."""
        end = time.time() + timeout_s
        while self.acquiring():
            if time.time() >= end:
                return "WAIT"
            time.sleep(0.05)
        return "STOP"

    def ensure_data(self, what: str = "waveform / measurement") -> None:
        """Refuse a data read while NORM mode is armed and no trigger arrives: the scope would only
        return the old record (or nothing), which is easy to mistake for a live signal."""
        if self.run_state() == "WAIT":
            raise ScopeError(
                f"{what} refused: the trigger is armed in NORM mode and no trigger is arriving, so the data "
                "would be stale. Stop (tek_run_control stop) to read the last acquisition, force a trigger, "
                "fix the trigger level, or use mode AUTO.")

    # --- settings ---------------------------------------------------------
    def set_channel(self, ch: int, display: bool | None = None, scale: float | None = None,
                    position_div: float | None = None, offset_v_center: float | None = None,
                    coupling: str | None = None, probe: float | None = None, bwlimit: bool | None = None,
                    invert: bool | None = None, units: str | None = None) -> None:
        """position_div is the Tek setting (divisions); offset_v_center is converted to it as
        -offset / scale, using the scale after this call. units "V" uses the voltage probe ratio (probe),
        "A" the current probe ratio (CH<n>:CURRENTPRO, V/A); a voltage probe on a channel left in "A"
        reads in amps."""
        p = f"CH{ch}"
        if display is not None:
            self.write(f"SEL:{p} {'ON' if display else 'OFF'}")
        if units is not None:  # units before probe and scale: the scale is in the channel's units
            self.write(f'{p}:YUN "{units.upper()}"')
        if probe is not None:  # probe ratio first: scale and position are in probe-corrected volts
            self.write(f"{p}:PRO {probe:g}")
        if coupling is not None:
            self.write(f"{p}:COUP {coupling.upper()}")
        if bwlimit is not None:
            self.write(f"{p}:BANDW {'ON' if bwlimit else 'OFF'}")
        if invert is not None:
            self.write(f"{p}:INV {'ON' if invert else 'OFF'}")
        if scale is not None:
            self.write(f"{p}:SCA {scale:g}")
        if offset_v_center is not None:
            position_div = -offset_v_center / self.qf(f"{p}:SCA?")
        if position_div is not None:
            self.write(f"{p}:POS {position_div:g}")

    def set_timebase(self, scale: float | None = None, position: float | None = None) -> None:
        if scale is not None:
            self.write(f"HOR:MAI:SCA {scale:g}")
        if position is not None:
            self.write(f"HOR:MAI:POS {position:g}")

    def set_trigger_edge(self, source: str | None = None, level: float | None = None,
                         slope: str | None = None, mode: str | None = None, coupling: str | None = None,
                         holdoff: float | None = None) -> None:
        self.write("TRIG:MAI:TYP EDGE")
        if source is not None:
            self.write(f"TRIG:MAI:EDGE:SOU {_source(source)}")
        if slope is not None:
            self.write(f"TRIG:MAI:EDGE:SLO {slope.upper()}")
        if coupling is not None:
            self.write(f"TRIG:MAI:EDGE:COUP {coupling.upper()}")
        self._trigger_common(level, mode, holdoff)

    def set_trigger_pulse(self, source: str | None = None, level: float | None = None,
                          polarity: str | None = None, when: str | None = None, width: float | None = None,
                          mode: str | None = None, holdoff: float | None = None) -> None:
        """Pulse-width trigger. polarity POS / NEG (sent as POSITIVE / NEGATIVE: the firmware rejects
        abbreviations). when: EQ / NOTE (within / outside +-5 % of width), INS (narrower than width),
        OUT (wider than width)."""
        self.write("TRIG:MAI:TYP PUL")
        if source is not None:
            self.write(f"TRIG:MAI:PUL:SOU {_source(source)}")
        if polarity is not None:
            self.write(f"TRIG:MAI:PUL:WID:POL {'POSITIVE' if polarity.upper().startswith('POS') else 'NEGATIVE'}")
        if when is not None:
            self.write(f"TRIG:MAI:PUL:WID:WHEN {when.upper()}")
        if width is not None:
            self.write(f"TRIG:MAI:PUL:WID:WID {width:g}")
        self._trigger_common(level, mode, holdoff)

    def _trigger_common(self, level, mode, holdoff) -> None:
        if level is not None:
            self.write(f"TRIG:MAI:LEV {level:g}")
        if mode is not None:
            self.write(f"TRIG:MAI:MOD {mode.upper()}")
        if holdoff is not None:
            self.write(f"TRIG:MAI:HOLDO:VAL {holdoff:g}")

    def trigger_settings(self) -> dict:
        q = self.query
        typ = q("TRIG:MAI:TYP?")
        out = {"type": typ, "mode": q("TRIG:MAI:MOD?"), "level_V": float(q("TRIG:MAI:LEV?")),
               "holdoff_s": float(q("TRIG:MAI:HOLDO:VAL?")), "trig_state": q("TRIG:STATE?"),
               "run_state": self.run_state()}
        if typ.upper().startswith("PUL"):
            out.update(pulse_source=q("TRIG:MAI:PUL:SOU?"), pulse_polarity=q("TRIG:MAI:PUL:WID:POL?"),
                       pulse_when=q("TRIG:MAI:PUL:WID:WHEN?"), pulse_width_s=float(q("TRIG:MAI:PUL:WID:WID?")))
        else:
            out.update(edge_source=q("TRIG:MAI:EDGE:SOU?"), edge_slope=q("TRIG:MAI:EDGE:SLO?"),
                       edge_coupling=q("TRIG:MAI:EDGE:COUP?"))
        return out

    def channel_settings(self, ch: int) -> dict:
        q, p = self.query, f"CH{ch}"
        scale, pos = float(q(f"{p}:SCA?")), float(q(f"{p}:POS?"))
        return {
            "display": q(f"SEL:{p}?") in ("1", "ON"),
            "scale_V_div": scale,
            "position_div": pos,
            "offset_V_center": -pos * scale,
            "coupling": q(f"{p}:COUP?"),
            "units": q(f"{p}:YUN?").strip('"'),
            "probe": float(q(f"{p}:PRO?")),
            "bwlimit_20MHz": q(f"{p}:BANDW?") in ("1", "ON"),
            "invert": q(f"{p}:INV?") in ("1", "ON"),
        }

    def timebase_settings(self) -> dict:
        return {"scale_s_div": self.qf("HOR:MAI:SCA?"), "position_s": self.qf("HOR:MAI:POS?")}

    def status(self) -> dict:
        """About 4 s over USB (each query costs 50-120 ms)."""
        q = self.query
        chans = {f"CH{ch}": self.channel_settings(ch) for ch in range(1, 5)}
        trigger = self.trigger_settings()
        return {
            "idn": self.idn(),
            "run_state": trigger["run_state"],
            "timebase": self.timebase_settings(),
            "acquire": {"mode": q("ACQ:MOD?"), "averages": int(float(q("ACQ:NUMAV?"))),
                        "stop_after": q("ACQ:STOPA?"), "state": q("ACQ:STATE?"),
                        "record_points": RECORD},
            "trigger": trigger,
            "channels": chans,
        }

    # --- data -------------------------------------------------------------
    def measure(self, item: str, source: str | int = "CH1", check_live: bool = True) -> float:
        """check_live=False skips the WAIT guard (the caller already ran ensure_data()).
        PDUT / NDUT are derived from two measurements (width / period * 100). Warnings the scope raised
        for this value (e.g. 541 low signal amplitude) are left in self.warnings."""
        if check_live:
            self.ensure_data(f"measurement {item}")
        key = item.upper()
        if key in DERIVED_DUTY:
            width = self.measure(DERIVED_DUTY[key], source, check_live=False)
            width_warnings = list(self.warnings)
            period = self.measure("PERI", source, check_live=False)
            self.warnings[:0] = width_warnings
            return width / period * 100
        name = MEAS_ALIASES.get(key, key)
        src = _source(source)
        self.write(f"MEASU:IMM:SOU {src}")
        self.write(f"MEASU:IMM:TYP {name}")
        self.warnings.clear()
        val = float(self.query_checked("MEASU:IMM:VAL?", 5000))
        self.check_error(f"{item} on {src}")
        if abs(val) >= INVALID:
            raise ScopeError(f"measurement {item} on {src} invalid (no signal / out of range)")
        return val

    def screenshot(self, white: bool = True) -> bytes:
        """PNG of the screen (the scope sends a BMP hardcopy over USB; converted with Pillow).
        white=True uses Ink Saver (white background) for reports. Ink Saver, format and layout are the
        front-panel PRINT settings too, so the previous values are restored afterwards."""
        from PIL import Image as PILImage

        old = {"INKS": self.query("HARDC:INKS?"), "FORM": self.query("HARDC:FORM?"),
               "LAY": self.query("HARDC:LAY?")}
        new = {"INKS": "ON" if white else "OFF", "FORM": "BMP", "LAY": "PORTRAIT"}
        old_timeout = self.inst.timeout
        try:
            for key, value in new.items():
                if old[key] != value:
                    self.write(f"HARDC:{key} {value}")
            self.inst.timeout = 30000
            self.inst.write("HARDC STAR")
            bmp = self.inst.read_raw()
        finally:
            self.inst.timeout = old_timeout
            for key, value in old.items():
                if value != new[key]:
                    self.write(f"HARDC:{key} {value}")
        start = bmp.find(b"BM")
        if start < 0:
            raise ScopeError(f"hardcopy did not return a BMP ({len(bmp)} bytes: {bmp[:32]!r})")
        out = io.BytesIO()
        PILImage.open(io.BytesIO(bmp[start:])).save(out, format="PNG")
        return out.getvalue()

    def waveform(self, source: str | int = "CH1", check_live: bool = True) -> Waveform:
        """The 2500-point record of a displayed channel (or MATH / REFA..REFD)."""
        src = _source(source)
        if check_live:
            self.ensure_data("waveform")
        self.write(f"DAT:SOU {src}")
        self.write("DAT:ENC RIB")
        self.write("DAT:WID 1")
        self.write("DAT:STAR 1")
        self.write(f"DAT:STOP {RECORD}")
        q = self.qf
        xinc, pt_off, xzero = q("WFMP:XIN?"), q("WFMP:PT_O?"), q("WFMP:XZE?")
        ymult, yoff, yzero = q("WFMP:YMU?"), q("WFMP:YOF?"), q("WFMP:YZE?")
        old_timeout = self.inst.timeout
        self.inst.timeout = max(old_timeout, 20000)
        try:
            raw = self.inst.query_binary_values("CURV?", datatype="b", container=np.array)
        finally:
            self.inst.timeout = old_timeout
        raw = np.asarray(raw, dtype=np.int8)
        v = (raw.astype(np.float64) - yoff) * ymult + yzero
        t = (np.arange(raw.size) - pt_off) * xinc + xzero
        return Waveform(src, "RECORD", t, v, xinc, raw)


def _split_events(events: str) -> list[str]:
    """ALLEV? answer '113,"Undefined header; Command error; ...",0,"No events..."' -> one string per event."""
    out, i, n = [], 0, len(events)
    while i < n:
        j = events.find('"', i)
        if j < 0:
            break
        k = events.find('"', j + 1)
        while k >= 0 and events[k + 1:k + 2] == '"':  # doubled quotes inside the message
            k = events.find('"', k + 2)
        if k < 0:
            k = n
        code = events[i:j].strip(" ,")
        if code.lstrip("-").isdigit():
            out.append(f"{code},{events[j:k + 1]}")
        i = k + 1
    return out


def _source(source: str | int) -> str:
    """Accept 1, "1", "ch1", "CHAN1", "MATH", "REFA", "EXT", "LINE", ... and return the SCPI source name."""
    src = str(source).upper()
    if src.isdigit():
        return f"CH{src}"
    if src.startswith("CHAN"):
        return f"CH{src[4:]}"
    return src


def _stamp() -> str:
    return time.strftime("%Y%m%d_%H%M%S")


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 1
    cmd, *args = argv
    if cmd == "list":
        rm = pyvisa.ResourceManager("@py")
        print([r for r in rm.list_resources("USB?*INSTR")])
        return 0
    with TDS2000B() as s:
        if cmd == "idn":
            print(s.idn())
        elif cmd == "status":
            print(json.dumps(s.status(), indent=2, ensure_ascii=False))
        elif cmd == "shot":
            white = not (len(args) > 1 and args[1].lower() == "black")
            out = Path(args[0]) if args and args[0] != "-" else CAPTURES / f"{_stamp()}_screen.png"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(s.screenshot(white))
            print(out)
        elif cmd == "wave":
            w = s.waveform(args[0] if args else "CH1")
            path = w.save_csv(CAPTURES / f"{_stamp()}_{w.channel}.csv")
            print(json.dumps({**w.stats(), "csv": str(path)}, indent=2))
        elif cmd == "meas":
            print(s.measure(args[0], args[1] if len(args) > 1 else "CH1"), s.warnings or "")
        elif cmd == "recover":
            s.recover()
            print("recovered:", s.idn(), s.run_state())
        elif cmd == "q":
            print(s.query_checked(args[0]))
        elif cmd == "w":
            s.write(args[0])
            print("ok")
        else:
            print(__doc__)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
