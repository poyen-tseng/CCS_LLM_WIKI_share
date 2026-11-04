"""Timer0 hardware acceptance and matched baseline/optimized workflow timings.

Run from the JEV venv: python bench/timer_flow.py --mode optimized --runs 5 [--channel CH2]
Requires GPIO0 on a 10x probe (RIGOL MSO5104: CHAN1 by default; Tektronix TDS2014B with SCOPE_MODEL=tek:
pass the probed channel, e.g. --channel CH2), GND, and a built TIMER0_EX RAM project.
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
from jev_accel.scope_io import dialect_of, open_scope, tek_channel
from jev_accel.rules import menu as menu_rules

ITEMS = ("FREQ", "PER", "PWID", "NWID", "PDUT", "VTOP", "VBASE")
SETTINGS = (":CHAN1:DISP ON", ":CHAN1:PROB 10", ":CHAN1:COUP DC", ":CHAN1:VERN OFF",
            ":CHAN1:SCAL 1", ":CHAN1:OFFS -1.65", ":TIM:MAIN:SCAL 0.1", ":TIM:MAIN:OFFS 0",
            ":TRIG:MODE EDGE", ":TRIG:EDGE:SOUR CHAN1", ":TRIG:EDGE:SLOP POS",
            ":TRIG:EDGE:LEV 1.65", ":TRIG:SWE NORM", ":MEAS:CLE ALL")
# readback targets in readback_queries() order: probe, V/div, offset (Tek: position in div), level, s/div, delay
TARGETS = (10, 1, -1.65, 1.65, .1, 0)
IDN_MODEL = {"rigol": "MSO5104", "tek": "TDS 2014B"}


def settings(model="rigol", channel="CHAN1"):
    """The known Timer frame: 1 V/div, 1.65 V at screen center, 100 ms/div, rising edge at 1.65 V, NORM."""
    if model != "tek":
        return SETTINGS if channel == "CHAN1" else tuple(c.replace("CHAN1", channel) for c in SETTINGS)
    ch = tek_channel(channel)
    # CH<n>:POS is in divisions: -1.65 div * 1 V/div puts 1.65 V at screen center (rule offset -1.65)
    return (f"SEL:{ch} ON", f'{ch}:YUN "V"', f"{ch}:PRO 10", f"{ch}:COUP DC", f"{ch}:INV OFF", f"{ch}:SCA 1",
            f"{ch}:POS -1.65", "HOR:MAI:SCA 0.1", "HOR:MAI:POS 0", "ACQ:MOD SAM", "TRIG:MAI:TYP EDGE",
            f"TRIG:MAI:EDGE:SOU {ch}", "TRIG:MAI:EDGE:SLO RIS", "TRIG:MAI:EDGE:COUP DC", "TRIG:MAI:LEV 1.65",
            "TRIG:MAI:MOD NORM")


def run_cmds(model="rigol"):
    return ("ACQ:STOPA RUNST", "ACQ:STATE RUN") if model == "tek" else (":RUN",)


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
    def __init__(self, mode, output, nodelay=False, channel=None):
        self.mode, self.output, self.nodelay = mode, Path(output), nodelay
        self.output.mkdir(parents=True, exist_ok=True)
        self.cfg = load_config()
        self.model = self.cfg["scope"]["model"]
        require(self.model in IDN_MODEL, "set SCOPE_MODEL=rigol or SCOPE_MODEL=tek")
        self.channel = channel or "CHAN1"
        self.counts = {"scope_connections": 0, "scope_commands": 0, "ccs_calls": 0, "wait_s": 0.0}
        self.stages = {}

    @property
    def tek(self):
        return getattr(self, "model", "rigol") == "tek"

    @contextlib.contextmanager
    def scope(self):
        self.counts["scope_connections"] += 1
        with open_scope(self.cfg) as sc:
            sc.consume_block_terminator = self.mode == "optimized"
            if hasattr(sc, "s"):  # TCP scopes only; the TDS2014B is on USB
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

    def stopped(self, sc):
        return sc.q("ACQ:STATE?") == "0" if self.tek else sc.q(":TRIG:STAT?").upper() == "STOP"

    def configure(self, sc):
        cmds = settings(self.model, self.channel) + run_cmds(self.model)
        if self.tek and self.mode == "optimized":
            # a TDS2014B write costs 0.08-0.64 s even for an unchanged value, a query ~0.06 s
            self.written = sc.ensure(cmds)
        else:
            for cmd in cmds:
                sc.w(cmd)
        # At 100 ms/div fill the entire one-second display with new data.
        self.wait(1.5 if self.mode == "baseline" else 1.0)
        got = [sc.qf(q) for q in sc.dialect.readback_queries(self.channel)]
        # TDS2014B steps: position 0.04 div (-1.65 -> -1.64), trigger level 0.02 div (measured 2026-11-03)
        tol = .021 if self.tek else 1e-6
        require(all(math.isclose(a, b, rel_tol=1e-6, abs_tol=tol)
                    for a, b in zip(got, TARGETS)), f"settings readback: {got}")
        if self.tek:
            require(not sc.errors(), "SCPI error after configure")

    def capture(self, sc):
        for cmd in sc.dialect.cmds_single()[-2:] if self.tek else (":SING",):
            sc.w(cmd)
        self.wait(.05)
        until = time.perf_counter() + 5
        while time.perf_counter() < until:
            if self.stopped(sc):
                return
            self.wait(.05)
        raise TimeoutError("fresh single capture did not finish in 5 seconds")

    def check(self, sc):
        delay = self.cfg["frame"]["settle_s"] if self.mode == "baseline" else 0
        self.wait(delay)
        self.frame_input = tools.read_frame(sc, self.channel, view="period")
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
        ch = getattr(self, "channel", "CHAN1")
        values = {}
        for k in ITEMS:
            if k in cached:
                values[k] = cached[k]
            elif k == "PDUT" and self.tek and self.mode == "optimized" and values.get("PER"):
                # same frozen STOP record: PWI / PERI * 100 is what the scope-side PDUT computes too,
                # without measuring PWI and PERI a second time (~1.3 s)
                values[k] = values["PWID"] / values["PER"] * 100
            else:
                values[k] = sc.measure(k) if ch == "CHAN1" else sc.measure(k, ch)
        # MSO5104 firmware 00.01.03.03.00 reports PDUT as a fraction, not percent; the TDS2014B value is
        # computed in percent (PWI / PERI * 100).
        if values['PDUT'] is not None and dialect_of(sc).name == "rigol":
            values['PDUT_raw'] = values['PDUT']
            values['PDUT'] *= 100
        require(acceptance(values), f"Timer measurement rejected: {values}")
        # Measurement queries add overlays; clear them and recheck the menu before the report screenshot.
        if dialect_of(sc).clear_meas:  # TDS2014B immediate measurements draw nothing
            sc.w(dialect_of(sc).clear_meas)
        return values

    def screenshot(self, sc, path):
        require(self.stopped(sc), "capture changed before screenshot")
        raw = sc.screenshot_bmp()
        # RIGOL measurement queries reopen Measure even after an earlier menu check.
        rows = menu_rules.stats(menu_rules.bmp_to_array(raw), sc.cfg)['hit_rows']
        if rows > sc.cfg['menu']['open_rows']:
            require(sc.dialect.hide_menu, f"a box covers the graticule ({rows} rows) and no SCPI closes it")
            sc.w(sc.dialect.hide_menu)
            self.wait(.8)
            raw = sc.screenshot_bmp()
        self.frame_input.menu_rows = menu_rules.stats(menu_rules.bmp_to_array(raw), sc.cfg)['hit_rows']
        require(tools.decide_frame(self.frame_input, cfg=sc.cfg)['ready'], 'final screenshot menu/frame not ready')
        with Image.open(io.BytesIO(raw)) as img:
            # TDS2014B screenshot_bmp(white=True) is already native white background (HARDC:INKS ON);
            # only RIGOL MSO5104 requires RGB inversion because its :DISP:DATA? ignores invert.
            (img.convert("RGB") if self.tek else ImageOps.invert(img.convert("RGB"))).save(path)
        if self.tek:
            require('TEKTRONIX' in sc.q('*IDN?'), 'hardcopy read misaligned subsequent IDN')
            require(not sc.errors(), "SCPI error after capture")
            return
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
    p.add_argument("--channel", default="CHAN1", help="probed channel, e.g. CHAN1 (RIGOL) or CH2 (TDS2014B)")
    p.add_argument("--output", type=Path)
    a = p.parse_args(argv)
    if a.runs < 1:
        p.error("runs must be positive")
    output = a.output or RESULTS / ('timer_' + time.strftime('%Y%m%d_%H%M%S') + '_' + a.mode)
    e = Experiment(a.mode, output, a.nodelay)
    e.channel = channel = a.channel
    model = getattr(e, 'model', None) or e.cfg['scope'].get('model', 'rigol')
    rows = []
    try:
        env = tools_ccs.ccs_env()
        require(env['probe_present'], 'XDS110 not present')
        metadata = {k: env[k] for k in ('probe', 'probe_present', 'tools')}
        program = tools_ccs.project_dir('TIMER0_EX') / 'Debug/TIMER0_EX.out'
        metadata.update(date=datetime.datetime.now().astimezone().isoformat(), scope=e.cfg['scope'],
                        channel=channel,
                        program_sha256=hashlib.sha256(program.read_bytes()).hexdigest() if program.exists() else None)
        with e.scope() as sc:
            idn = sc.q('*IDN?')
            require(IDN_MODEL.get(model, 'MSO5104') in idn, 'unexpected scope model')
        metadata['scope_idn'] = idn.split(',')[:2] + idn.split(',')[3:]  # without the serial number
        (output / 'environment.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
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
                for cmd in settings(model, channel) + run_cmds(model):
                    sc.w(cmd)
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
