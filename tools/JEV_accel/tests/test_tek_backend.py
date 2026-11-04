"""Offline tests of the Tektronix TDS2014B backend (scope.model "tek"): position in divisions, int8 record
to the BYTE clip scale, 1-2.5-5 timebase, WAIT handling, menu overlay detector, Timer bench (no scope)."""
import importlib.util
import types
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw

from jev_accel import scope_io, tools
from jev_accel.config import ROOT, load_config
from jev_accel.rules import diagnose as diag_rules, menu as menu_rules
from jev_accel.rules.frame import FrameInput, evaluate
from jev_accel.scope_io import (TEK, TekScope, levels_from_waveform, prepare_read, same_channel, tek_channel,
                                tek_raw_to_u8, tek_tdiv)

FIX = Path(__file__).parent / "fixtures"

# the parts of tools/MCP/scope-tek-tds2000b/tek.py that TekScope uses (no pyvisa needed here)
TEK_MOD = types.SimpleNamespace(
    RECORD=2500, INVALID=9.9e37, DERIVED_DUTY={"PDUT": "PWI", "NDUT": "NWI"},
    MEAS_ALIASES={"FREQ": "FREQ", "PER": "PERI", "PWID": "PWI", "NWID": "NWI", "RTIM": "RIS", "FTIM": "FALL"})


class FakeInst:
    def __init__(self, owner):
        self.owner, self.timeout, self.writes = owner, 5000, []

    def write(self, cmd):
        self.writes.append(cmd)
        self.owner.apply(cmd)

    def query_binary_values(self, cmd, datatype, container):
        self.owner.check_live(cmd)
        return container(self.owner.codes)


class FakeTek:
    """A TDS2014B with GPIO0 (0 / 3.28 V square, 2.5 Hz) on CH2. Any 'HDR value' write sets 'HDR?'.
    The int8 codes follow the real scaling (25 codes/div, YOF = position * 25); below 10 us/div the edge
    shows its overshoot (3.64 / -0.12 V), as the real GPIO0 edge did at 250 ns/div."""

    def __init__(self, state="STOP", mode="NORMAL"):
        self.state, self.forced, self.n_acq = state, False, 7
        self.inst = FakeInst(self)
        self.values = {"CH2:PRO?": "1.0E1", "CH2:SCA?": "1.0E0", "CH2:POS?": "-1.64E0", "HOR:MAI:SCA?": "1.0E-1",
                       "HOR:MAI:POS?": "0.0E0", "TRIG:MAI:LEV?": "1.64E0", "TRIG:MAI:EDGE:SLO?": "RISE",
                       "TRIG:MAI:EDGE:SOU?": "CH2", "TRIG:MAI:MOD?": mode, "WFMP:XIN?": "4.0E-4",
                       "WFMP:PT_O?": "0", "WFMP:XZE?": "-5.0E-1", "WFMP:YZE?": "0.0E0"}
        self.meas = {"PERI": "4.0E-1", "FREQ": "2.5E0", "PWI": "2.0E-1", "NWI": "2.0E-1", "RIS": "4.0E-9"}
        self.queries = []

    @property
    def codes(self):
        t = np.arange(2500) * 4e-4
        v = np.where((t % 0.4) < 0.2, 3.28, 0.0)
        if float(self.values["HOR:MAI:SCA?"]) < 1e-5:
            v[::50], v[25::50] = 3.64, -0.12
        ymult, yoff = float(self.values["CH2:SCA?"]) / 25, float(self.values["CH2:POS?"]) * 25
        return np.clip(np.round(v / ymult + yoff), -128, 127).astype(np.int8)

    def apply(self, cmd):
        if cmd == "TRIG FORC":
            self.forced, self.n_acq = True, self.n_acq + 1
            return
        head, _, arg = cmd.partition(" ")
        if arg:
            self.values[f"{head}?"] = arg

    def check_live(self, cmd):
        if self.state == "WAIT" and not self.forced and self.values["TRIG:MAI:MOD?"].upper().startswith("NORM"):
            raise AssertionError(f"{cmd}: stale record read while NORM waits for a trigger")

    def num_acq(self):
        return self.n_acq

    def acquiring(self):
        return self.state != "STOP"

    def query(self, cmd, timeout_ms=None):
        self.queries.append(cmd)
        if cmd == "WFMP:YMU?":
            return str(float(self.values["CH2:SCA?"]) / 25)
        if cmd == "WFMP:YOF?":
            return str(float(self.values["CH2:POS?"]) * 25)
        return self.values[cmd]

    def query_checked(self, cmd, timeout_ms=2000):
        self.check_live(cmd)
        return self.meas[self.values["MEASU:IMM:TYP?"]]

    def run_state(self, window_s=0.25):
        if self.values["TRIG:MAI:MOD?"].upper().startswith("AUTO"):
            return "AUTO"
        return self.state

    def errors(self):
        return []

    def close(self):
        self.closed = True


