"""Offline check of the Timer0 period in ../Init.c (no board needed).

CPU Timer period (F28004x TRM): T = (PRD + 1) * (TDDR + 1) / SYSCLK.
TDDR is TPRH:TPR bits 15:8 / 7:0 -> divider value = TDDRH:TDDR.
GPIO0 toggles once per interrupt, so the square wave period is 2T.

Run:  python -I timer_math.py      (from this tools/ folder or anywhere)
"""
import re
import sys
from pathlib import Path

SYSCLK = 100e6          # InitSysCtrl(): 20 MHz XTAL x 10 / 2
TARGET_T = 0.2          # 3_TIMER_lecture.pdf p12: count 0.2 s
TOL = 1e-3              # 0.1 %

src = (Path(__file__).resolve().parent.parent / "Init.c").read_text(encoding="utf-8")


def reg(name: str) -> int:
    m = re.search(rf"CpuTimer0Regs\.{name}\.all\s*=\s*(0[xX][0-9a-fA-F]+|\d+)", src)
    if not m:
        sys.exit(f"FAIL: CpuTimer0Regs.{name}.all not found in Init.c")
    return int(m.group(1), 0)


prd, tpr, tprh = reg("PRD"), reg("TPR"), reg("TPRH")
tddr = ((tprh & 0xFF) << 8) | (tpr & 0xFF)

t_int = (prd + 1) * (tddr + 1) / SYSCLK
f_sq = 1 / (2 * t_int)

print(f"Init.c : PRD = {prd}, TPR = 0x{tpr:04X}, TPRH = 0x{tprh:04X} -> TDDR = {tddr}")
print(f"Interrupt period T  = (PRD+1)(TDDR+1)/SYSCLK = {t_int:.9f} s")
print(f"GPIO0 high = low    = {t_int * 1e3:.6f} ms, duty 50 %")
print(f"GPIO0 square wave   = {2 * t_int:.9f} s period, {f_sq:.7f} Hz")
print(f"Exact PRD for 0.2 s = {round(TARGET_T * SYSCLK / (tddr + 1)) - 1}")

# Lecture p7 worked examples (lecture writes the divider as "TDDR = 1", i.e. register 0).
print()
print("Lecture p7:")
print(f"  PRD for 0.2 s, divide-by-1  : {TARGET_T * SYSCLK:,.0f}  (< 2^32 = {2**32:,})")
print(f"  max, PRD 2^32, divide-by-1   : {2**32 / SYSCLK:.3f} s")
t_max = 2**32 * 2**16 / SYSCLK
print(f"  max, PRD 2^32, divide 2^16   : {t_max:,.2f} s = {t_max / 86400:.1f} days")

ok = abs(t_int - TARGET_T) / TARGET_T <= TOL and abs(f_sq - 2.5) / 2.5 <= TOL
print()
print("PASS" if ok else f"FAIL: T = {t_int} s is not 0.2 s +/- {TOL:.1%}")
sys.exit(0 if ok else 1)
