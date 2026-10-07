"""Replay all fixtures: python bench/replay.py [--jev auto|always|off] [--bridge frame ...]"""
import argparse
import json

from jev_accel import replay

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("--jev", choices=["auto", "always", "off"], default="auto")
p.add_argument("--bridge", action="append", choices=replay.BRIDGES)
p.add_argument("--json", action="store_true", help="print the summary as JSON instead of markdown")
a = p.parse_args()
s = replay.run(a.jev, tuple(a.bridge) if a.bridge else replay.BRIDGES)
print(json.dumps(s, ensure_ascii=False, indent=2) if a.json else replay.markdown(s))
if "jev_errors" in s:
    print("\nJev errors:", *s["jev_errors"], sep="\n- ")
print("\nsaved:", s["saved"])
