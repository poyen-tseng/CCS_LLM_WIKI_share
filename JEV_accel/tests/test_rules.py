"""Offline L0 tests: autoframe math, frame / diagnose / flash / menu rules, and the fixture replay with Jev off."""
import numpy as np
import pytest

from jev_accel import replay, tools
from jev_accel.config import load_config
from jev_accel.rules import autoframe, flash, menu
from jev_accel.rules.frame import FrameInput, evaluate

CFG = load_config()


@pytest.fixture(autouse=True)
def no_jev_key(monkeypatch):
    """Offline tests must never reach the API, even if the key is set in the shell."""
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    tools._gate = None


# --- E: autoframe ----------------------------------------------------------------------------
def test_vdiv_matches_accepted_ex1_frame():
    # c8f002db L397: 3.72 V overshoot clipped at 0.5 V/div; 0.6 V/div with VERN fit
    assert autoframe.vdiv_for(3.72, 0.05) == pytest.approx(0.6)
    assert not autoframe.is_std_step(0.6)
    assert autoframe.is_std_step(0.5) and autoframe.is_std_step(1.0) and autoframe.is_std_step(2e-9)


def test_plan_centers_on_measured_mid():
    p = autoframe.plan(vtop=3.66, vbase=0.17, vmax=3.72, vmin=0.05, rise_s=11.8e-9)
    assert p["offset"] == pytest.approx(-1.915)
    assert p["trigger_level"] == pytest.approx(1.915)
    assert p["tdiv"] == pytest.approx(5e-9)  # floor of the MSO5104
    assert p["vernier"] is True


@pytest.mark.parametrize("delay, tdiv", [(320e-9, 50e-9), (35e-6, 5e-6), (33.1e-6, 5e-6)])
def test_delay_timebase_matches_transcripts(delay, tdiv):
    # 32ca5dc5 / c8f002db: QSEL=0 delay at 50 ns/div, QSEL=2 delay at 5 us/div
    assert autoframe.tdiv_for_delay(delay) == pytest.approx(tdiv)


def test_round_125():
    assert autoframe.round_125(4.4e-6) == pytest.approx(5e-6)
    assert autoframe.round_125(5.9e-9, up=False) == pytest.approx(5e-9)
    assert autoframe.round_125(1.0) == pytest.approx(1.0)


# --- A: frame --------------------------------------------------------------------------------
def _good(**kw) -> FrameInput:
    base = dict(vdiv=0.6, offset=-1.915, probe=10, tdiv=5e-9, t_offset=0.0, trig_level=1.915,
                trig_status="STOP", vtop=3.66, vbase=0.17, vmax=3.72, vmin=0.05, raw_min=44, raw_max=228,
                t50=0.0, rise_s=11.8e-9, menu_rows=0)
    base.update(kw)
    return FrameInput(**base)


def test_clean_frame_is_ok_and_decisive():
    r = evaluate(_good(), CFG)
    assert r.label == "ok" and r.decisive and r.violations == []


def test_positive_offset_is_caught_before_the_user_complains():
    r = evaluate(_good(vdiv=1.0, offset=1.65, vmax=2.35, raw_max=255), CFG)
    assert r.label == "fix_offset"
    # clipped: no offset advice from clipped levels (on the scope it diverged); check_frame re-frames instead
    assert tools.frame_fix_scpi("fix_offset", r) == []
    assert "autoframe" in tools.decide_frame(_good(vdiv=1.0, offset=1.65, vmax=2.35, raw_max=255), "off")["hint"]


def test_unclipped_offset_error_gets_a_direct_fix():
    r = evaluate(_good(offset=-1.2), CFG)  # 0.7 div off, nothing clipped
    assert r.label == "fix_offset" and tools.frame_fix_scpi("fix_offset", r)[-1] == ":CHAN1:OFFS -1.915"


def test_running_display_is_not_a_failed_capture():
    assert evaluate(_good(trig_status="AUTO"), CFG).label == "ok"
    assert evaluate(_good(trig_status="WAIT"), CFG).label == "diagnose"


def test_delay_view_does_not_require_a_centered_edge():
    fi = _good(tdiv=5e-8, t_offset=1.6e-7, t50=1e-9)
    assert evaluate(fi, CFG).label == "shift_timebase"
    fi.view = "delay"
    assert evaluate(fi, CFG).label == "ok"


def test_multiple_violations_are_not_decisive():
    r = evaluate(_good(probe=1, menu_rows=300), CFG)
    assert r.violations[:2] == ["fix_probe", "hide_menu"] and not r.decisive


# --- C: flash --------------------------------------------------------------------------------
def test_parse_real_edge_run_log():
    p = flash.parse((replay.FIXTURES / "logs" / "edge_run_ok_672437.txt").read_text(encoding="utf-8"))
    assert (p.pc, p.ready, p.ran, p.exit_code) == (0x87C0, True, True, 0)


