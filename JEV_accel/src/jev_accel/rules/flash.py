"""C: parse build / flash / debug output (gmake, run.bat edge_run.js, ccs-debug MCP errors).

edge_run.js prints: connecting, reset-then-load, "PC 0x87c0", READY, running, RAN.
Labels match questions.FLASH_STATES.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

APP_MAX = 0x3F0000  # anything at/above this is boot ROM on the F28004x

_PC = re.compile(r"^\s*PC\s+0x([0-9a-fA-F]+)\s*$", re.M)
_EXIT = re.compile(r"exit_code:\s*(-?\d+)")
_TIMEOUT = re.compile(r"timed? ?out|timeout", re.I)
_UP_TO_DATE = re.compile(r"is up to date|Nothing to be done", re.I)
_ERROR = re.compile(r"^.*\b(error|exception|failed)\b.*$", re.I | re.M)


NEXT_STEPS = {
    "ok_running": "proceed to measurement",
    "waiting_go": r"arm the scope (:SING, wait for WAIT), then write %TEMP%\gpio_edge_go.txt",
    "at_bootrom": "rerun edge_run.js (reset before loadProgram); do not reset after load",
    "retry": "retry the same command once; arm the scope sooner if 'waiting for scope arm' timed out",
    "fallback_dss": r"stop polling ccs-debug; run C:\ti\ccs2101\ccs\scripting\run.bat edge_run.js",
    "rebuild_needed": "touch the edited source (e.g. Init.c), rerun gmake, then reload",
}


@dataclass
class FlashParse:
    pc: int | None = None
    ready: bool = False
    ran: bool = False
    not_in_app: bool = False
    timeouts: int = 0
    arm_timeout: bool = False
    up_to_date: bool = False
    exit_code: int | None = None
    errors: list[str] = field(default_factory=list)


@dataclass
class FlashResult:
    parsed: FlashParse
    candidates: list[str]
    next_step: str
    behavior_matches: bool | None = None

    @property
    def label(self) -> str:
        return self.candidates[0] if self.candidates else "retry"

    @property
    def decisive(self) -> bool:
        return len(self.candidates) == 1

    def to_dict(self) -> dict:
        d = asdict(self)
        d["parsed"]["pc"] = hex(self.parsed.pc) if self.parsed.pc is not None else None
        return {**d, "label": self.label, "decisive": self.decisive}


def parse(text: str) -> FlashParse:
    p = FlashParse()
    pcs = _PC.findall(text)
    if pcs:
        p.pc = int(pcs[-1], 16)
    p.ready = bool(re.search(r"^\s*READY\s*$", text, re.M))
    p.ran = bool(re.search(r"^\s*RAN\s*$", text, re.M))
    p.not_in_app = "PC is not in the application" in text
    p.arm_timeout = "timed out waiting for scope arm" in text
    p.timeouts = len(_TIMEOUT.findall(text))
    p.up_to_date = bool(_UP_TO_DATE.search(text))
    ex = _EXIT.findall(text)
    p.exit_code = int(ex[-1]) if ex else None
    p.errors = [e.strip()[:200] for e in _ERROR.findall(text) if "GEL" not in e][:5]
    return p


def classify(p: FlashParse, expected_range: tuple[float, float] | None = None,
             measured: float | None = None) -> FlashResult:
    cands: list[str] = []
    matches = None
    if expected_range is not None and measured is not None:
        lo, hi = expected_range
        matches = lo <= measured <= hi
        if not matches:
            cands.append("rebuild_needed")
    if p.not_in_app or (p.pc is not None and p.pc >= APP_MAX):
        cands.append("at_bootrom")
    if p.up_to_date and "rebuild_needed" not in cands and matches is not True:
        cands.append("rebuild_needed")
    in_app = p.pc is not None and p.pc < APP_MAX
    if not cands:
        if p.ready and p.ran and in_app and p.exit_code in (0, None):
            cands.append("ok_running")
        elif p.ready and not p.ran and not p.arm_timeout and p.exit_code is None:
            cands.append("waiting_go")
        elif p.arm_timeout:
            cands.append("retry")
        elif p.timeouts >= 2 and not p.ready:
            cands.append("fallback_dss")
        elif p.timeouts == 1 or (p.exit_code not in (0, None)):
            cands.append("retry")
    label = cands[0] if cands else "retry"
    return FlashResult(p, cands, NEXT_STEPS[label], matches)
