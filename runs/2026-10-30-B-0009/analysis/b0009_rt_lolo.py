import csv, statistics as st, sys, random
from pathlib import Path
d = Path(sys.argv[1])
rows = list(csv.DictReader(open(d / "summary.csv")))
arms = {a["key"]: a for a in csv.DictReader(open(d / "arms.csv"))}
stock = {r["vehicle"]: r for r in csv.DictReader(open(d / "driver_rows_benchmark_austria.csv"))}
EX = {"8", "19"}
starts = sorted({int(r["start"]) for r in rows})
by = {s: [r for r in rows if int(r["start"]) == s] for s in starts}
K = {}
for s in starts:
    c = [r for r in by[s] if r["vehicle"] not in EX]
    rs = lambda r: float(stock[r["vehicle"]]["reaction_speed"])
    K[s] = sum((0.35 - float(r["reaction_time"])) * rs(r) for r in c) / (0.21 * sum(rs(r) ** 2 for r in c))
def slope(smp, drop):
    x, y = [], []
    for s in smp:
        for r in by[s]:
            a = arms.get(r["vehicle"])
            if a and a["level"] != drop:
                x.append(float(a["level"])); y.append(float(r["reaction_time"]) - (0.35 - 0.21 * K[s] * float(stock[r["vehicle"]]["reaction_speed"])))
    mx, my = st.mean(x), st.mean(y)
    return sum((a - mx) * (b - my) for a, b in zip(x, y)) / sum((a - mx) ** 2 for a in x)
print("rs-adjusted reaction residual slope, leave one level out (bootstrap over starts, 2000, seed 1)")
for drop in ["0.02", "0.35", "0.65", "0.98"]:
    rng = random.Random(1); p = slope(starts, drop)
    bs = [slope([rng.choice(starts) for _ in starts], drop) for _ in range(2000)]
    se = st.stdev(bs); print(f"drop {drop}: {p:.4f} SE {se:.4f} z {p/se:.2f}")
