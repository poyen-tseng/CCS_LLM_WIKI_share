"""RIGOL MSO5000 series driver over LAN (pyvisa + pyvisa-py, raw SCPI socket on port 5555).

CLI usage (python -I rigol.py <cmd> ...):
    idn | status | shot [out.png] | wave <ch> [norm|raw] [max_points] | meas <item> <ch>
    q "<SCPI query>" | w "<SCPI command>"
"""
from __future__ import annotations

import json
import os
import struct
import sys
import time
import zlib
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pyvisa

HERE = Path(__file__).resolve().parent
CAPTURES = HERE / "captures"
DEFAULT_ADDR = "192.168.137.50"
RAW_CHUNK = 250_000  # max points per :WAV:DATA? read in BYTE format


def _resolve_resource(addr: str | None) -> str:
    addr = addr or os.environ.get("SCOPE_ADDR")
    if not addr:
        cfg = HERE / "config.json"
        if cfg.exists():
            addr = json.loads(cfg.read_text(encoding="utf-8")).get("addr")
    addr = addr or DEFAULT_ADDR
    return addr if "::" in addr else f"TCPIP0::{addr}::5555::SOCKET"


class ScopeError(RuntimeError):
    pass


@dataclass
class Waveform:
    channel: str
    mode: str
    t: np.ndarray
    v: np.ndarray
    xinc: float

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


def bmp_to_png(bmp: bytes) -> bytes:
    """Convert an uncompressed 24/32-bit BMP (what the MSO5000 returns) to PNG using only zlib."""
    if bmp[:2] != b"BM":
        return bmp  # already PNG or unknown; pass through
    offset = struct.unpack_from("<I", bmp, 10)[0]
    width, height = struct.unpack_from("<ii", bmp, 18)
    bpp = struct.unpack_from("<H", bmp, 28)[0]
    if bpp not in (24, 32):
        raise ScopeError(f"unsupported BMP bit depth {bpp}")
    bottom_up = height > 0
    height = abs(height)
    bytes_pp = bpp // 8
    stride = (width * bytes_pp + 3) & ~3
    rows = np.frombuffer(bmp, dtype=np.uint8, count=stride * height, offset=offset).reshape(height, stride)
    px = rows[:, : width * bytes_pp].reshape(height, width, bytes_pp)[:, :, 2::-1]  # BGR(A) -> RGB
    if bottom_up:
        px = px[::-1]
    raw = np.hstack([np.zeros((height, 1), np.uint8), px.reshape(height, width * 3)]).tobytes()

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b"")


