"""Periodic frames, restricted target reads, and fragmented SCPI replies (offline)."""
import importlib.util
import contextlib
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from jev_accel import ccs_daemon, tools
from jev_accel.config import ROOT, load_config
from jev_accel.rules.frame import FrameInput, evaluate


def periodic(**changes):
    values = dict(vdiv=1, offset=-1.65, probe=10, tdiv=.1, t_offset=0, trig_level=1.65,
                  trig_status='STOP', vtop=3.3, vbase=0, vmax=3.3, vmin=0,
                  raw_min=80, raw_max=175, t50=-.4, menu_rows=0,
                  view='period', period_s=.4, span_s=.999)
    values.update(changes)
    return FrameInput(**values)


def test_period_view_keeps_multiple_cycles_without_centering_first_edge():
    r = evaluate(periodic(), load_config('rigol'))
    assert r.label == 'ok'
    assert r.metrics['visible_periods'] == pytest.approx(2.4975)
    assert 't_offset' not in r.suggestion


def test_period_view_requires_period_and_enough_visible_cycles():
    cfg = load_config('rigol')
    assert evaluate(periodic(period_s=None), cfg).label == 'diagnose'
    r = evaluate(periodic(span_s=.1, tdiv=.01), cfg)
    assert r.label == 'shift_timebase'
    assert tools.frame_fix_scpi(r.label, r) == [':TIM:MAIN:SCAL 0.1']
    assert evaluate(periodic(raw_max=255), cfg).metrics['clipped']


@pytest.mark.parametrize('period', [0, -1, float('nan'), float('inf')])
def test_invalid_period_is_rejected(period):
    assert evaluate(periodic(period_s=period), load_config('rigol')).label == 'diagnose'


def test_period_trigger_accepts_interior_level_and_rejects_near_rail():
    cfg = load_config('rigol')
    assert evaluate(periodic(vtop=2.96, vmax=3.13), cfg).label == 'ok'
    assert evaluate(periodic(trig_level=3.2), cfg).label == 'move_trigger'


def test_period_menu_fix_rechecks_without_repeating_measurements(monkeypatch):
    fi = periodic(menu_rows=340)
    calls, writes = [], []
    monkeypatch.setattr(tools, 'read_frame', lambda *a: calls.append(True) or fi)
    monkeypatch.setattr(tools.menu_rules, 'bmp_to_array', lambda raw: raw)
    monkeypatch.setattr(tools.menu_rules, 'stats', lambda raw, cfg: {'hit_rows': 0})
    sc = SimpleNamespace(cfg=load_config('rigol'), settle=lambda s: None, w=writes.append, screenshot_bmp=lambda: b'image')
    out = tools.check_frame_on(sc, view='period', apply=True, jev_mode='off')
    assert out['ready'] and calls == [True] and writes == [':SYST:KEY:PRES MOFF']


@pytest.mark.parametrize('name', ['x=1', 'fn()', 'x; y', 'a[0]', 'a->b', 'a.'])
def test_read_var_does_not_evaluate_arbitrary_gel(monkeypatch, name):
    monkeypatch.setattr(ccs_daemon, 'S', SimpleNamespace(lock=threading.RLock(), last_cmd=0), raising=False)
    monkeypatch.setattr(ccs_daemon, '_need_ds', lambda: None)
    out = ccs_daemon.do({'cmd': 'read_var', 'names': [name]})
    assert not out['ok'] and 'variable names' in out['error']


def test_read_var_reads_field_only_while_halted(monkeypatch):
    session = SimpleNamespace(expressions=SimpleNamespace(evaluate=lambda name: 20))
    monkeypatch.setattr(ccs_daemon, 'S', SimpleNamespace(lock=threading.RLock(), session=session, last_cmd=0), raising=False)
    monkeypatch.setattr(ccs_daemon, '_need_ds', lambda: None)
    monkeypatch.setattr(ccs_daemon, '_connect', lambda xml: None)
    monkeypatch.setattr(ccs_daemon, '_halted', lambda: True)
    assert ccs_daemon.do({'cmd': 'read_var', 'names': ['CpuTimer0.InterruptCount']})['values'] == {'CpuTimer0.InterruptCount': 20}
    monkeypatch.setattr(ccs_daemon, '_halted', lambda: False)
    assert not ccs_daemon.do({'cmd': 'read_var', 'names': ['CpuTimer0.InterruptCount']})['ok']


