import csv, statistics as st, sys, math
from pathlib import Path
d = Path(sys.argv[1])
rows = list(csv.DictReader(open(d / "summary.csv")))
arms = {a["key"]: a for a in csv.DictReader(open(d / "arms.csv"))}
stock = {r["vehicle"]: r for r in csv.DictReader(open(d / "driver_rows_benchmark_austria.csv"))}
EX = {"8", "19"}
starts = sorted({int(r["start"]) for r in rows})
by = {s: [r for r in rows if int(r["start"]) == s] for s in starts}
def kr(rs_):
    n = sum((0.35 - float(r["reaction_time"])) * float(stock[r["vehicle"]]["reaction_speed"]) for r in rs_)
    return n / (0.21 * sum(float(stock[r["vehicle"]]["reaction_speed"]) ** 2 for r in rs_))
def ols(x, y):
    n = len(x); mx, my = st.mean(x), st.mean(y); sxx = sum((a - mx) ** 2 for a in x)
    b = sum((a - mx) * (c - my) for a, c in zip(x, y)) / sxx
    res = [c - (my + b * (a - mx)) for a, c in zip(x, y)]
    se = math.sqrt(sum(e * e for e in res) / (n - 2) / sxx)
    return b, se
# driver-level means: b and rs-adjusted reaction residual
lv, mb, mr = [], [], []
for v, a in arms.items():
    bs, rr = [], []
    for s in starts:
        k = kr([r for r in by[s] if r["vehicle"] not in EX])
        me = [r for r in by[s] if r["vehicle"] == v][0]
        bs.append(1 - float(me["race_start_performance"]) / 100)
        rr.append(float(me["reaction_time"]) - (0.35 - 0.21 * k * float(stock[v]["reaction_speed"])))
    lv.append(float(a["level"])); mb.append(st.mean(bs)); mr.append(st.mean(rr))
print("driver-level (8 drivers, 6 df): slope, SE, t")
b, se = ols(lv, mb); print(f"mean b on level: {b:.4f} {se:.4f} {b/se:.2f}")
b, se = ols(lv, mr); print(f"rs-adjusted reaction residual on level: {b:.4f} {se:.4f} {b/se:.2f}")
# stock field: within-start correlation of b_rel and rt_rel (is reaction tied to the bad-start draw?)
xb, xr = [], []
for s in starts:
    f = [r for r in by[s] if r["vehicle"] not in EX and r["vehicle"] not in arms]
    k = kr([r for r in by[s] if r["vehicle"] not in EX])
    for r in f:
        xb.append(1 - float(r["race_start_performance"]) / 100)
        xr.append(float(r["reaction_time"]) - (0.35 - 0.21 * k * float(stock[r["vehicle"]]["reaction_speed"])))
mx, my = st.mean(xb), st.mean(xr)
c = sum((a - mx) * (b - my) for a, b in zip(xb, xr)) / math.sqrt(sum((a - mx) ** 2 for a in xb) * sum((b - my) ** 2 for b in xr))
print(f"stock field: corr(b, reaction residual) = {c:.3f} over {len(xb)} samples")
# stock field: does stock row mistakes predict the reaction residual?
xm = []
for s in starts:
    for r in by[s]:
        if r["vehicle"] not in EX and r["vehicle"] not in arms: xm.append(float(stock[r["vehicle"]]["mistakes"]))
b, se = ols(xm, xr); print(f"stock field: reaction residual on stock mistakes: {b:.4f} (naive SE {se:.4f})")
