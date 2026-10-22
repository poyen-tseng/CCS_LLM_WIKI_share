"""Timer0 hardware acceptance and matched baseline/optimized workflow timings.

Run from the JEV venv: python bench/timer_flow.py --mode optimized --runs 5
Requires GPIO0 on RIGOL CH1, 10x probe, GND, and a built TIMER0_EX RAM project.
"""
from __future__ import annotations

import argparse
import csv
import contextlib
import datetime
import hashlib
import io
import json
import math
import socket
import statistics
import time
from pathlib import Path

from PIL import Image, ImageOps

from jev_accel import tools, tools_ccs
from jev_accel.config import RESULTS, load_config
from jev_accel.scope_io import open_scope
from jev_accel.rules import menu as menu_rules

ITEMS = ("FREQ", "PER", "PWID", "NWID", "PDUT", "VTOP", "VBASE")
SETTINGS = (":CHAN1:DISP ON", ":CHAN1:PROB 10", ":CHAN1:COUP DC", ":CHAN1:VERN OFF",
            ":CHAN1:SCAL 1", ":CHAN1:OFFS -1.65", ":TIM:MAIN:SCAL 0.1", ":TIM:MAIN:OFFS 0",
            ":TRIG:MODE EDGE", ":TRIG:EDGE:SOUR CHAN1", ":TRIG:EDGE:SLOP POS",
            ":TRIG:EDGE:LEV 1.65", ":TRIG:SWE NORM", ":MEAS:CLE ALL")


def acceptance(values):
    """Electrical levels are recorded for review; TASK gives no numeric voltage tolerance."""
    if any(values.get(k) is None or not math.isfinite(values[k]) for k in ITEMS):
        return False
    return (abs(values["FREQ"] / 2.5 - 1) <= .01 and abs(values["PER"] / .4 - 1) <= .01
            and abs(values["PWID"] / .2 - 1) <= .01 and abs(values["NWID"] / .2 - 1) <= .01
            and 49 <= values["PDUT"] <= 51)


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