def lan_module():
    path = Path(load_config('rigol')['rigol_mso_dir']) / 'tools/scope_lan.py'
    spec = importlib.util.spec_from_file_location('timer_test_lan', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FragmentedSocket:
    def __init__(self, chunks):
        self.chunks = list(chunks)

    def sendall(self, data):
        pass

    def recv(self, size):
        if not self.chunks:
            return b''
        part = self.chunks.pop(0)
        if len(part) > size:
            self.chunks.insert(0, part[size:])
        return part[:size]


@pytest.mark.parametrize('chunks', [[b'#13abc\n', b'RIGOL\n'],
                                   [b'#', b'1', b'3', b'ab', b'c', b'\n', b'RIGOL\n'],
                                   [b'#13abc\r', b'\n', b'RIGOL\n']])
def test_block_terminator_keeps_next_query_aligned(chunks):
    lan = lan_module()
    s = FragmentedSocket(chunks)
    assert lan.read_block(s, 'DATA?', consume_terminator=True) == b'abc'
    assert lan.query(s, '*IDN?') == 'RIGOL'


@pytest.mark.parametrize('chunks', [[b'#'], [b'#13a'], [b'#13abc']])
def test_eof_in_block_or_terminator_fails_promptly(chunks):
    with pytest.raises(EOFError):
        lan_module().read_block(FragmentedSocket(chunks), 'DATA?', consume_terminator=True)


def bench_module():
    spec = importlib.util.spec_from_file_location('timer_bench_test', ROOT / 'bench/timer_flow.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_duty_fraction_is_converted_without_changing_driver_contract(tmp_path):
    bench = bench_module()
    e = bench.Experiment.__new__(bench.Experiment)
    e.mode = 'optimized'
    sc = SimpleNamespace(measure=lambda item: {'FREQ': 2.5, 'PWID': .2, 'NWID': .2, 'PDUT': .5}[item], w=lambda cmd: None)
    got = e.measure(sc, {'measurements': {'PER': .4, 'VTOP': 3.3, 'VBASE': 0}})
    assert got['PDUT_raw'] == .5 and got['PDUT'] == 50
    assert not bench.acceptance(got | {'FREQ': 3.0})
    assert not bench.acceptance(got | {'VTOP': float('nan')})


@pytest.mark.parametrize('chunks', [[], [b'RIGOL']])
def test_query_eof_cannot_be_mistaken_for_a_complete_reply(chunks):
    with pytest.raises(EOFError):
        lan_module().query(FragmentedSocket(chunks), '*IDN?')


def test_failed_run_restores_scope_and_releases_probe(tmp_path, monkeypatch):
    bench = bench_module()
    writes, released = [], []
    class FailedExperiment:
        def __init__(self, mode, output, nodelay):
            Path(output).mkdir(parents=True, exist_ok=True)
            self.cfg = {'scope': {}}
        @contextlib.contextmanager
        def scope(self):
            yield SimpleNamespace(q=lambda cmd: 'MSO5104', w=writes.append)
        def run(self, index):
            return dict(mode='baseline', index=index, ok=False, elapsed_s=1, stages_s={}, counts={}, error='load failed')
    monkeypatch.setattr(bench, 'Experiment', FailedExperiment)
    monkeypatch.setattr(bench.tools_ccs, 'ccs_env', lambda: dict(probe_present=True, probe={}, tools={}))
    monkeypatch.setattr(bench.tools_ccs, 'ccs_release', lambda: released.append(True) or {'ok': True})
    monkeypatch.setattr(bench.tools, 'menu', lambda **kw: {'visible': False})
    assert bench.main(['--mode', 'baseline', '--runs', '5', '--output', str(tmp_path)]) == 1
    assert released == [True] and writes[-1] == ':RUN'
