"""B-0009 extra readout: per-driver medians, tagged-driver k vs stock-field k, reaction control adjusted for rs."""
import csv, random, statistics as st, sys
from pathlib import Path

d = Path(sys.argv[1])
rows = list(csv.DictReader(open(d / "summary.csv")))
arms = {a["key"]: a for a in csv.DictReader(open(d / "arms.csv"))}
stock = {r["vehicle"]: r for r in csv.DictReader(open(d / "driver_rows_benchmark_austria.csv"))}
EXCL = {"8", "19"}
starts = sorted({int(r["start"]) for r in rows})
by = {s: [r for r in rows if int(r["start"]) == s] for s in starts}


def ols(x, y):
    mx, my = st.mean(x), st.mean(y)
    sxx = sum((a - mx) ** 2 for a in x)
    return sum((a - mx) * (b - my) for a, b in zip(x, y)) / sxx


def per_start(s):
    """k_bad and k_rt from the stock field and the tagged cars of one start (fixed-intercept estimators)."""
    out = {}
    field = [r for r in by[s] if r["vehicle"] not in EXCL and r["vehicle"] not in arms]
    tag = [r for r in by[s] if r["vehicle"] in arms]
    def kb(rs, mfun):
        num = sum((0.24 - (1 - float(r["race_start_performance"]) / 100)) * mfun(r) for r in rs)
        return num, 0.08 * sum(mfun(r) ** 2 for r in rs)
    def kr(rs):
        num = sum((0.35 - float(r["reaction_time"])) * float(stock[r["vehicle"]]["reaction_speed"]) for r in rs)
        return num, 0.21 * sum(float(stock[r["vehicle"]]["reaction_speed"]) ** 2 for r in rs)
    out["bad_field"] = kb(field, lambda r: float(stock[r["vehicle"]]["mistakes"]))
    out["bad_tag"] = kb(tag, lambda r: float(arms[r["vehicle"]]["level"]))
    out["rt_all"] = kr([r for r in by[s] if r["vehicle"] not in EXCL])
    return out


def pooled(sample, key):
    num = den = 0.0
    for s in sample:
        n, dd = per_start(s)[key]
        num += n; den += dd
    return num / den


def rt_adj_slope(sample):
    """slope of reaction residual (rt - (0.35 - 0.21 k_s rs)) on level, k_s from all non-Ferrari cars of start s."""
    x, y = [], []
    for s in sample:
        n, dd = per_start(s)["rt_all"]; k = n / dd
        for r in by[s]:
            if r["vehicle"] in arms:
                rs = float(stock[r["vehicle"]]["reaction_speed"])
                x.append(float(arms[r["vehicle"]]["level"]))
                y.append(float(r["reaction_time"]) - (0.35 - 0.21 * k * rs))
    return ols(x, y)


stats = {
    "k_bad_stock_field": lambda smp: pooled(smp, "bad_field"),
    "k_bad_tagged": lambda smp: pooled(smp, "bad_tag"),
    "k_rt_all": lambda smp: pooled(smp, "rt_all"),
    "rt_resid_slope_on_level": rt_adj_slope,
}
point = {k: f(starts) for k, f in stats.items()}
point["k_tagged_minus_field"] = point["k_bad_tagged"] - point["k_bad_stock_field"]
rng = random.Random(1)
boot = {k: [] for k in point}
for _ in range(2000):
    smp = [rng.choice(starts) for _ in starts]
    v = {k: f(smp) for k, f in stats.items()}
    v["k_tagged_minus_field"] = v["k_bad_tagged"] - v["k_bad_stock_field"]
    for k in v:
        boot[k].append(v[k])
print("statistic,estimate,boot_se,z")
for k in point:
    se = st.stdev(boot[k])
    print(f"{k},{point[k]:.4f},{se:.4f},{point[k] / se:.2f}")

print()
print("level,driver,vehicle,stock_mistakes,stock_rs,median_b_rel,median_b,median_rt_rel,mean_b")
for v, a in sorted(arms.items(), key=lambda kv: (float(kv[1]["level"]), kv[1]["driver"])):
    brel, b, rrel = [], [], []
    for s in starts:
        field = [r for r in by[s] if r["vehicle"] not in EXCL and r["vehicle"] not in arms]
        fb = st.median([1 - float(r["race_start_performance"]) / 100 for r in field])
        fr = st.median([float(r["reaction_time"]) for r in field])
        me = [r for r in by[s] if r["vehicle"] == v][0]
        bb = 1 - float(me["race_start_performance"]) / 100
        b.append(bb); brel.append(bb - fb); rrel.append(float(me["reaction_time"]) - fr)
    print(f"{a['level']},{a['driver']},{v},{a['stock_row']},{stock[v]['reaction_speed']},"
          f"{st.median(brel):+.3f},{st.median(b):.3f},{st.median(rrel):+.3f},{st.mean(b):.3f}")