def test_measured_behavior_overrides_a_clean_log():
    text = (replay.FIXTURES / "logs" / "edge_run_ok_672438.txt").read_text(encoding="utf-8")
    assert flash.classify(flash.parse(text), (2e-5, 5e-5), 2.4e-7).label == "rebuild_needed"
    assert flash.classify(flash.parse(text), (2e-5, 5e-5), 3.31e-5).label == "ok_running"


# --- D: menu ---------------------------------------------------------------------------------
def _screen(open_menu: bool) -> np.ndarray:
    img = np.zeros((600, 1024, 3), np.uint8)
    img[300, :, 1] = 200  # a yellow-ish CH1 trace crossing the band must not count
    img[300, :, 0] = 200
    if open_menu:
        img[200:540, 852:856] = (0, 44, 90)  # the real Measure-menu border color
    return img


def test_menu_stats_on_synthetic_screens():
    s_open, s_closed = menu.stats(_screen(True), CFG), menu.stats(_screen(False), CFG)
    assert menu.classify(s_open, CFG) is True and s_open["hit_rows"] == 340
    assert menu.classify(s_closed, CFG) is False and s_closed["hit_rows"] == 0


def test_bmp_decoder_round_trip():
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.fromarray(_screen(True)).save(buf, format="BMP")
    assert np.array_equal(menu.bmp_to_array(buf.getvalue()), _screen(True))


# --- replay with Jev off -----------------------------------------------------------------------
@pytest.mark.parametrize("bridge", replay.BRIDGES)
def test_fixtures_pass_with_rules_only(bridge):
    for case in replay.load(bridge):
        if case.get("needs_jev"):
            continue
        got, _ = replay.decide_case(bridge, case, "off")
        assert got in case["accept"], f"{case['id']}: {got} not in {case['accept']} ({case['source']})"


# --- E: autoframe on a scope that starts badly framed -------------------------------------------
class FakeScope:
    """1x probe setting on a 10x probe, 1 us/div on a 1 kHz 0-3 V square: VTOP/VBASE invalid until
    the probe is fixed and the timebase shows whole periods (the live state seen 2026-10-07)."""

    def __init__(self):
        self.probe, self.tdiv, self.writes = 1.0, 1e-6, []

    def w(self, cmd):
        self.writes.append(cmd)
        if cmd.startswith(":CHAN1:PROB"):
            self.probe = float(cmd.split()[1])
        if cmd.startswith(":TIM:MAIN:SCAL"):
            self.tdiv = float(cmd.split()[1])

    def q(self, cmd):
        return "ok"

    def waveform_raw(self, ch):
        return None, None, np.array([60, 200] if not getattr(self, "clipped", False) else [40, 255])

    def qf(self, cmd):
        return self.probe if cmd == ":CHAN1:PROB?" else 0.0

    def settle(self, s):
        pass

    def measure(self, item, ch):
        k = self.probe / 10  # displayed volts scale with the probe setting
        whole_periods = self.tdiv >= 1e-4
        return {"VTOP": 3.0 * k if whole_periods else None, "VBASE": 0.0 if whole_periods else None,
                "VMAX": 3.05 * k, "VMIN": -0.02 * k, "RTIM": 1e-6 if whole_periods else None}[item]


def test_autoframe_fixes_probe_then_coarse_frames_then_plans():
    sc = FakeScope()
    out = tools.autoframe_on(sc, CFG, "CHAN1", "edge")
    assert "error" not in out and out["coarse_pass"] is True
    assert out["pre_scpi"][0] == ":CHAN1:PROB 10"  # probe before any level is used
    assert out["plan"]["trigger_level"] == pytest.approx(1.5)  # measured in 10x units, not 0.15
    assert out["plan"]["offset"] == pytest.approx(-1.5)
    assert ":TIM:MAIN:SCAL 0.0002" in out["pre_scpi"]


def test_autoframe_reframes_a_clipped_trace_from_the_logic_midpoint():
    sc = FakeScope()
    sc.probe, sc.tdiv, sc.clipped = 10.0, 1e-3, True  # levels measurable but clipped
    out = tools.autoframe_on(sc, CFG, "CHAN1", "edge")
    assert out["was_clipped"] and out["coarse_pass"]
    assert ":CHAN1:OFFS -1.650" in out["pre_scpi"]  # not from the clipped VMAX/VMIN


def test_autoframe_reports_no_signal_after_coarse_pass():
    sc = FakeScope()
    sc.measure = lambda item, ch: None
    out = tools.autoframe_on(sc, CFG, "CHAN1", "edge")
    assert out["coarse_pass"] is True and "no signal" in out["error"]


@pytest.mark.parametrize("name, visible", [("menu_band_open.npy", True), ("menu_band_closed.npy", False)])
def test_menu_rule_on_real_scope_pixels(name, visible):
    """Real bands from 2026-10-07: the old b>120 rule saw 0 rows in both."""
    band = np.load(replay.FIXTURES / name)
    img = np.zeros((600, 1024, 3), np.uint8)
    img[200:541, 850:863] = band
    assert menu.classify(menu.stats(img, CFG), CFG) is visible
