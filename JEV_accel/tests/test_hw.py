"""Read-only checks against the configured scope (skipped when it is not reachable within 1 s).

These never change scope settings (the Keysight menu check toggles Ink Saver for the black screenshot
and restores it); the fault-injection checks (offset +1 div, probe 1x) are manual, see README "硬體驗證".
"""
import socket

import pytest

from jev_accel import tools
from jev_accel.config import load_config
from jev_accel.scope_io import dialect_of, open_scope


def _reachable() -> bool:
    sc = load_config()["scope"]
    try:
        with socket.create_connection((sc["addr"], sc["port"]), timeout=1.0):
            return True
    except OSError:
        return False


pytestmark = [pytest.mark.hw, pytest.mark.skipif(not _reachable(), reason="scope not reachable")]


def test_idn_and_block_read_stay_in_sync():
    with open_scope() as s:
        vendors = dialect_of(s).idn_vendors
        assert any(v in s.q("*IDN?").upper() for v in vendors)
        assert len(s.screenshot_bmp()) > 10_000
        assert any(v in s.q("*IDN?").upper() for v in vendors)  # the block read kept the next reply aligned


def test_check_frame_runs_end_to_end():
    out = tools.check_frame(jev_mode="off")
    assert out["next_fix"] in tools.Q.FRAME_FIXES
    assert {"vpp_div", "clipped", "center_err_div"} <= set(out["l0"]["metrics"])


def test_menu_reads_without_pressing_anything():
    cfg = load_config()["menu"]
    out = tools.menu(hide=False, jev_mode="off")
    assert out["visible"] in (True, False) and out["stats"]["band_rows"] == cfg["y1"] - cfg["y0"]