class Experiment:
    def __init__(self, mode, output, nodelay=False):
        self.mode, self.output, self.nodelay = mode, Path(output), nodelay
        self.output.mkdir(parents=True, exist_ok=True)
        self.cfg = load_config()
        require(self.cfg["scope"]["model"] == "rigol", "set SCOPE_MODEL=rigol")
        self.counts = {"scope_connections": 0, "scope_commands": 0, "ccs_calls": 0, "wait_s": 0.0}
        self.stages = {}

    @contextlib.contextmanager
    def scope(self):
        self.counts["scope_connections"] += 1
        with open_scope(self.cfg) as sc:
            sc.consume_block_terminator = self.mode == "optimized"
            sc.s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, int(self.nodelay))
            for name in ("q", "w", "block"):
                method = getattr(sc, name)
                def counted(*args, _method=method, **kwargs):
                    self.counts["scope_commands"] += 1
                    return _method(*args, **kwargs)
                setattr(sc, name, counted)
            yield sc

    def wait(self, seconds):
        self.counts["wait_s"] += seconds
        time.sleep(seconds)

    def ccs(self, fn, *args, **kwargs):
        self.counts["ccs_calls"] += 1
        return fn(*args, **kwargs)

    def stage(self, name, fn):
        start = time.perf_counter()
        try:
            return fn()
        finally:
            self.stages[name] = time.perf_counter() - start

    def configure(self, sc):
        for cmd in SETTINGS:
            sc.w(cmd)
        sc.w(":RUN")
        # At 100 ms/div fill the entire one-second display with new data.
        self.wait(1.5 if self.mode == "baseline" else 1.0)
        got = [sc.qf(q) for q in sc.dialect.readback_queries("CHAN1")]
        require(all(math.isclose(a, b, rel_tol=1e-6, abs_tol=1e-6)
                    for a, b in zip(got, (10, 1, -1.65, 1.65, .1, 0))), f"settings readback: {got}")

    def capture(self, sc):
        sc.w(":SING")
        self.wait(.05)
        until = time.perf_counter() + 5
        while time.perf_counter() < until:
            if sc.q(":TRIG:STAT?").upper() == "STOP":
                return
            self.wait(.05)
        raise TimeoutError("fresh single capture did not finish in 5 seconds")

    def check(self, sc):
        delay = self.cfg["frame"]["settle_s"] if self.mode == "baseline" else 0
        self.wait(delay)
        self.frame_input = tools.read_frame(sc, view="period")
        out = tools.decide_frame(self.frame_input, cfg=sc.cfg)
        if out['next_fix'] == 'hide_menu':
            sc.w(sc.dialect.hide_menu)
            self.wait(.8)
            self.frame_input.menu_rows = menu_rules.stats(menu_rules.bmp_to_array(sc.screenshot_bmp()), sc.cfg)['hit_rows']
            out = tools.decide_frame(self.frame_input, cfg=sc.cfg)
        out['measurements'] = {'PER': self.frame_input.period_s, 'VTOP': self.frame_input.vtop, 'VBASE': self.frame_input.vbase}
        require(out["ready"], f"frame rejected: {out}")
        return out

    def measure(self, sc, frame):
        cached = frame["measurements"] if self.mode == "optimized" else {}
        values = {k: cached[k] if k in cached else sc.measure(k) for k in ITEMS}
        # MSO5104 firmware 00.01.03.03.00 reports PDUT as a fraction, not percent.
        if values['PDUT'] is not None:
            values['PDUT_raw'] = values['PDUT']
            values['PDUT'] *= 100
        require(acceptance(values), f"Timer measurement rejected: {values}")
        # Measurement queries add overlays; clear them and recheck the menu before the report screenshot.
        sc.w(":MEAS:CLE ALL")
        return values

    def screenshot(self, sc, path):
        require(sc.q(":TRIG:STAT?").upper() == "STOP", "capture changed before screenshot")
        raw = sc.screenshot_bmp()
        # RIGOL measurement queries reopen Measure even after an earlier menu check.
        rows = menu_rules.stats(menu_rules.bmp_to_array(raw), sc.cfg)['hit_rows']
        if rows > sc.cfg['menu']['open_rows']:
            sc.w(sc.dialect.hide_menu)
            self.wait(.8)
            raw = sc.screenshot_bmp()
        self.frame_input.menu_rows = menu_rules.stats(menu_rules.bmp_to_array(raw), sc.cfg)['hit_rows']
        require(tools.decide_frame(self.frame_input, cfg=sc.cfg)['ready'], 'final screenshot menu/frame not ready')
        with Image.open(io.BytesIO(raw)) as img:
            ImageOps.invert(img.convert("RGB")).save(path)
        require('RIGOL' in sc.q('*IDN?'), 'block read misaligned subsequent IDN')
        require(sc.q(":SYST:ERR?").startswith("0,"), "SCPI error after capture")

    def run(self, index):
        self.stages = {}
        self.counts = dict.fromkeys(self.counts, 0)
        start = time.perf_counter()
        out = {"mode": self.mode, "index": index, "ok": False, "nodelay": self.nodelay}
        try:
            build = self.stage("build", lambda: self.ccs(tools_ccs.ccs_build, "TIMER0_EX"))
            require(build.get("result") == "ok" and build.get("map", {}).get("ok"), f"build failed: {build}")
            load = self.stage("load", lambda: self.ccs(tools_ccs.ccs_load, project="TIMER0_EX", run=True))
            require(load.get("state") == "flash_ok" and load.get("running"), f"RAM load failed: {load}")
            out.update(build=build, load=load)
            if self.mode == "optimized":
                with self.scope() as sc:
                    self.stage("configure", lambda: self.configure(sc))
                    self.stage("capture", lambda: self.capture(sc))
                    frame = self.stage("frame", lambda: self.check(sc))
                    values = self.stage("measure", lambda: self.measure(sc, frame))
                    self.stage("screenshot", lambda: self.screenshot(sc, self.output / f"{index}.png"))
            else:
                with self.scope() as sc:
                    self.stage("configure", lambda: self.configure(sc))
                with self.scope() as sc:
                    self.stage("capture", lambda: self.capture(sc))
                with self.scope() as sc:
                    frame = self.stage("frame", lambda: self.check(sc))
                with self.scope() as sc:
                    values = self.stage("measure", lambda: self.measure(sc, frame))
                with self.scope() as sc:
                    self.stage("screenshot", lambda: self.screenshot(sc, self.output / f"{index}.png"))
            out.update(ok=True, frame=frame, measurements=values)
        except Exception as exc:
            out["error"] = f"{type(exc).__name__}: {exc}"
        finally:
            out.update(elapsed_s=time.perf_counter() - start, stages_s=self.stages.copy(), counts=self.counts.copy())
            (self.output / f"{index}.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
        return out


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mode", choices=("baseline", "optimized"), required=True)
    p.add_argument("--runs", type=int, default=5)
    p.add_argument("--nodelay", action="store_true")
    p.add_argument("--output", type=Path)
    a = p.parse_args(argv)
    if a.runs < 1:
        p.error("runs must be positive")
    output = a.output or RESULTS / ('timer_' + time.strftime('%Y%m%d_%H%M%S') + '_' + a.mode)
    e = Experiment(a.mode, output, a.nodelay)
    rows = []
    try:
        env = tools_ccs.ccs_env()
        require(env['probe_present'], 'XDS110 not present')
        metadata = {k: env[k] for k in ('probe', 'probe_present', 'tools')}
        program = tools_ccs.project_dir('TIMER0_EX') / 'Debug/TIMER0_EX.out'
        metadata.update(date=datetime.datetime.now().astimezone().isoformat(), scope=e.cfg['scope'],
                        program_sha256=hashlib.sha256(program.read_bytes()).hexdigest() if program.exists() else None)
        (output / 'environment.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
        with e.scope() as sc:
            require('MSO5104' in sc.q('*IDN?'), 'unexpected scope model')
        # Hide only when the JEV menu detector sees an open menu; MOFF is a toggle.
        menu = tools.menu(hide=True, jev_mode='auto')
        (output / 'menu_preflight.json').write_text(json.dumps(menu, indent=2), encoding='utf-8')
        for i in range(a.runs):
            row = e.run(i)
            rows.append(row)
            print(json.dumps({k: row[k] for k in ('mode', 'index', 'ok', 'elapsed_s', 'stages_s', 'counts')}
                             | {k: row[k] for k in ('measurements', 'error') if k in row}), flush=True)
            if not row["ok"]:
                break
    finally:
        # Leave the board and scope running normally, and always release the probe.
        try:
            with e.scope() as sc:
                for cmd in SETTINGS:
                    sc.w(cmd)
                sc.w(":RUN")
        finally:
            release = tools_ccs.ccs_release()
            require(release.get("ok"), f"probe release failed: {release}")
    totals = [r['elapsed_s'] for r in rows if r['ok']]
    summary = {'mode': a.mode, 'runs': len(rows), 'passed': len(totals), 'output': str(output),
               'median_s': statistics.median(totals) if totals else None,
               'range_s': [min(totals), max(totals)] if totals else None}
    (output / 'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    with (output / 'measurements.csv').open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['mode', 'index', 'ok', 'elapsed_s', *ITEMS, 'PDUT_raw'])
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row[k] for k in ('mode', 'index', 'ok', 'elapsed_s')} | row.get('measurements', {}))
    print(json.dumps(summary), flush=True)
    return 0 if len(totals) == a.runs else 1


if __name__ == '__main__':
    raise SystemExit(main())
