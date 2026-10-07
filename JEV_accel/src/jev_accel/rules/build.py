"""F: classify gmake / cl2000 / ccs-server-cli build output. Labels match questions.BUILD_ERRORS.

The regexes come from real logs (tests/fixtures/logs/build_*.txt, made by fault injection on a copy of
LED_test on 2026-10-07): cl2000 prints `"file", line N: error #NNNN: ...`, the linker `error #10xxx-D`.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

# priority order when several fire: a missing tool hides everything else, a header error hides the
# follow-on syntax errors, and the linker only runs when every file compiled
ORDER = ("missing_compiler", "slow_path", "include_path", "syntax_error", "undefined_symbol",
         "memory_placement", "stale_build", "other_error", "ok")

NEXT_STEPS = {
    "missing_compiler": "the compiler in the project is not installed: point CG_TOOL_ROOT / the .cproject at an installed "
                        "one (ccs_env lists it), e.g. ccs-server-cli -application com.ti.ccs.apps.modifyProject "
                        "-ccs.compilerVersion 25.11.1.LTS, or edit the hand-kept Debug/*.mk",
    "slow_path": "the project is on a cloud / network drive: copy it to a local folder (D:/code/_TI_CCS_no_chinese) and build there",
    "include_path": "a header was not found: fix the #include name or add the folder to --include_path",
    "syntax_error": "fix the source at the reported file:line (the first error; later ones are often follow-on)",
    "undefined_symbol": "a function/variable is declared but not defined or not linked: add its .c to the build "
                        "(subdir_vars.mk / sources) or fix the name",
    "memory_placement": "a section does not fit its memory range: move it (#pragma DATA_SECTION / linker .cmd) or shrink it",
    "stale_build": "gmake said up to date but a source is newer than the .out: touch the source and rebuild (ccs_build does this)",
    "other_error": "read the error lines in errors[]; the rules did not recognize them",
    "ok": "build is current; next: ccs_map_check / ccs_load",
}

_ERR_LINE = re.compile(r'^"(?P<file>[^"]+)", line (?P<line>\d+): (?:fatal )?error #(?P<code>\d+)(?:-D)?: (?P<msg>.*)$', re.M)
_LINK_ERR = re.compile(r"^(?:\"[^\"]+\", line \d+: )?error #(?P<code>10\d{3})(?:-D)?: (?P<msg>.*)$", re.M)
_WARN = re.compile(r'^"(?P<file>[^"]+)", line (?P<line>\d+): warning #(?P<code>\d+)(?:-D)?: (?P<msg>.*)$', re.M)
_MISSING_TOOL = re.compile(r"process_begin: CreateProcess\(NULL, (?P<exe>\S*cl2000)", re.I)
_CLI_COMPILER = re.compile(r"compiler.{0,80}(not (?:found|installed|available)|could not be found)", re.I)
_UNDEF_SYM = re.compile(r"^\s*(_\w+)\s+\S+\.obj\s*$", re.M)
_UP_TO_DATE = re.compile(r"is up to date|Nothing to be done", re.I)
_BUILT = re.compile(r"Finished building target: \"([^\"]+)\"")
_GMAKE_FAIL = re.compile(r"gmake(?:\[\d\])?: \*\*\* .*Error \d+|not remade because of errors|Compilation failure")
_EXIT = re.compile(r"exit_code: (-?\d+)")
_SLOW_ROOT = re.compile(r"^(?:[g-zG-Z]:[\\/](?:我的雲端硬碟|My Drive)|\\\\)", re.I)
_CLEAN_NOISE = re.compile(r"^(Could Not Find|找不到) ", re.M)  # DEL /F on a missing .d during `gmake clean`


@dataclass
class BuildParse:
    errors: list[dict] = field(default_factory=list)       # {file, line, code, msg}
    link_errors: list[dict] = field(default_factory=list)  # {code, msg}
    warnings: list[dict] = field(default_factory=list)
    missing_tool: str | None = None
    undefined: list[str] = field(default_factory=list)
    up_to_date: bool = False
    built: list[str] = field(default_factory=list)
    failed: bool = False
    exit_code: int | None = None
    clean_noise: int = 0
    unknown_error_lines: list[str] = field(default_factory=list)


@dataclass
class BuildResult:
    parsed: BuildParse
    candidates: list[str]
    newer_sources: list[str]

    @property
    def label(self) -> str:
        return self.candidates[0] if self.candidates else "other_error"

    @property
    def decisive(self) -> bool:
        """Any recognized cause is decisive (ORDER settles several); only unrecognized error text goes to Jev."""
        return self.label != "other_error"

    @property
    def next_step(self) -> str:
        return NEXT_STEPS[self.label]

    def to_dict(self) -> dict:
        return {**asdict(self), "label": self.label, "decisive": self.decisive, "next_step": self.next_step}


def parse(text: str) -> BuildParse:
    p = BuildParse()
    for m in _ERR_LINE.finditer(text):
        if int(m["code"]) >= 10000:  # linker diagnostics (#10xxx) can carry a .cmd file:line; they are not compile errors
            continue
        p.errors.append({"file": m["file"], "line": int(m["line"]), "code": int(m["code"]), "msg": m["msg"].strip()[:200]})
    for m in _LINK_ERR.finditer(text):
        p.link_errors.append({"code": int(m["code"]), "msg": m["msg"].strip()[:300]})
    for m in _WARN.finditer(text):
        p.warnings.append({"file": m["file"], "line": int(m["line"]), "code": int(m["code"]), "msg": m["msg"].strip()[:160]})
    m = _MISSING_TOOL.search(text)
    p.missing_tool = m["exe"] if m else ("compiler (ccs-server-cli)" if _CLI_COMPILER.search(text) else None)
    if any(e["code"] == 10234 for e in p.link_errors):
        p.undefined = sorted(set(_UNDEF_SYM.findall(text)))
    p.up_to_date = bool(_UP_TO_DATE.search(text))
    p.built = _BUILT.findall(text)
    p.failed = bool(_GMAKE_FAIL.search(text))
    ex = _EXIT.findall(text)
    p.exit_code = int(ex[-1]) if ex else None
    p.clean_noise = len(_CLEAN_NOISE.findall(text))
    known = {e["msg"][:60] for e in p.errors} | {e["msg"][:60] for e in p.link_errors}
    for line in text.splitlines():
        s = line.strip()
        if re.search(r"\berror\b", s, re.I) and "cl2000" not in s and not _GMAKE_FAIL.search(s) \
                and not any(k and k in s for k in known) and "error detected in the compilation" not in s:
            p.unknown_error_lines.append(s[:200])
    p.unknown_error_lines = p.unknown_error_lines[:8]
    return p


def classify(p: BuildParse, newer_sources: list[str] | None = None, project_dir: str = "",
             elapsed_s: float | None = None) -> BuildResult:
    newer = list(newer_sources or [])
    c: set[str] = set()
    if p.missing_tool:
        c.add("missing_compiler")
    if project_dir and _SLOW_ROOT.match(project_dir) and (elapsed_s is None or elapsed_s > 120):
        c.add("slow_path")
    for e in p.errors:
        c.add("include_path" if e["code"] == 1965 or "cannot open source file" in e["msg"] else "syntax_error")
    codes = {e["code"] for e in p.link_errors}
    if 10234 in codes:
        c.add("undefined_symbol")
    if 10099 in codes or any("placement" in e["msg"] for e in p.link_errors):
        c.add("memory_placement")
    if p.up_to_date and newer and not p.built:
        c.add("stale_build")
    failed = p.failed or (p.exit_code not in (0, None))
    if failed and not c:
        c.add("other_error")
    if not c and p.unknown_error_lines and not p.built and not p.up_to_date:
        c.add("other_error")
    if not c:
        c.add("ok")
    return BuildResult(p, [k for k in ORDER if k in c], newer)
