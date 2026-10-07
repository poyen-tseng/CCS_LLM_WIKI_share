"""Capture one GPIO rising edge with Track cursors and save two screenshots.

Run edge_run.js first and wait for READY; this script arms the scope and then writes the go file.
"""
import argparse
import os
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from scope_lan import (DEFAULT_PORT, bmp_to_png, connect, default_addr, default_bind, drain, query,
                       read_block, waveform, write)

DEFAULT_GO = pathlib.Path(os.environ.get("TEMP", ".")) / "gpio_edge_go.txt"
DEFAULT_OUT_DIR = pathlib.Path(__file__).resolve().parent.parent / "captures"


def parse_args():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--addr", default=default_addr(), help="scope IP (default: SCOPE_ADDR, then ../config.json)")
    p.add_argument("--port", type=int, default=DEFAULT_PORT)
    p.add_argument("--bind", default=default_bind(),
                   help='local address to bind before connect (default: SCOPE_BIND or 192.168.137.1; "" = no bind)')
    p.add_argument("--vscale", type=float, default=0.6, help="CH1 V/div (default 0.6)")
    p.add_argument("--offset", type=float, default=-1.65, help="CH1 offset in V; negative moves the trace down")
    p.add_argument("--level", type=float, default=1.95, help="trigger level in V, 50%% of the real swing")
    p.add_argument("--tdiv", type=float, default=5e-9, help="time/div in s (default 5e-9)")
    p.add_argument("--go-file", type=pathlib.Path, default=DEFAULT_GO,
                   help="file edge_run.js waits for (default %%TEMP%%\\gpio_edge_go.txt)")
    p.add_argument("--out-dir", type=pathlib.Path, default=DEFAULT_OUT_DIR,
                   help="screenshot folder (default MCP/rigol-mso/captures)")
    p.add_argument("--prefix", default="GPIO0_rise", help="screenshot name prefix")
    p.add_argument("--reuse", action="store_true", help="skip configure/arm; reuse the frozen acquisition")
    p.add_argument("--config-only", action="store_true", help="configure the scope and exit")
    p.add_argument("--menu-off", action="store_true",
                   help="press MOFF before the first screenshot; it toggles, so use only when the menu is visible")
    return p.parse_args()


def cursor_at(s, which, t, tdiv):
    px = max(0, min(999, round(500 + t / (10 * tdiv) * 1000)))
    write(s, f":CURS:TRACk:C{which}X {px}")
    time.sleep(1.0)
    print(which, "pixel", px, "target", t, "got", query(s, f":CURS:TRACk:{which}XV?"))


def configure(s, a):
    write(s, ":STOP")
    write(s, ":CURS:MODE OFF")
    write(s, ":CHAN1:DISP ON")
    write(s, ":CHAN1:PROB 10")
    write(s, ":CHAN1:VERN ON" if a.vscale not in (0.5, 1.0) else ":CHAN1:VERN OFF")
    write(s, f":CHAN1:SCAL {a.vscale}")
    write(s, f":CHAN1:OFFS {a.offset}")
    write(s, f":TIM:MAIN:SCAL {a.tdiv:g}")
    write(s, ":TIM:MAIN:OFFS 0")
    write(s, ":TRIG:MODE EDGE")
    write(s, ":TRIG:EDGE:SOUR CHAN1")
    write(s, ":TRIG:EDGE:SLOP POS")
    write(s, ":TRIG:SWE NORM")
    write(s, f":TRIG:EDGE:LEV {a.level}")
    write(s, ":MEAS:CLEar ALL")
    write(s, ":MEAS:ITEM RTIM,CHAN1")
    time.sleep(0.5)
    for q in (":CHAN1:SCAL?", ":CHAN1:OFFS?", ":CHAN1:PROB?", ":TIM:MAIN:SCAL?", ":TIM:MAIN:OFFS?", ":TRIG:EDGE:LEV?"):
        print(q, query(s, q))


def arm_and_capture(s, go_file):
    write(s, ":SING")
    state = ""
    for i in range(40):
        state = query(s, ":TRIG:STAT?")
        if state == "WAIT":
            break
        time.sleep(0.1)
    if state != "WAIT":
        raise SystemExit("not armed " + state)
    time.sleep(0.1)
    if query(s, ":TRIG:STAT?") != "WAIT":
        raise SystemExit("lost wait")
    go_file.write_text("go\n", encoding="ascii")
    print("armed, go")
    t0 = time.time()
    final = "WAIT"
    while time.time() - t0 < 10:
        final = query(s, ":TRIG:STAT?")
        if final in ("STOP", "TD"):
            break
        time.sleep(0.05)
    print("FINAL", final)
    if final not in ("STOP", "TD"):
        raise SystemExit("no trigger")


def first_cross(times, vals, level):
    for i, v in enumerate(vals):
        if v >= level:
            return times[i]
    return None


def snap(s, out, menu_off=False):
    if menu_off:
        write(s, ":SYST:KEY:PRES MOFF")
    time.sleep(0.6)
    png = bmp_to_png(read_block(s, ":DISP:DATA? ON,OFF,PNG"))
    drain(s)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(png)
    print("saved", out, len(png))


def report(s):
    for q in (":CURS:TRACk:AXV?", ":CURS:TRACk:AYV?", ":CURS:TRACk:BXV?", ":CURS:TRACk:BYV?",
              ":CURS:TRACk:XDEL?", ":CURS:TRACk:YDEL?"):
        print(q, query(s, q))
    print("RTIM", query(s, ":MEAS:ITEM? RTIM,CHAN1"))


def main():
    a = parse_args()
    s = connect(a.addr, a.port, a.bind)
    if not a.reuse:
        configure(s, a)
        if a.config_only:
            s.close()
            return
        arm_and_capture(s, a.go_file)
    times, vals = waveform(s)
    lo = float(query(s, ":MEAS:ITEM? VBASe,CHAN1"))
    hi = float(query(s, ":MEAS:ITEM? VTOP,CHAN1"))
    amp = hi - lo
    t10 = first_cross(times, vals, lo + 0.1 * amp)
    t50 = first_cross(times, vals, lo + 0.5 * amp)
    t90 = first_cross(times, vals, lo + 0.9 * amp)
    print(f"low {lo:.3f} high {hi:.3f} t10 {t10*1e9:.2f}ns t50 {t50*1e9:.2f}ns t90 {t90*1e9:.2f}ns")
    print("screen x-range ns", times[0] * 1e9, times[-1] * 1e9)

    write(s, ":CURS:MODE TRACk")
    write(s, ":CURS:TRACk:SOUR1 CHAN1")
    write(s, ":CURS:TRACk:SOUR2 CHAN1")
    time.sleep(0.5)

    cursor_at(s, "A", t10, a.tdiv)
    cursor_at(s, "B", t90, a.tdiv)
    time.sleep(0.3)
    report(s)
    snap(s, a.out_dir / f"{a.prefix}_10_90.png", menu_off=a.menu_off)

    cursor_at(s, "A", t50 - 12e-9, a.tdiv)
    cursor_at(s, "B", 14e-9, a.tdiv)
    time.sleep(0.3)
    report(s)
    snap(s, a.out_dir / f"{a.prefix}_swing.png")
    s.close()


if __name__ == "__main__":
    main()
