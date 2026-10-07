"""Jev question definitions for bridges A-D (JEV_ACCELERATION.md section 2).

Plain dicts in the SDK's ChoiceModel / NoulModel shape, so the rules and tests don't import the SDK.
The label sets are shared with the L0 rules: a rule result and a Jev answer are always comparable.
"""
from __future__ import annotations

# A: frame acceptance. Order = L0 priority (first match wins when several rules fire).
FRAME_FIXES: dict[str, str] = {
    "diagnose": "flat trace or no trigger; the capture itself failed, run the no-trigger diagnosis",
    "fix_probe": "channel probe ratio differs from the 10x probe actually attached",
    "hide_menu": "the side menu panel covers the right part of the waveform",
    "fix_offset": "trace is vertically off-center or pushed off screen by a wrong offset (often the wrong sign)",
    "change_vdiv": "trace is centered but clipped (overshoot) or too small; change V/div",
    "move_trigger": "trigger level is not at 50% of VBASE/VTOP, so the edge is not at the trigger point",
    "shift_timebase": "edge is not horizontally centered (more than 0.3 div from the center)",
    "clear_meas": "a leftover measurement or readout overlay covers the waveform",
    "rescreen": "screen was captured before it refreshed after a settings change; wait and capture again",
    "ok": "nothing to change; the frame can be saved for the report",
}

# B: why a single-shot capture is flat / never triggered. Order = L0 priority; wiring is last on purpose.
ROOT_CAUSES: dict[str, str] = {
    "pc_in_bootrom": "CPU PC is in boot ROM (0x3Fxxxx), e.g. reset after load; the application never ran",
    "stale_build": "the .out is older than the source or gmake said 'up to date'; old code is running",
    "probe_ratio": "channel probe setting does not match the 10x probe, so volts and trigger level are scaled "
                   "wrong (a real signal still shows, at 1/10 or 10x; a ratio error cannot make a live trace sit at 0 V)",
    "trig_level_out_of_range": "trigger level was clamped by the scope or lies outside the signal swing",
    "sweep_mode": "sweep is AUTO / not armed single, so the one-time edge was missed",
    "wiring": "no signal reaches the probe: tip/ground not connected or the pin is not driven (a live AUTO "
              "trace sitting at 0 V); choose only when every software cause is ruled out",
}

# C: build / flash / debug state.
FLASH_STATES: dict[str, str] = {
    "ok_running": "PC in application range (RAM 0x8000-0x1FFFF or flash 0x80000+), READY and RAN printed",
    "waiting_go": "program loaded and halted (READY) but still waiting for the scope go-file",
    "at_bootrom": "PC 0x3Fxxxx or 'PC is not in the application'; reload without reset after load",
    "retry": "a single transient timeout or connection error; retry the same command once",
    "fallback_dss": "the ccs-debug MCP timed out repeatedly; use run.bat edge_run.js instead",
    "rebuild_needed": "gmake said up to date or the measured behavior contradicts the source settings",
}


def frame_questions() -> dict:
    return {
        "report_ready": {
            "type": "noul",
            "instructions": "Is this oscilloscope frame ready to be saved as a lab-report screenshot?",
            "criteria": {
                "true": "edge within 0.3 div of center, no clipping, menu hidden, trigger at 50%, screen refreshed",
                "false": "any of: clipped, off-center, menu visible, stale screen, wrong probe ratio, flat trace",
            },
        },
        "next_fix": {
            "type": "choice",
            "instructions": "What single adjustment should be made next? Prefer the most fundamental problem.",
            "criteria": FRAME_FIXES,
        },
    }


def diagnose_questions() -> dict:
    return {
        "root_cause": {
            "type": "choice",
            "instructions": "Why did the single-shot capture show a flat line or never trigger?",
            "criteria": ROOT_CAUSES,
        },
        "fix_is_software": {
            "type": "noul",
            "instructions": "Can this be fixed by the agent (scope settings, rebuild, reload) without the human touching hardware?",
        },
    }


def flash_questions(with_behavior: bool = False) -> dict:
    q = {
        "flash_state": {
            "type": "choice",
            "instructions": "What is the state of the build / flash / debug step, from this terminal output?",
            "criteria": FLASH_STATES,
        }
    }
    if with_behavior:
        q["behavior_matches_source"] = {
            "type": "noul",
            "instructions": "Does the measured behavior match what the source code configuration should produce?",
            "criteria": {
                "true": "e.g. QSEL=2 with CTRL=255 gives a delay of tens of microseconds",
                "false": "e.g. QSEL=2 configured but the delay is only a few hundred nanoseconds",
            },
        }
    return q


def menu_questions() -> dict:
    return {
        "menu_visible": {
            "type": "noul",
            "instructions": "Is the RIGOL side menu panel visible, judging from these pixel statistics of a black-background screenshot?",
            "criteria": {
                "true": "a blue border column (x 850-862) is hit on many rows between y 200 and 540",
                "false": "few or no hits; the waveform area extends to the right edge",
            },
        }
    }


# F: why the build failed. Order = rules.build.ORDER (priority when several apply).
BUILD_ERRORS: dict[str, str] = {
    "missing_compiler": "the compiler version the project names is not installed (CreateProcess fails on cl2000, "
                        "or the CLI says the compiler is not found)",
    "slow_path": "the project sits on a cloud or network drive and the build stalls there",
    "include_path": "a header file cannot be opened (#include name wrong or include path missing)",
    "syntax_error": "a C / asm compile error in the source at a file:line",
    "undefined_symbol": "the linker cannot resolve a symbol: a function or variable is used but never defined or linked",
    "memory_placement": "a section does not fit its memory range in the linker command file",
    "stale_build": "gmake said up to date although a source file is newer than the .out",
    "other_error": "an error that is none of the above (tool crash, license, permission, makefile syntax)",
    "ok": "no error: the target was built or is genuinely up to date; clean-time 'Could Not Find' lines are harmless",
}

# G: state after a DSS / CCS scripting flash, connect or run step. Order = rules.ccs.DSS_ORDER.
DSS_STATES: dict[str, str] = {
    "no_probe": "Windows / the debugger does not see an XDS110 at all",
    "probe_busy": "the XDS110 is held by another process or debug session",
    "target_power": "the probe answers but the CPU / DAP does not (no power, reset held, cJTAG link down)",
    "connect_fail": "connecting to the CPU failed for another reason",
    "flash_fail": "erasing, programming or verifying the flash failed",
    "run_fail": "the program loaded but run / halt / reset failed",
    "timeout": "a scripting call timed out",
    "other_error": "an error that fits none of the above",
    "flash_ok": "program loaded and verified",
    "connect_ok": "connected to the CPU, no load requested",
}


def build_questions() -> dict:
    return {"build_error": {"type": "choice", "instructions": "What is the root cause of this build output? "
                            "Pick the first cause; later errors are often follow-on.", "criteria": BUILD_ERRORS}}


def dss_questions() -> dict:
    return {"dss_state": {"type": "choice", "instructions": "What happened in this debugger / flash script output?",
                          "criteria": DSS_STATES}}


def drift_questions() -> dict:
    return {"drift_equivalent": {
        "type": "noul",
        "instructions": "The IDE regenerated this project's build files. Do the changed compiler options leave the "
                        "generated code and the memory layout the same?",
        "criteria": {"true": "only diagnostics / advice / formatting options changed",
                     "false": "an option that changes code, ABI, memory model or optimization changed"},
    }}