def _scope(fake):
    sc = TekScope.__new__(TekScope)
    sc.cfg, sc.mod, sc.tek = load_config("tek"), TEK_MOD, fake
    sc._wave, sc._meas_src, sc._dat_src = {}, None, None
    return sc


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(scope_io.time, "sleep", lambda s: None)


def test_config_resolves_the_tek_block():
    cfg = load_config("tek")
    assert cfg["scope"]["model"] == "tek" and cfg["scope"]["resource"] == "auto"
    assert cfg["menu"]["kind"] == "tek_graticule" and cfg["menu"]["in_frame"] is False
    assert Path(cfg["tek_tds_dir"]).is_absolute() and (Path(cfg["tek_tds_dir"]) / "tek.py").exists()


def test_position_in_divisions_matches_the_rule_offset():
    # rule offset = -(screen-center volts); TDS2014B center = -position * V/div, so position = offset / V/div
    assert TEK.cmd_offset("CHAN2", -1.65, vdiv=1) == "CH2:POS -1.65"
    assert TEK.cmd_offset("CH2", -1.65, vdiv=0.5) == "CH2:POS -3.3"
    assert TEK.cmd_offset("CH1", 0.0, vdiv=2) == "CH1:POS 0"
    with pytest.raises(ValueError):
        TEK.cmd_offset("CH2", -1.65)
    sc = _scope(FakeTek())
    assert TEK.offset(sc, "CHAN2") == pytest.approx(-1.64)  # POS -1.64 div * 1 V/div; center +1.64 V
    center = -float(sc.tek.values["CH2:POS?"]) * float(sc.tek.values["CH2:SCA?"])
    assert center == pytest.approx(-TEK.offset(sc, "CH2"))


def test_names_timebase_and_commands():
    assert tek_channel("CHAN3") == "CH3" and tek_channel(2) == "CH2" and tek_channel("math") == "MATH"
    assert same_channel("CH2", "CHAN2") and not same_channel("CH1", "CHAN2")
    assert tek_tdiv(2e-4) == pytest.approx(2.5e-4) and tek_tdiv(1e-9) == pytest.approx(5e-9)
    assert tek_tdiv(0.1) == pytest.approx(0.1) and tek_tdiv(3e-3) == pytest.approx(5e-3)
    assert TEK.cmd_tdiv(2e-4) == "HOR:MAI:SCA 0.00025" and TEK.cmd_vernier("CH2", True) == ""
    assert TEK.cmd_probe("CHAN2", 10) == "CH2:PRO 10" and TEK.cmd_trig_level(1.65, ".3f") == "TRIG:MAI:LEV 1.650"
    assert TEK.cmds_single() == ["TRIG:MAI:MOD NORM", "ACQ:STOPA SEQ", "ACQ:STATE RUN"]
    assert TEK.hide_menu is None and TEK.clear_meas is None


