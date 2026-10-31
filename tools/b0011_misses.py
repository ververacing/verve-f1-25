"""B-0011 diagnostic (descriptive, not part of the criterion): every reaction-envelope miss with its side and margin.

Usage: python3 tools/b0011_misses.py <run folder> <table.csv> <vehicle map csv>
"""
import csv
import sys
from pathlib import Path

run, table, vmap = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
t = {r["label"]: r for r in csv.DictReader(table.open())}
drv = {r["vehicle"]: r["driver"] for r in csv.DictReader(vmap.open())}
rows = [r for r in csv.DictReader((run / "summary.csv").open()) if r["vehicle"] not in ("8", "19")]
starts = sorted({int(r["start"]) for r in rows})
print("start,k,driver,vehicle,rs,reaction,lo,hi,side,outside_by_s")
n = 0
for s in starts:
    cars = [(r, float(t[drv[r["vehicle"]]]["reaction_speed_verve"]), float(r["reaction_time"])) for r in rows if int(r["start"]) == s]
    k = sum((0.35 - rt) * 0.21 * rs for _, rs, rt in cars) / sum((0.21 * rs) ** 2 for _, rs, _ in cars)
    for r, rs, rt in cars:
        lo, hi = 0.28 - 0.24 * k * rs, 0.42 - 0.18 * k * rs
        if rt < lo - 0.005 or rt > hi + 0.005:
            n += 1
            side = "below" if rt < lo else "above"
            print(f"{s},{k:.3f},{drv[r['vehicle']]},{r['vehicle']},{rs:.4f},{rt:.4f},{lo:.4f},{hi:.4f},{side},{(lo - rt) if side == 'below' else (rt - hi):.4f}")
print(f"misses {n} of {len(rows)}")
