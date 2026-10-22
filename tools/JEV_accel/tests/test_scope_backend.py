"""Offline tests of the Keysight backend: offset sign, SCPI dialect, WAIT handling (no scope needed)."""
import types

import numpy as np
import pytest

from jev_accel import tools
from jev_accel.config import load_config
from jev_accel.rules.frame import evaluate
from jev_accel.scope_io import KEYSIGHT, RIGOL, KeysightScope, prepare_read


class FakeLan:
    """Stands in for ks_lan: a CLK-like 0-2 V square, centered at +1.0 V (Keysight offset)."""

    def __init__(self, state="TD", sweep="NORM"):
        self.state, self.writes = state, []
        self.values = {":CHAN1:OFFS?": "+1.0E+00", ":CHAN1:SCAL?": "+400E-03", ":CHAN1:PROB?": "+10.0E+00",
                       ":TIM:SCAL?": "+20.0E-09", ":TIM:POS?": "+0.0E+00", ":TRIG:EDGE:LEV?": "+1.0E+00",
                       ":TRIG:EDGE:SLOP?": "POS", ":TRIG:EDGE:SOUR?": "CHAN1", ":TRIG:SWE?": sweep,
                       ":MEAS:VTOP? CHAN1": "+2.0E+00", ":MEAS:VBAS? CHAN1": "+0.0E+00",
                       ":MEAS:VMAX? CHAN1": "+2.05E+00", ":MEAS:VMIN? CHAN1": "-0.05E+00",
                       ":MEAS:RIS? CHAN1": "+40E-09"}

    def query(self, s, cmd):
        if cmd.startswith((":MEAS", ":WAV")) and self.state == "WAIT" and self.values[":TRIG:SWE?"] == "NORM":
            raise AssertionError(f"{cmd} would block the scope while it waits for a trigger")
        return self.values[cmd]

    def write(self, s, cmd):
        self.writes.append(cmd)
        if cmd.startswith(":TRIG:SWE"):
            self.values[":TRIG:SWE?"] = cmd.split()[1]

    def run_state(self, s):
        return "AUTO" if self.values[":TRIG:SWE?"] == "AUTO" else self.state

    def waveform_raw(self, s, source, points):
        if self.state == "WAIT" and self.values[":TRIG:SWE?"] == "NORM":
            raise AssertionError("waveform read while waiting")
        t = np.linspace(-1e-7, 1e-7, 640)
        v = np.where(t < 0, 0.0, 2.0)
        return t, v, (v / 0.0134 + 128 - 1.0 / 0.0134).astype(np.uint8)


def _scope(lan):
    sc = KeysightScope.__new__(KeysightScope)
    sc.cfg, sc.lan, sc.s = load_config("keysight"), lan, types.SimpleNamespace(close=lambda: None)
    return sc


def test_keysight_offset_is_the_negated_center_voltage():
    sc = _scope(FakeLan())
    assert KEYSIGHT.offset(sc, "CHAN1") == pytest.approx(-1.0)  # rule convention: -(center volts)
    assert KEYSIGHT.cmd_offset("CHAN1", -1.085) == ":CHAN1:OFFS 1.085"
    assert KEYSIGHT.cmd_offset("CHAN1", 0.0) == ":CHAN1:OFFS 0"
    assert RIGOL.cmd_offset("CHAN1", -1.085) == ":CHAN1:OFFS -1.085"


def test_keysight_timebase_menu_and_measure_names():
    assert KEYSIGHT.cmd_tdiv(2e-8) == ":TIM:SCAL 2e-08" and KEYSIGHT.cmd_t_offset(0, "g") == ":TIM:POS 0"
    assert KEYSIGHT.hide_menu is None and KEYSIGHT.clear_meas == ":MEAS:CLE"
    sc = _scope(FakeLan())
    assert sc.measure("VBASE") == pytest.approx(0.0) and sc.measure("RTIM") == pytest.approx(4e-8)


def test_centered_keysight_frame_is_ok_and_fix_uses_keysight_syntax():
    sc = _scope(FakeLan())
    fi = tools.read_frame(sc, check_menu=False)
    assert fi.offset == pytest.approx(-1.0) and fi.trig_status == "TD"
    r = evaluate(fi, load_config("keysight"))
    assert r.metrics["center_err_div"] == pytest.approx(0.0)
    fix = tools.frame_fix_scpi("fix_offset", r, "CHAN1", KEYSIGHT)
    assert fix[-1] == ":CHAN1:OFFS 1" and tools.frame_fix_scpi("hide_menu", r, "CHAN1", KEYSIGHT) == []


def test_check_frame_never_reads_data_while_waiting():
    sc = _scope(FakeLan(state="WAIT"))
    fi = tools.read_frame(sc, check_menu=False)  # FakeLan raises if a blocking query is sent
    assert fi.trig_status == "WAIT" and fi.vtop is None and fi.raw_min is None
    assert evaluate(fi, load_config("keysight")).label == "diagnose"
    assert not any(w.startswith(":TRIG:SWE") for w in sc.lan.writes)  # an armed single shot is left alone


def test_diagnose_peeks_in_auto_and_restores_norm():
    lan = FakeLan(state="WAIT")
    sc = _scope(lan)
    prepare_read(sc, peek=True)
    assert lan.writes == [":TRIG:SWE AUTO"]
    assert KEYSIGHT.trig_status(sc) == "WAIT" and KEYSIGHT.sweep(sc) == "NORM"  # the state found, not AUTO
    assert sc.measure("VMAX") == pytest.approx(2.05)
    sc.close()
    assert lan.writes[-1] == ":TRIG:SWE NORM"


def test_rigol_doubles_need_no_prepare_read():
    prepare_read(types.SimpleNamespace(), peek=True)  # FakeScope-style objects: no-op
