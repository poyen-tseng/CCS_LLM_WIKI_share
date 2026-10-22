"""Offline check of the Timer0 settings in ../Init.h and ../Init.c (no board needed).

CPU Timer period (F28004x TRM): T = (PRD + 1) * (TDDR + 1) / SYSCLK.
TDDR is TPRH:TPR bits 15:8 / 7:0 -> divider value = TDDRH:TDDR.
HW_PART 1: GPIO1 toggles every ISR (100 Hz), GPIO2 pulses every ISR.
HW_PART 2: GPIO2 toggles every ISR (500 Hz), GPIO1 every 5 ISRs (100 Hz), GPIO0 pulses.

Run:  python -I timer_math.py      (from this tools/ folder or anywhere)
"""
import re
import sys
from pathlib import Path

SYSCLK = 100e6          # InitSysCtrl(): 20 MHz XTAL x 10 / 2
TOL = 1e-2              # TASK.md: +/- 1 %

root = Path(__file__).resolve().parent.parent
hdr = (root / "Init.h").read_text(encoding="utf-8")
src = (root / "Init.c").read_text(encoding="utf-8")

m = re.search(r"^\s*#define\s+HW_PART\s+(\d+)", hdr, re.M)
if not m:
    sys.exit("FAIL: #define HW_PART not found in Init.h")
part = int(m.group(1))
if part not in (1, 2):
    sys.exit(f"FAIL: HW_PART = {part}, expected 1 or 2")

# PRD sits in an #if HW_PART == 1 / #else block; pick the branch for this part.
prds = re.findall(r"CpuTimer0Regs\.PRD\.all\s*=\s*(0[xX][0-9a-fA-F]+|\d+)", src)
if len(prds) != 2:
    sys.exit(f"FAIL: expected 2 PRD assignments (HW_PART 1 / 2) in Init.c, found {len(prds)}")
prd = int(prds[part - 1], 0)


def reg(name: str) -> int:
    m = re.search(rf"CpuTimer0Regs\.{name}\.all\s*=\s*(0[xX][0-9a-fA-F]+|\d+)", src)
    if not m:
        sys.exit(f"FAIL: CpuTimer0Regs.{name}.all not found in Init.c")
    return int(m.group(1), 0)


tpr, tprh = reg("TPR"), reg("TPRH")
tddr = ((tprh & 0xFF) << 8) | (tpr & 0xFF)
t_isr = (prd + 1) * (tddr + 1) / SYSCLK
f_isr = 1 / t_isr

# (signal, toggles every n ISRs, target Hz)
if part == 1:
    waves = [("GPIO1", 1, 100.0)]
    pulse = "GPIO2"
else:
    waves = [("GPIO1", 5, 100.0), ("GPIO2", 1, 500.0)]
    pulse = "GPIO0"

print(f"HW_PART = {part}")
print(f"Init.c : PRD = {prd}, TPR = 0x{tpr:04X}, TPRH = 0x{tprh:04X} -> TDDR = {tddr}")
print(f"ISR period = (PRD+1)(TDDR+1)/SYSCLK = {t_isr * 1e3:.6f} ms ({f_isr:.4f} Hz)")
t_design = 1 / (2 * waves[0][1] * waves[0][2])  # ISR period the design needs
print(f"Design ISR period {t_design * 1e3:g} ms -> lecture PRD = SYSCLK x T = {SYSCLK * t_design:.0f}"
      f", TRM-exact PRD = {SYSCLK * t_design - 1:.0f}")
ok = True
for name, n, target in waves:
    f = f_isr / (2 * n)
    good = abs(f - target) / target <= TOL
    ok &= good
    print(f"{name} square = {f:.4f} Hz (toggle every {n} ISR, half period {n * t_isr * 1e3:.5f} ms)"
          f"  target {target:g} Hz  {'ok' if good else 'OUT OF RANGE'}")
target_isr = 1 / t_design                        # 200 Hz (part 1), 1 kHz (part 2)
good = abs(f_isr - target_isr) / target_isr <= TOL
ok &= good
print(f"{pulse} ISR pulse rate = {f_isr:.4f} Hz  target {target_isr:g} Hz  {'ok' if good else 'OUT OF RANGE'}")
print(f"PRD from a measured pulse rate f: PRD = SYSCLK / f - 1 = {SYSCLK / f_isr - 1:.0f}")

print()
print("PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