def test_ensure_writes_only_settings_that_differ():
    from jev_accel.scope_io import tek_setting_matches as m
    assert m("CH2:POS", "-1.65", "-1.64E0") and m("TRIG:MAI:LEV", "1.65", "1.64E0")
    assert not m("HOR:MAI:SCA", "2.5e-7", "1.0E-6") and not m("HOR:MAI:POS", "0.001", "0.0E0")
    assert m("SEL:CH2", "ON", "1") and m("ACQ:STATE", "RUN", "1") and not m("ACQ:STATE", "RUN", "0")
    assert m("ACQ:MOD", "SAM", "SAMPLE") and m("TRIG:MAI:EDGE:SLO", "RIS", "RISE") and m("CH2:YUN", '"V"', '"V"')
    assert not m("TRIG:MAI:MOD", "NORM", "AUTO") and m("ACQ:STOPA", "RUNST", "RUNSTOP")
    fake = FakeTek()
    fake.values.update({"ACQ:STATE?": "0", "SEL:CH2?": "1"})
    sc = _scope(fake)
    sent = sc.ensure(["SEL:CH2 ON", "CH2:SCA 1", "CH2:POS -1.65", "HOR:MAI:SCA 0.1", "ACQ:STATE RUN"])
    assert sent == ["ACQ:STATE RUN"] == fake.inst.writes


def test_int8_record_maps_onto_the_byte_clip_rule():
    """Codes measured 2026-11-03: centred GPIO0 -41..43; 0 V half a division under the screen -112;
    beyond +5.1 div the ADC saturates at +127. Reaching the screen edge (|code| >= 99) counts as clipped."""
    u = tek_raw_to_u8(np.array([-41, 43, 98, -98, 99, -99, -112, 127, -128], dtype=np.int8))
    assert u.tolist() == [87, 171, 226, 30, 255, 0, 0, 255, 0]
    cfg = load_config("tek")
    base = dict(vdiv=1, offset=-1.64, probe=10, tdiv=.1, t_offset=0, trig_level=1.64, trig_status="STOP",
                vtop=3.28, vbase=0, vmax=3.36, vmin=0, view="period", period_s=.4, span_s=1.0)
    assert not evaluate(FrameInput(raw_min=87, raw_max=171, **base), cfg).metrics["clipped"]
    edge = tek_raw_to_u8(np.array([-112, -29], dtype=np.int8))  # the "0 V below the screen" capture
    assert evaluate(FrameInput(raw_min=int(edge.min()), raw_max=int(edge.max()), **base), cfg).metrics["clipped"]


def test_clipped_period_frame_without_period_gets_a_clip_hint():
    """Hardware 2026-11-03: 0.2 V/div, 1.5 V centered on the 0-3.3 V square -> PERI 9.9E37, codes saturated."""
    cfg = load_config("tek")
    fi = FrameInput(vdiv=.2, offset=-1.5, probe=10, tdiv=.1, t_offset=0, trig_level=1.65, trig_status="STOP",
                    vtop=2.52, vbase=0.48, vmax=2.52, vmin=0.48, raw_min=0, raw_max=255, view="period",
                    period_s=None, span_s=1.0)
    out = tools.decide_frame(fi, "off", cfg=cfg, channel="CH2", dialect=TEK)
    assert not out["ready"] and out["l0"]["metrics"]["clipped"] and "clipped" in out["hint"]


def test_levels_from_the_record_ignore_overshoot():
    v = np.r_[np.zeros(1000), np.full(1000, 3.3), [3.9, -0.4]]
    top, base = levels_from_waveform(v, 0.2)
    assert top == pytest.approx(3.3) and base == pytest.approx(0.0)
    assert levels_from_waveform(np.full(100, 0.02), 0.2) == (None, None)


def test_period_frame_on_ch2_is_ready_and_fix_uses_divisions():
    sc = _scope(FakeTek())
    fi = tools.read_frame(sc, "CHAN2", check_menu=True, view="period")  # menu.in_frame=false: no hardcopy
    assert fi.menu_rows is None and fi.trig_on_channel and fi.period_s == pytest.approx(0.4)
    assert fi.vtop == pytest.approx(3.28) and fi.vbase == pytest.approx(0.0) and fi.raw_max == 169
    out = tools.decide_frame(fi, "off", cfg=sc.cfg, channel="CH2", dialect=TEK)
    assert out["ready"] and out["next_fix"] == "ok"
    assert not any(q.startswith("MEASU") for q in sc.tek.queries)  # VTOP/VBASE came from the record
    r = evaluate(FrameInput(**{**fi.__dict__, "offset": -0.64}), sc.cfg)
    assert r.label == "fix_offset"
    assert tools.frame_fix_scpi("fix_offset", r, "CH2", TEK, vdiv=1) == ["CH2:POS -1.64"]


