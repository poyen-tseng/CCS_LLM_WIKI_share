"""Capture one rising edge with waveform markers and save two white-background screenshots (Keysight DSO-X 4034A).

Self-test without a board: --demo CLK drives the Demo 1 terminal (probe CH1 on Demo 1).
With the F280049C: run edge_run.js first, wait for READY, and pass --go-file; this script arms the scope
and then writes the go file.
"""
import argparse
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from ks_lan import DEFAULT_PORT, connect, default_addr, default_bind, errors, query, run_state, screenshot, waveform, write

DEFAULT_OUT_DIR = pathlib.Path(__file__).resolve().parent.parent / "captures"


def parse_args():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--addr", default=default_addr(), help="scope IP (default: KS_ADDR, then ../config.json)")
    p.add_argument("--port", type=int, default=DEFAULT_PORT)
    p.add_argument("--bind", default=default_bind(),
                   help='local address to bind before connect (default: KS_BIND or 192.168.137.1; "" = no bind)')
    p.add_argument("--channel", default="CHAN1")
    p.add_argument("--vscale", type=float, default=0.3, help="V/div (default 0.3; fine values set vernier)")
    p.add_argument("--center", type=float, default=1.05,
                   help="voltage at screen center in V (Keysight offset; 1.65 for 3.3 V GPIO, 1.05 for Demo CLK)")
    p.add_argument("--level", type=float, default=None, help="trigger level in V (default: --center)")
    p.add_argument("--tdiv", type=float, default=10e-9, help="time/div in s (default 10e-9)")
    p.add_argument("--demo", default="CLK", help='demo function to drive Demo 1 ("" = leave the demo output alone)')
    p.add_argument("--go-file", type=pathlib.Path, default=None,
                   help=r"file edge_run.js waits for, e.g. %%TEMP%%\gpio_edge_go.txt (default: none)")
    p.add_argument("--out-dir", type=pathlib.Path, default=DEFAULT_OUT_DIR,
                   help="screenshot folder (default tools/MCP/scope-keysight-dsox4000/captures)")
    p.add_argument("--prefix", default="edge_rise", help="screenshot name prefix")
    p.add_argument("--reuse", action="store_true", help="skip configure/arm; reuse the frozen acquisition")
    p.add_argument("--config-only", action="store_true", help="configure the scope and exit")
    return p.parse_args()


def configure(s, a):
    ch = a.channel
    if a.demo:
        write(s, f":DEMO:FUNC {a.demo}")
        write(s, ":DEMO:OUTP 1")
    write(s, ":RUN")
    write(s, ":MARK:MODE OFF")
    write(s, f":{ch}:DISP 1")
    write(s, f":{ch}:PROB 10")
    write(s, f":{ch}:VERN {0 if a.vscale in (0.1, 0.2, 0.5, 1.0, 2.0, 5.0) else 1}")
    write(s, f":{ch}:SCAL {a.vscale}")
    write(s, f":{ch}:OFFS {a.center}")
    write(s, f":TIM:SCAL {a.tdiv:g}")
    write(s, ":TIM:REF CENT")
    write(s, ":TIM:POS 0")
    write(s, ":TRIG:MODE EDGE")
    write(s, f":TRIG:EDGE:SOUR {ch}")
    write(s, ":TRIG:EDGE:SLOP POS")
    write(s, ":TRIG:SWE NORM")
    write(s, f":TRIG:EDGE:LEV {a.center if a.level is None else a.level}")
    time.sleep(0.5)
    for q in (f":{ch}:SCAL?", f":{ch}:OFFS?", f":{ch}:PROB?", ":TIM:SCAL?", ":TIM:POS?", ":TRIG:EDGE:LEV?"):
        print(q, query(s, q))
    errs = errors(s)
    if errs:
        raise SystemExit(f"scope errors after configure: {errs}")