class MSO5000:
    def __init__(self, addr: str | None = None, timeout_ms: int = 10000):
        self.resource = _resolve_resource(addr)
        self._rm = pyvisa.ResourceManager("@py")
        self.inst = self._rm.open_resource(
            self.resource, read_termination="\n", write_termination="\n", timeout=timeout_ms
        )

    def close(self) -> None:
        try:
            self.inst.close()
        finally:
            self._rm.close()

    def __enter__(self) -> "MSO5000":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # --- basic I/O -------------------------------------------------------
    def query(self, cmd: str) -> str:
        return self.inst.query(cmd).strip()

    def write(self, cmd: str, check: bool = True) -> None:
        self.inst.write(cmd)
        if check:
            self.check_error(cmd)

    def check_error(self, context: str = "") -> None:
        errors = []
        for _ in range(10):
            err = self.query(":SYST:ERR?")
            if err.startswith("0,"):
                break
            errors.append(err)
        if errors:
            raise ScopeError(f"{context}: {'; '.join(errors)}")

    def idn(self) -> str:
        return self.query("*IDN?")

    # --- acquisition control ---------------------------------------------
    def run(self) -> None:
        self.write(":RUN")

    def stop(self) -> None:
        self.write(":STOP")

    def single(self) -> None:
        self.write(":SING")

    def force_trigger(self) -> None:
        self.write(":TFOR")

    def autoscale(self) -> None:
        self.write(":AUT", check=False)
        time.sleep(3)  # autoscale takes a few seconds; queries during it may time out
        self.check_error(":AUT")

    def trigger_status(self) -> str:
        return self.query(":TRIG:STAT?")

    def wait_trigger(self, timeout_s: float = 10.0) -> str:
        """After single(): poll until the acquisition completes (STOP) or timeout."""
        end = time.time() + timeout_s
        st = self.trigger_status()
        while st != "STOP" and time.time() < end:
            time.sleep(0.1)
            st = self.trigger_status()
        return st

    # --- settings ---------------------------------------------------------
    def set_channel(self, ch: int, display: bool | None = None, scale: float | None = None,
                    offset: float | None = None, coupling: str | None = None,
                    probe: float | None = None, bwlimit: str | None = None) -> None:
        p = f":CHAN{ch}"
        if display is not None:
            self.write(f"{p}:DISP {1 if display else 0}")
        if probe is not None:  # set probe ratio before scale: scale is in probe-corrected volts
            self.write(f"{p}:PROB {probe:g}")
        if coupling is not None:
            self.write(f"{p}:COUP {coupling.upper()}")
        if bwlimit is not None:
            self.write(f"{p}:BWL {bwlimit.upper()}")
        if scale is not None:
            self.write(f"{p}:SCAL {scale:g}")
        if offset is not None:
            self.write(f"{p}:OFFS {offset:g}")

    def set_timebase(self, scale: float | None = None, offset: float | None = None) -> None:
        if scale is not None:
            self.write(f":TIM:MAIN:SCAL {scale:g}")
        if offset is not None:
            self.write(f":TIM:MAIN:OFFS {offset:g}")

    def set_trigger_edge(self, source: str | None = None, level: float | None = None,
                         slope: str | None = None, sweep: str | None = None) -> None:
        self.write(":TRIG:MODE EDGE")
        if source is not None:
            self.write(f":TRIG:EDGE:SOUR {source.upper()}")
        if slope is not None:
            self.write(f":TRIG:EDGE:SLOP {slope.upper()}")
        if level is not None:
            self.write(f":TRIG:EDGE:LEV {level:g}")
        if sweep is not None:
            self.write(f":TRIG:SWE {sweep.upper()}")

    def set_memory_depth(self, depth: str) -> None:
        """depth: AUTO, 1k, 10k, 100k, 1M, 10M, 25M, 50M, ... (scope must be running)."""
        self.write(f":ACQ:MDEP {depth}")

    def status(self) -> dict:
        q = self.query
        chans = {}
        for ch in range(1, 5):
            p = f":CHAN{ch}"
            chans[f"CHAN{ch}"] = {
                "display": q(f"{p}:DISP?") == "1",
                "scale_V_div": float(q(f"{p}:SCAL?")),
                "offset_V": float(q(f"{p}:OFFS?")),
                "coupling": q(f"{p}:COUP?"),
                "probe": float(q(f"{p}:PROB?")),
                "bwlimit": q(f"{p}:BWL?"),
            }
        return {
            "idn": self.idn(),
            "trigger_status": q(":TRIG:STAT?"),
            "timebase": {"scale_s_div": float(q(":TIM:MAIN:SCAL?")), "offset_s": float(q(":TIM:MAIN:OFFS?"))},
            "acquire": {"sample_rate_Sa_s": float(q(":ACQ:SRAT?")), "memory_depth": q(":ACQ:MDEP?")},
            "trigger": {
                "mode": q(":TRIG:MODE?"), "sweep": q(":TRIG:SWE?"),
                "edge_source": q(":TRIG:EDGE:SOUR?"), "edge_slope": q(":TRIG:EDGE:SLOP?"),
                "edge_level_V": float(q(":TRIG:EDGE:LEV?")),
            },
            "channels": chans,
        }

    # --- data -------------------------------------------------------------
    def measure(self, item: str, source: str | int = "CHAN1") -> float:
        src = _source(source)
        val = float(self.query(f":MEAS:ITEM? {item.upper()},{src}"))
        if abs(val) >= 9.9e37:  # RIGOL returns 9.9E37 when the measurement is invalid
            raise ScopeError(f"measurement {item} on {src} invalid (no signal / out of range)")
        return val

    def screenshot(self) -> bytes:
        """Return a PNG of the current screen."""
        data = self.inst.query_binary_values(":DISP:DATA? ON,OFF,PNG", datatype="B", container=bytes)
        return bmp_to_png(data)

    def waveform(self, source: str | int = "CHAN1", mode: str = "NORM", max_points: int | None = None) -> Waveform:
        """NORM: screen data (1000 pts, works while running). RAW: memory data, stops the scope."""
        src = _source(source)
        mode = mode.upper()
        if mode == "RAW":
            self.stop()
        self.write(f":WAV:SOUR {src}")
        self.write(f":WAV:MODE {mode}")
        self.write(":WAV:FORM BYTE")
        pre = [float(x) for x in self.query(":WAV:PRE?").split(",")]
        _fmt, _typ, points, _cnt, xinc, xorig, xref, yinc, yorig, yref = pre
        points = int(points)
        if max_points:
            points = min(points, int(max_points))
        chunks = []
        start = 1
        old_timeout = self.inst.timeout
        self.inst.timeout = max(old_timeout, 30000)
        try:
            while start <= points:
                stop = min(start + RAW_CHUNK - 1, points)
                self.write(f":WAV:STAR {start}")
                self.write(f":WAV:STOP {stop}")
                chunks.append(self.inst.query_binary_values(":WAV:DATA?", datatype="B", container=np.array))
                start = stop + 1
        finally:
            self.inst.timeout = old_timeout
        raw = np.concatenate(chunks).astype(np.float64) if chunks else np.array([])
        v = (raw - yorig - yref) * yinc
        t = (np.arange(raw.size) - xref) * xinc + xorig
        return Waveform(src, mode, t, v, xinc)


def _source(source: str | int) -> str:
    """Accept 1, "1", "chan1", "CHAN1", "MATH1", ... and return the SCPI source name."""
    src = str(source).upper()
    return f"CHAN{src}" if src.isdigit() else src


def _stamp() -> str:
    return time.strftime("%Y%m%d_%H%M%S")


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 1
    cmd, *args = argv
    with MSO5000() as s:
        if cmd == "idn":
            print(s.idn())
        elif cmd == "status":
            print(json.dumps(s.status(), indent=2, ensure_ascii=False))
        elif cmd == "shot":
            out = Path(args[0]) if args else CAPTURES / f"{_stamp()}_screen.png"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(s.screenshot())
            print(out)
        elif cmd == "wave":
            ch = args[0] if args else "CHAN1"
            mode = args[1] if len(args) > 1 else "NORM"
            maxp = int(args[2]) if len(args) > 2 else None
            w = s.waveform(ch, mode, maxp)
            path = w.save_csv(CAPTURES / f"{_stamp()}_{w.channel}_{w.mode}.csv")
            print(json.dumps({**w.stats(), "csv": str(path)}, indent=2))
        elif cmd == "meas":
            print(s.measure(args[0], args[1] if len(args) > 1 else "CHAN1"))
        elif cmd == "q":
            print(s.query(args[0]))
        elif cmd == "w":
            s.write(args[0])
            print("ok")
        else:
            print(__doc__)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