def test_check_frame_never_reads_a_stale_record_while_waiting():
    sc = _scope(FakeTek(state="WAIT"))
    fi = tools.read_frame(sc, "CH2", check_menu=False)  # FakeTek raises on CURV? / MEASU while waiting
    assert fi.trig_status == "WAIT" and fi.vtop is None and fi.raw_min is None
    assert evaluate(fi, sc.cfg).label == "diagnose"
    assert not any(w.startswith("TRIG:MAI:MOD") for w in sc.tek.inst.writes)


def test_diagnose_peeks_in_auto_restores_normal_and_speaks_tek():
    fake = FakeTek(state="WAIT")
    fake.values["HOR:MAI:SCA?"] = "2.5E-3"  # below 100 ms/div AUTO free-runs normally
    sc = _scope(fake)
    prepare_read(sc, peek=True)
    assert fake.inst.writes == ["TRIG:MAI:MOD AUTO"]
    assert TEK.trig_status(sc) == "WAIT" and TEK.sweep(sc) == "NORM"
    assert sc.measure("VMAX", "CHAN2") == pytest.approx(3.28)
    sc.close()
    assert fake.inst.writes[-1] == "TRIG:MAI:MOD NORM"
    di = diag_rules.DiagInput(probe=1, expected_probe=10, trig_level_set=None, trig_level_readback=0.2,
                              trig_status="WAIT", sweep="AUTO", want_single=True, vmax=0.33, vmin=0.0)
    out = tools.decide_diagnose(di, "off", load_config("tek"), TEK, "CH2")
    assert out["root_cause"] == "probe_ratio" and out["fix"][0] == "CH2:PRO 10"
    assert out["l0"]["fixes"]["sweep_mode"] == TEK.cmds_single()


def test_autoframe_sets_probe_then_positions_in_divisions_and_widens_for_overshoot():
    fake = FakeTek(state="TD")
    fake.values["CH2:PRO?"] = "1.0E0"
    sc = _scope(fake)
    out = tools.autoframe_on(sc, sc.cfg, "CH2", "edge", None, True)
    assert out["pre_scpi"] == ["CH2:PRO 10"] and not out["coarse_pass"]
    assert out["plan"]["vdiv"] == 0.5 and out["plan"]["offset"] == pytest.approx(-1.64)
    assert out["scpi"] == ["CH2:SCA 0.5", "CH2:POS -3.28", "TRIG:MAI:LEV 1.64", "HOR:MAI:SCA 5e-09",
                           "HOR:MAI:POS 0"]
    # at 5 ns/div the overshoot reaches the screen edge at 0.5 V/div: one wider step, same center
    v = out["verify"]
    assert v["reason"] == "clipped" and v["vdiv"] == 0.6 and v["scpi"] == ["CH2:SCA 0.6", "CH2:POS -2.73333"]
    assert "" not in fake.inst.writes and out["readback"]["CH2:SCA?"] == "0.6"
    assert evaluate(tools.read_frame(_rescan(sc), "CH2", check_menu=False), sc.cfg).metrics["clipped"] is False


def _rescan(sc):
    sc._wave.clear()
    sc.state_before = None
    return sc


def test_slow_timebase_peek_forces_one_acquisition_instead_of_rolling_auto():
    fake = FakeTek(state="WAIT")
    sc = _scope(fake)  # 100 ms/div: AUTO would roll (SCAN) and leave a half-filled record
    prepare_read(sc, peek=True)
    assert fake.inst.writes == ["TRIG FORC"] and TEK.trig_status(sc) == "WAIT"
    assert sc.measure("VMAX", "CH2") == pytest.approx(3.28) and sc.measure("VMIN", "CH2") == pytest.approx(0.0)
    sc.close()
    assert not any(w.startswith("TRIG:MAI:MOD") for w in fake.inst.writes)  # nothing to restore


