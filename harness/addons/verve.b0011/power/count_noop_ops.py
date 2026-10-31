import csv, json, sys
from pathlib import Path
w = Path(sys.argv[1])
ops = json.load(open(w / "harness/addons/verve.b0011/db/verve.json"))["ops"]
rows = {r["label"]: r for r in csv.DictReader(l for l in open(w / "docs/stock/driver_characteristics_grid.csv") if not l.startswith("#"))}
curves = {(r["stats_label"], r["dataset"]): r["evolution"] for r in csv.DictReader(l for l in open(w / "docs/stock/pace_curves_grid.csv") if not l.startswith("#"))}
def pts(e): return [tuple(float(v) for v in p.split(":")) for p in e.split(",")[1:] if p.split(":")[0] not in ("maxx", "miny", "maxy")]
same_c = same_p = near_p = 0
for o in ops:
    if o["field"].startswith("driver_characteristics."):
        lab = o["select"].split("=")[1].rstrip("]"); n = o["field"].split(".")[1]
        same_c += float(rows[lab][n]) == float(o["value"])
    else:
        h = o["select"].split("driver=")[1].split("]")[0]; ds = o["select"].split("_metadata_=")[1].split("]")[0]
        a, b = pts(curves[(h, ds)]), pts(o["value"])
        same_p += a == b; near_p += a != b and all(abs(x - y) < 1e-3 and abs(p - q) < 1e-9 for (p, x), (q, y) in zip(a, b))
print(f"ops {len(ops)}: characteristic ops equal to stock {same_c}; pace curves equal {same_p}, equal after rounding only {near_p}")
print(f"expected overwritten if the build drops exact equals: {52 + len(ops) - same_c - same_p}")
