"""Tektronix MSO2000 / DPO2000 (MSO2014) driver over USB (pyvisa + pyvisa-py USBTMC on a WinUSB-bound device).

Analog channels only; the 16 digital channels (P6316 probe) are not handled yet.
Differences from the RIGOL / Keysight / TDS2014B drivers that matter (probed on FV:v1.39, 2026-10-22):
  * CH<n>:OFFSet is a real volts offset and CH<n>:POSition is in divisions; the voltage at screen
    center is offset - position * scale. Probe attenuation is CH<n>:PRObe:GAIN = 1 / ratio.
  * errors come from *ESR? + ALLEV? (there is no :SYST:ERR?); headers are switched off on connect.
  * the run state comes from ACQ:STATE?, TRIG:A:MODe? and ACQ:NUMACQ? increasing.
  * waveforms: DATa:RESOlution REDUced gives ~5000 screen points, FULL the whole 125 k / 1 M record;
    volts = (raw - YOFF) * YMULT + YZERO from the WFMOutpre preamble.
  * a screenshot is HARDCopy START (full word: the abbreviation STAR is rejected with error 141), which
    returns a PNG over USB; SAVe:IMAGe:INKSaver chooses the white or black background.
  * a short-timeout query sent while AUTOSet runs wedges the USB link until the cable is replugged, so
    autoset waits with one long *OPC?.
  * there is no function generator; PROBE COMP (about 5 V, 1 kHz) is the self-test signal.

CLI usage (python -I mso.py <cmd> ...):
    list | idn | status | shot [out.png] [black] | wave <ch> [screen|full] [max_points]
    meas <item> <ch> [ch2] | recover | q "<SCPI query>" | w "<SCPI command>"
"""
from __future__ import annotations

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
TEK_VID, MSO2014_PID = 0x0699, 0x0377
INVALID = 9.9e37  # value the scope returns when a measurement cannot be made

# RIGOL-style item names -> MEASU:IMM:TYP argument. Native types pass through unchanged. Firmware v1.39
# also accepts AREA, BURST, CAREA, CMEAN, NEDGECOUNT, PEDGECOUNT, NPULSECOUNT, PPULSECOUNT (probed
# 2026-10-22); PK2 and TOVERSHOOT are rejected with error 141.
MEAS_ALIASES = {
    "FREQ": "FREQ", "PER": "PERI", "PERI": "PERI", "VPP": "PK2P", "PK2": "PK2P", "PK2P": "PK2P",
    "VMAX": "MAX", "MAX": "MAX", "VMIN": "MINI", "MINI": "MINI", "VAVG": "MEAN", "MEAN": "MEAN",
    "VRMS": "RMS", "RMS": "RMS", "CRMS": "CRMS", "VAMP": "AMP", "AMP": "AMP", "VTOP": "HIGH", "HIGH": "HIGH",
    "VBASE": "LOW", "LOW": "LOW", "RTIM": "RIS", "RIS": "RIS", "FTIM": "FALL", "FALL": "FALL",
    "PWID": "PWI", "PWI": "PWI", "NWID": "NWI", "NWI": "NWI", "PDUT": "PDU", "PDU": "PDU", "NDUT": "NDU",
    "NDU": "NDU", "OVER": "POV", "POV": "POV", "NOV": "NOV", "DEL": "DEL", "DELAY": "DEL", "PHAS": "PHA",
    "PHASE": "PHA", "PHA": "PHA",
}
TWO_SOURCE = {"DEL", "PHA"}


def load_config() -> dict:
    cfg = {"resource": "auto"}
    for name in ("config.json", "config.local.json"):
        path = HERE / name
        if path.exists():
            cfg.update(json.loads(path.read_text(encoding="utf-8")))
    if os.environ.get("MSO_RESOURCE"):
        cfg["resource"] = os.environ["MSO_RESOURCE"]
    return cfg