def test_menu_detector_on_the_real_closed_screen_and_a_synthetic_box():
    cfg = load_config("tek")
    # Native white-background hardcopy (HARDC:INKS ON, default)
    white_closed = np.asarray(Image.open(FIX / "tek_screen_white_closed.png").convert("RGB"))
    sw = menu_rules.stats(white_closed, cfg)
    assert sw["hit_rows"] == 0 and sw["band_rows"] == 199 and tools.decide_menu(sw, "off", cfg)["visible"] is False
    w_img = Image.fromarray(white_closed.copy())
    wd = ImageDraw.Draw(w_img)
    wd.rectangle((40, 80, 220, 130), outline=(0, 0, 0), fill=(255, 255, 255))
    wd.text((48, 90), "Trigger level out of range", fill=(0, 0, 0))
    wd.text((48, 108), "Press any key to continue", fill=(0, 0, 0))
    sw_open = menu_rules.stats(np.asarray(w_img), cfg)
    assert sw_open["hit_rows"] > cfg["menu"]["open_rows"] and tools.decide_menu(sw_open, "off", cfg)["visible"] is True
    # Black-background hardcopy (HARDC:INKS OFF)
    closed = np.asarray(Image.open(FIX / "tek_screen_closed.png").convert("RGB"))  # real, CH1 menu open
    s = menu_rules.stats(closed, cfg)
    assert s["hit_rows"] == 0 and s["band_rows"] == 199 and tools.decide_menu(s, "off", cfg)["visible"] is False
    img = Image.fromarray(closed.copy())  # synthetic: a white-framed message box with text over the grid
    d = ImageDraw.Draw(img)
    d.rectangle((40, 80, 220, 130), outline=(204, 204, 204))
    d.text((48, 90), "Trigger level out of range", fill=(204, 204, 204))
    d.text((48, 108), "Press any key to continue", fill=(204, 204, 204))
    s = menu_rules.stats(np.asarray(img), cfg)
    assert s["hit_rows"] > cfg["menu"]["open_rows"] and tools.decide_menu(s, "off", cfg)["visible"] is True


def _bench():
    spec = importlib.util.spec_from_file_location("timer_bench_tek", ROOT / "bench/timer_flow.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_timer_bench_settings_for_ch2():
    bench = _bench()
    s = bench.settings("tek", "CH2")
    assert "CH2:POS -1.65" in s and "TRIG:MAI:EDGE:SOU CH2" in s and s[-1] == "TRIG:MAI:MOD NORM"
    assert bench.run_cmds("tek") == ("ACQ:STOPA RUNST", "ACQ:STATE RUN")
    assert bench.settings("rigol", "CHAN1") == bench.SETTINGS and bench.run_cmds() == (":RUN",)
    assert ":CHAN2:OFFS -1.65" in bench.settings("rigol", "CHAN2")


def test_timer_bench_tek_duty_is_percent_and_reuses_the_stop_record():
    bench = _bench()
    e = bench.Experiment.__new__(bench.Experiment)
    e.mode, e.model, e.channel = "optimized", "tek", "CH2"
    calls = []

    def measure(item, src="CHAN1"):
        calls.append((item, src))
        return {"FREQ": 2.5, "PWID": .2, "NWID": .2}[item]
    sc = types.SimpleNamespace(measure=measure, dialect=TEK, w=lambda cmd: calls.append(cmd))
    got = e.measure(sc, {"measurements": {"PER": .4, "VTOP": 3.28, "VBASE": 0}})
    assert got["PDUT"] == pytest.approx(50) and "PDUT_raw" not in got and bench.acceptance(got)
    assert calls == [("FREQ", "CH2"), ("PWID", "CH2"), ("NWID", "CH2")]  # no PDUT query, no overlay clear
