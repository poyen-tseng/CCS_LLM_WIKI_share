"""Read-only checks against the real MSO5104 (skipped when the scope is not reachable within 1 s).

These never change scope settings; the fault-injection checks (offset +1.65, probe 1x) are manual,
see README "硬體驗證".
"""
import socket

import pytest

from jev_accel import tools
from jev_accel.config import load_config
from jev_accel.scope_io import open_scope


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
        assert "RIGOL" in s.q("*IDN?").upper()
        assert len(s.screenshot_bmp()) > 100_000
        assert "RIGOL" in s.q("*IDN?").upper()  # drain() kept the next reply aligned


def test_check_frame_runs_end_to_end():
    out = tools.check_frame(jev_mode="off")
    assert out["next_fix"] in tools.Q.FRAME_FIXES
    assert {"vpp_div", "clipped", "center_err_div"} <= set(out["l0"]["metrics"])


def test_menu_reads_without_pressing_anything():
    out = tools.menu(hide=False, jev_mode="off")
    assert out["visible"] in (True, False) and out["stats"]["band_rows"] == 340