def arm_and_capture(s, go_file):
    query(s, ":TER?")  # clear the trigger latch
    write(s, ":SING")
    state = ""
    for _ in range(40):
        state = run_state(s)
        if state in ("WAIT", "STOP"):
            break
        time.sleep(0.05)
    if go_file is not None:
        if state != "WAIT":
            raise SystemExit("not armed " + state)
        go_file.write_text("go\n", encoding="ascii")
        print("armed, go")
    t0 = time.time()
    while state != "STOP" and time.time() - t0 < 10:
        time.sleep(0.05)
        state = run_state(s)
    print("FINAL", state)
    if state != "STOP":
        raise SystemExit("no trigger")


def levels(vals, bins=64):
    lo_v, hi_v = min(vals), max(vals)
    width = (hi_v - lo_v) / bins or 1.0
    counts = [0] * bins
    for v in vals:
        counts[min(bins - 1, int((v - lo_v) / width))] += 1
    centers = [lo_v + (i + 0.5) * width for i in range(bins)]
    med = sorted(vals)[len(vals) // 2]
    low = max((c for c in zip(counts, centers) if c[1] <= med), default=(0, lo_v))[1]
    high = max((c for c in zip(counts, centers) if c[1] > med), default=(0, hi_v))[1]
    return low, high


def crossings(times, vals, level):
    out = []
    for i in range(len(vals) - 1):
        if vals[i] < level <= vals[i + 1]:
            dv = vals[i + 1] - vals[i]
            out.append(times[i] + (level - vals[i]) / dv * (times[i + 1] - times[i]))
    return out


def snap(s, out):
    time.sleep(0.4)
    png = screenshot(s, white=True)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(png)
    print("saved", out, len(png))


def report(s, ch):
    for q in (":MARK:X1P?", ":MARK:X2P?", ":MARK:Y1P?", ":MARK:Y2P?", ":MARK:XDEL?", ":MARK:YDEL?"):
        print(q, query(s, q))
    print("RIS", query(s, f":MEAS:RIS? {ch}"))


def main():
    a = parse_args()
    s = connect(a.addr, a.port, a.bind)
    ch = a.channel
    if not a.reuse:
        configure(s, a)
        if a.config_only:
            s.close()
            return
        arm_and_capture(s, a.go_file)
    times, vals = waveform(s, ch, 62500)
    lo, hi = levels(vals)
    amp = hi - lo
    c50 = crossings(times, vals, lo + 0.5 * amp)
    if not c50:
        raise SystemExit("no rising edge on screen")
    t50 = min(c50, key=abs)  # the edge at the trigger point
    t10 = max((t for t in crossings(times, vals, lo + 0.1 * amp) if t <= t50), default=None)
    t90 = min((t for t in crossings(times, vals, lo + 0.9 * amp) if t >= t50), default=None)
    if t10 is None or t90 is None:
        raise SystemExit("edge is not complete on screen; increase --tdiv")
    print(f"low {lo:.3f} high {hi:.3f} t10 {t10*1e9:.2f}ns t50 {t50*1e9:.2f}ns t90 {t90*1e9:.2f}ns")
    print("screen x-range ns", times[0] * 1e9, times[-1] * 1e9)

    write(s, ":MARK:MODE WAV")
    write(s, f":MARK:X1Y1 {ch}")
    write(s, f":MARK:X2Y2 {ch}")
    write(s, f":MARK:X1P {t10:g}")
    write(s, f":MARK:X2P {t90:g}")
    report(s, ch)
    snap(s, a.out_dir / f"{a.prefix}_10_90.png")

    write(s, ":MARK:MODE MAN")
    write(s, f":MARK:X1P {t50:g}")
    write(s, f":MARK:X2P {t50:g}")
    write(s, f":MARK:Y1P {lo:g}")
    write(s, f":MARK:Y2P {hi:g}")
    report(s, ch)
    snap(s, a.out_dir / f"{a.prefix}_swing.png")
    errs = errors(s)
    if errs:
        print("scope errors:", errs)
    s.close()


if __name__ == "__main__":
    main()