def _is_mso(resource: str) -> bool:
    parts = resource.split("::")
    try:
        return int(parts[1], 0) == TEK_VID and int(parts[2], 0) == MSO2014_PID
    except (IndexError, ValueError):
        return False


def _resolve_resource(rm: pyvisa.ResourceManager | None, resource: str | None = None) -> str:
    resource = resource or load_config()["resource"]
    if resource != "auto":
        return resource
    if rm is None:
        return "auto (USB VID 0x0699 PID 0x0377)"
    found = [r for r in rm.list_resources("USB?*INSTR") if _is_mso(r)]
    if not found:
        raise ScopeError("no MSO2014 on USB (VID 0x0699 PID 0x0377): check the cable, the power and that "
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


class MSO2000:
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

    def __enter__(self) -> "MSO2000":
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
        and report the event queue instead of hanging (about 2 s on this scope)."""
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
        device clear (inst.clear() raises). If even *IDN? then times out, the link is wedged and only
        replugging the USB cable helps."""
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
        """AUTOSet takes several seconds and the scope does not service USB meanwhile: wait with one long
        *OPC? (no error check in between, which would time out and wedge the link)."""
        self.write("AUTOS EXEC", check=False)
        self.wait_idle(30.0)
        self.check_error("AUTOS EXEC")

    def wait_idle(self, timeout_s: float = 10.0) -> None:
        """Wait until the scope finishes a long operation: *OPC? blocks until then."""
        self.query("*OPC?", timeout_ms=int(timeout_s * 1000))

    def acquiring(self) -> bool:
        return self.query("ACQ:STATE?") not in ("0", "STOP")

    def num_acq(self) -> int:
        return int(float(self.query("ACQ:NUMAC?")))

    def settle(self, delay_s: float = 0.4) -> None:
        """After a trigger, channel or timebase change: let the scope apply it and drop acquisitions that
        still used the old setting. Without this, ACQ:NUMACQ? counted stale triggers and run_state was wrong
        either way (seen 2026-10-22: pulse LESS 200 us reported TD, LESS 1 ms reported WAIT), and the first
        measurement after a V/div change carried the old setting's "low signal amplitude" warning."""
        self.wait_idle()
        time.sleep(delay_s)

    def run_state(self, window_s: float = 0.4) -> str:
        """RIGOL-style trigger status: STOP; AUTO (auto mode, free-running); in NORM mode TD when an
        acquisition completes within window_s (ACQ:NUMACQ? increases), else WAIT."""
        if not self.acquiring():
            return "STOP"
        if self.query("TRIG:A:MOD?").upper().startswith("AUTO"):
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
        return the old record, which is easy to mistake for a live signal."""
        if self.run_state() == "WAIT":
            raise ScopeError(
                f"{what} refused: the trigger is armed in NORM mode and no trigger is arriving, so the data "
                "would be stale. Stop (mso_run_control stop) to read the last acquisition, force a trigger, "
                "fix the trigger level, or use mode AUTO.")

    # --- settings ---------------------------------------------------------
    def set_channel(self, ch: int, display: bool | None = None, scale: float | None = None,
                    position_div: float | None = None, offset_v_center: float | None = None,
                    coupling: str | None = None, probe: float | None = None, bwlimit: bool | None = None,
                    invert: bool | None = None, units: str | None = None) -> None:
        """offset_v_center sets CH<n>:OFFSet to that voltage and the position to 0 divisions (unless
        position_div is also given), so the voltage shows at the center line. probe is the attenuation
        ratio (10 for a 10:1 probe), sent as CH<n>:PRObe:GAIN = 1 / ratio."""
        p = f"CH{ch}"
        if display is not None:
            self.write(f"SEL:{p} {'ON' if display else 'OFF'}")
        if units is not None:  # units before probe and scale: the scale is in the channel's units
            self.write(f'{p}:YUN "{units.upper()}"')
        if probe is not None:  # probe first: scale and offset are in probe-corrected volts
            self.write(f"{p}:PRO:GAIN {1 / probe:g}")
        if coupling is not None:
            self.write(f"{p}:COUP {coupling.upper()}")
        if bwlimit is not None:
            self.write(f"{p}:BAN {'TWE' if bwlimit else 'FUL'}")
        if invert is not None:
            self.write(f"{p}:INV {'ON' if invert else 'OFF'}")
        if scale is not None:
            self.write(f"{p}:SCA {scale:g}")
        if offset_v_center is not None:
            self.write(f"{p}:OFFS {offset_v_center:g}")
            if position_div is None:
                position_div = 0.0
        if position_div is not None:
            self.write(f"{p}:POS {position_div:g}")

    def set_timebase(self, scale: float | None = None, position_pct: float | None = None,
                     delay_s: float | None = None, record_length: int | None = None) -> None:
        """position_pct: where the trigger sits on screen (0-100 %, delay mode off).
        delay_s: time from the trigger to the screen center (turns delay mode on).
        record_length: 125000 or 1000000 points."""
        if record_length is not None:
            self.write(f"HOR:RECO {int(record_length)}")
        if scale is not None:
            self.write(f"HOR:SCA {scale:g}")
        if position_pct is not None:
            self.write("HOR:DEL:MOD OFF")
            self.write(f"HOR:POS {position_pct:g}")
        if delay_s is not None:
            self.write("HOR:DEL:MOD ON")
            self.write(f"HOR:DEL:TIM {delay_s:g}")

    def set_trigger_edge(self, source: str | None = None, level: float | None = None,
                         slope: str | None = None, mode: str | None = None, coupling: str | None = None,
                         holdoff: float | None = None) -> None:
        self.write("TRIG:A:TYP EDG")
        if source is not None:
            self.write(f"TRIG:A:EDGE:SOU {_source(source)}")
        if slope is not None:
            self.write(f"TRIG:A:EDGE:SLO {slope.upper()}")
        if coupling is not None:
            self.write(f"TRIG:A:EDGE:COUP {coupling.upper()}")
        self._trigger_common(level, mode, holdoff, self.query("TRIG:A:EDGE:SOU?"))

    def set_trigger_pulse(self, source: str | None = None, level: float | None = None,
                          polarity: str | None = None, when: str | None = None, width: float | None = None,
                          mode: str | None = None, holdoff: float | None = None) -> None:
        """Pulse-width trigger. polarity POS / NEG; when: LESS / MORE (narrower / wider than width),
        EQ / UNEQ (within / outside a tolerance around width)."""
        self.write("TRIG:A:TYP PULS")  # "PUL" is rejected (141)
        self.write("TRIG:A:PUL:CLA WID")
        if source is not None:
            self.write(f"TRIG:A:PULSEW:SOU {_source(source)}")
        if polarity is not None:
            self.write(f"TRIG:A:PULSEW:POL {'POS' if polarity.upper().startswith('POS') else 'NEG'}")
        if when is not None:
            self.write(f"TRIG:A:PULSEW:WHE {when.upper()}")
        if width is not None:
            self.write(f"TRIG:A:PULSEW:WID {width:g}")
        self._trigger_common(level, mode, holdoff, self.query("TRIG:A:PULSEW:SOU?"))

    def _trigger_common(self, level, mode, holdoff, source: str) -> None:
        if level is not None:  # the level is stored per source channel
            self.write(f"TRIG:A:LEV:{source} {level:g}")
        if mode is not None:
            self.write(f"TRIG:A:MOD {mode.upper()}")
        if holdoff is not None:
            self.write(f"TRIG:A:HOLD:TIM {holdoff:g}")

    def trigger_settings(self) -> dict:
        q = self.query
        typ = q("TRIG:A:TYP?")
        out = {"type": typ, "mode": q("TRIG:A:MOD?"), "holdoff_s": float(q("TRIG:A:HOLD:TIM?")),
               "trig_state": q("TRIG:STATE?"), "run_state": self.run_state()}
        if typ.upper().startswith("PUL"):
            src = q("TRIG:A:PULSEW:SOU?")
            out.update(pulse_class=q("TRIG:A:PUL:CLA?"), pulse_source=src,
                       pulse_polarity=q("TRIG:A:PULSEW:POL?"), pulse_when=q("TRIG:A:PULSEW:WHE?"),
                       pulse_width_s=float(q("TRIG:A:PULSEW:WID?")))
        else:
            src = q("TRIG:A:EDGE:SOU?")
            out.update(edge_source=src, edge_slope=q("TRIG:A:EDGE:SLO?"), edge_coupling=q("TRIG:A:EDGE:COUP?"))
        out["level_V"] = float(q(f"TRIG:A:LEV:{src}?")) if src.startswith("CH") else None
        return out

    def channel_settings(self, ch: int) -> dict:
        q, p = self.query, f"CH{ch}"
        scale, pos, offs = float(q(f"{p}:SCA?")), float(q(f"{p}:POS?")), float(q(f"{p}:OFFS?"))
        bandwidth = float(q(f"{p}:BAN?"))
        return {
            "display": q(f"SEL:{p}?") in ("1", "ON"),
            "scale_V_div": scale,
            "position_div": pos,
            "offset_V": offs,
            "center_V": offs - pos * scale,
            "coupling": q(f"{p}:COUP?"),
            "units": q(f"{p}:YUN?").strip('"'),
            "probe": round(1 / float(q(f"{p}:PRO:GAIN?")), 6),
            "bandwidth_Hz": bandwidth,
            "bwlimit_20MHz": bandwidth <= 20e6,
            "invert": q(f"{p}:INV?") in ("1", "ON"),
        }

    def timebase_settings(self) -> dict:
        q = self.query
        return {"scale_s_div": float(q("HOR:SCA?")), "position_pct": float(q("HOR:POS?")),
                "delay_mode": q("HOR:DEL:MOD?") in ("1", "ON"), "delay_s": float(q("HOR:DEL:TIM?")),
                "record_length": int(float(q("HOR:RECO?"))), "sample_rate_Sa_s": float(q("HOR:SAMPLER?"))}

    def status(self) -> dict:
        """About 1.5 s over USB (each query costs 25-50 ms)."""
        q = self.query
        chans = {f"CH{ch}": self.channel_settings(ch) for ch in range(1, 5)}
        trigger = self.trigger_settings()
        return {
            "idn": self.idn(),
            "run_state": trigger["run_state"],
            "timebase": self.timebase_settings(),
            "acquire": {"mode": q("ACQ:MOD?"), "averages": int(float(q("ACQ:NUMAV?"))),
                        "stop_after": q("ACQ:STOPA?"), "state": q("ACQ:STATE?")},
            "trigger": trigger,
            "channels": chans,
        }

    # --- data -------------------------------------------------------------
    def measure(self, item: str, source: str | int = "CH1", source2: str | int | None = None,
                check_live: bool = True) -> float:
        """check_live=False skips the WAIT guard (the caller already ran ensure_data()). DEL / PHAS use
        source2 (default CH2). Warnings the scope raised for this value (e.g. 541 low signal amplitude)
        are left in self.warnings."""
        if check_live:
            self.ensure_data(f"measurement {item}")
        name = MEAS_ALIASES.get(item.upper(), item.upper())
        src = _source(source)
        self.write(f"MEASU:IMM:SOU1 {src}")
        if name in TWO_SOURCE:
            self.write(f"MEASU:IMM:SOU2 {_source(source2 or 'CH2')}")
        self.write(f"MEASU:IMM:TYP {name}")
        self.warnings.clear()
        val = float(self.query_checked("MEASU:IMM:VAL?", 5000))
        self.check_error(f"{item} on {src}")
        if abs(val) >= INVALID:
            raise ScopeError(f"measurement {item} on {src} invalid (no signal / out of range)")
        return val

    def screenshot(self, white: bool = True) -> bytes:
        """PNG of the screen over USB (480 x 234, about 2.3 s). HARDCopy must be spelled out: "HARDC STAR"
        is rejected with 141 and nothing is sent. SAVe:IMAGe:INKSaver sets the background (HARDCopy:INKSaver
        has no effect); it and the file format are front-panel save settings too, so they are restored."""
        old = {"INKS": self.query("SAV:IMAG:INKS?"), "FILEF": self.query("SAV:IMAG:FILEF?")}
        new = {"INKS": "1" if white else "0", "FILEF": "PNG"}
        old_timeout = self.inst.timeout
        try:
            for key, value in new.items():
                if old[key] != value:
                    self.write(f"SAV:IMAG:{key} {value}")
            self.inst.timeout = 30000
            self.inst.write("HARDC START")
            data = self.inst.read_raw()
        finally:
            self.inst.timeout = old_timeout
            for key, value in old.items():
                if value != new[key]:
                    self.write(f"SAV:IMAG:{key} {value}")
        start = data.find(b"\x89PNG")
        if start < 0:
            raise ScopeError(f"HARDC START did not return a PNG ({len(data)} bytes: {data[:32]!r})")
        return data[start:]

    def waveform(self, source: str | int = "CH1", mode: str = "SCREEN", max_points: int | None = None,
                 check_live: bool = True) -> Waveform:
        """SCREEN: the reduced record (~5000 points, DATa:RESOlution REDUced). FULL: the whole record
        (125 k or 1 M points; max_points keeps the first max_points). The channel must be displayed."""
        src = _source(source)
        mode = mode.upper()
        if check_live:
            self.ensure_data("waveform")
        self.write(f"DAT:SOU {src}")
        self.write("DAT:ENC RIB")
        self.write("DAT:WID 1")
        self.write(f"DAT:RESO {'FULL' if mode == 'FULL' else 'REDU'}")
        self.write("DAT:STAR 1")
        self.write(f"DAT:STOP {int(max_points) if max_points else 1000000000}")
        q = self.qf
        xinc, pt_off, xzero = q("WFMO:XIN?"), q("WFMO:PT_O?"), q("WFMO:XZE?")
        ymult, yoff, yzero = q("WFMO:YMU?"), q("WFMO:YOF?"), q("WFMO:YZE?")
        old_timeout = self.inst.timeout
        self.inst.timeout = max(old_timeout, 60000)
        try:
            raw = self.inst.query_binary_values("CURV?", datatype="b", container=np.array)
        finally:
            self.inst.timeout = old_timeout
            self.write("DAT:RESO FULL")
        raw = np.asarray(raw, dtype=np.int8)
        v = (raw.astype(np.float64) - yoff) * ymult + yzero
        t = (np.arange(raw.size) - pt_off) * xinc + xzero
        return Waveform(src, mode, t, v, xinc, raw)


def _split_events(events: str) -> list[str]:
    """ALLEV? answer '113,"Undefined header; ...",0,"No events..."' -> one string per event."""
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
    """Accept 1, "1", "ch1", "CHAN1", "MATH", "REF1", "LINE", ... and return the SCPI source name."""
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
    with MSO2000() as s:
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
            w = s.waveform(args[0] if args else "CH1", args[1] if len(args) > 1 else "SCREEN",
                           int(args[2]) if len(args) > 2 else None)
            path = w.save_csv(CAPTURES / f"{_stamp()}_{w.channel}_{w.mode}.csv")
            print(json.dumps({**w.stats(), "csv": str(path)}, indent=2))
        elif cmd == "meas":
            print(s.measure(args[0], args[1] if len(args) > 1 else "CH1", args[2] if len(args) > 2 else None),
                  s.warnings or "")
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
