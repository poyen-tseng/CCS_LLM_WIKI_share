"""Offline tests for the CCS side: .map check, build / DSS classification, verify parsing, probe owner,
build-file drift and content-hash stale detection. Inputs are the real logs and maps under tests/fixtures."""
import os
import time

import pytest

from jev_accel import replay, tools, tools_ccs
from jev_accel.rules import build, ccs

FX = replay.FIXTURES


@pytest.fixture(autouse=True)
def no_jev_key(monkeypatch):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    tools._gate = None


def _log(name: str) -> str:
    return tools_ccs._decode((FX / "logs" / name).read_bytes())


# --- .map --------------------------------------------------------------------------------------
def test_flash_map_of_led_test_is_ok():
    r = ccs.check_map((FX / "map" / "LED_test.map").read_text(encoding="utf-8"), "flash")
    assert r["ok"], r["problems"]
    assert r["codestart"] == "0x80000" and r["ramfunc"] == {"load": "0x81000", "size": "0x4b", "run": "0x8000"}
    assert r["symbols"]["_main"] == "0x813a2"  # the PC the daemon reports right after loadProgram


def test_ram_build_rejected_as_flash():
    text = (FX / "map" / "GPIO_EX1.map").read_text(encoding="utf-8")
    assert ccs.check_map(text, "ram")["ok"]
    bad = ccs.check_map(text, "flash")
    assert not bad["ok"] and any("codestart at 0x0" in p for p in bad["problems"])


def test_nearly_full_ignores_peripheral_frames():
    r = ccs.check_map((FX / "map" / "LED_test.map").read_text(encoding="utf-8"), "flash")
    assert r["nearly_full"] == []


# --- build -------------------------------------------------------------------------------------
def test_undefined_symbol_names_are_extracted():
    p = build.parse(_log("build_undef.txt"))
    assert p.undefined == ["_MissingFunc"] and {e["code"] for e in p.link_errors} == {10234, 10010}


def test_linker_error_on_cmd_line_is_not_a_syntax_error():
    r = build.classify(build.parse(_log("build_placement.txt")))
    assert r.candidates == ["memory_placement"]


def test_missing_compiler_reports_the_tool_path():
    p = build.parse(_log("build_compiler.txt"))
    assert p.missing_tool.endswith("ti-cgt-c2000_22.6.0.LTS/bin/cl2000")


def test_big5_clean_noise_is_harmless():
    p = build.parse(_log("build_clean.txt"))
    assert p.clean_noise >= 2 and build.classify(p).label == "ok"


def test_unknown_error_text_is_not_decisive():
    r = build.classify(build.parse(_log("build_syn_gnu_include.txt")))
    assert r.label == "other_error" and not r.decisive


# --- DSS ---------------------------------------------------------------------------------------
def test_error_260_means_busy_when_the_probe_is_plugged_in():
    text = _log("dss_busy.txt")
    assert tools_ccs.decide_dss(text, True, None, "off")["state"] == "probe_busy"
    assert tools_ccs.decide_dss(text, False, None, "off")["state"] == "no_probe"


def test_terminal_header_literals_are_ignored():
    assert ccs.classify_dss(_log("dss_connect_ok_253247.txt")).label == "connect_ok"


def test_trouble_writing_memory_is_flash_fail():
    assert ccs.classify_dss(_log("dss_syn_trouble_writing.txt")).label == "flash_fail"


# --- verify / owner / drift --------------------------------------------------------------------
def test_verify_parse_real_feedback_output():
    v = ccs.parse_verify(_log("verify_fb.txt"))
    assert v["overall"] is True and v["failed"] == [] and v["exit_code"] == 0 and len(v["checks"]) == 4


def test_verify_parse_failure():
    v = ccs.parse_verify("RATE: PASS\nFORMAT: FAIL\nOVERALL: FAIL\nEXIT_CODE=1")
    assert v["overall"] is False and v["failed"] == ["FORMAT"]


@pytest.mark.parametrize("procs, alive, conn, owner", [
    ([], False, False, "free"),
    ([], True, True, "daemon"),
    ([{"name": "java", "pid": 1}], True, False, "dss_script"),
    ([{"name": "node", "pid": 2, "path": "C:\\ti\\ccs2101\\ccs\\ccs_base\\cloudagent\\node.exe"}], False, False, "script_maybe"),
    ([{"name": "node", "pid": 2}], True, False, "free"),  # the daemon's own CloudAgent, released
    ([{"name": "ccstudio", "pid": 3}, {"name": "DSLite", "pid": 4}], False, False, "ide_maybe"),
])
def test_probe_owner(procs, alive, conn, owner):
    assert ccs.probe_owner(procs, alive, conn)["owner"] == owner


def _flags():
    return ccs.build_flags((FX / "map" / "sp_makefile").read_text(encoding="utf-8"),
                           (FX / "map" / "sp_subdir_rules.mk").read_text(encoding="utf-8"))


def test_build_flags_of_serial_plotter():
    f = _flags()
    assert "_FLASH" in f["defines"] and "../280049C_FLASH_lnk.cmd" in f["linker_cmds"]
    assert f["compiler"] and all("25.11.1" in c for c in f["compiler"]) and f["abi"] == "coffabi"


def test_drift_key_change_is_decisive():
    a, b = _flags(), _flags()
    b["defines"] = [d for d in b["defines"] if d != "_FLASH"]
    d = ccs.drift(a, b)
    assert d["equivalent"] is False and "defines" in d["key_changed"]


def test_drift_other_option_only_is_undecided():
    a, b = _flags(), _flags()
    b["other_options"] = sorted(set(b["other_options"]) | {"--diag_suppress=10063"})
    assert ccs.drift(a, b)["equivalent"] is None
    assert ccs.drift(a, _flags())["equivalent"] is True


# --- stale detection by content ---------------------------------------------------------------
def test_changed_sources_uses_hashes_not_mtimes(tmp_path, monkeypatch):
    monkeypatch.setattr(tools_ccs, "STATE_DIR", tmp_path / "state")
    pd = tmp_path / "Proj"
    (pd / "Debug").mkdir(parents=True)
    src = pd / "main.c"
    src.write_text("int a;\n")
    (pd / "Debug" / "Proj.out").write_bytes(b"x")
    tools_ccs._save_state(pd, built_hashes=tools_ccs._hashes(pd))
    old = time.time() - 3600
    src.write_text("int b;\n")
    os.utime(src, (old, old))  # copied with an old mtime: gmake would say 'up to date'
    ch = tools_ccs.changed_sources(pd)
    assert ch == {"basis": "hash", "changed": ["main.c"]}
