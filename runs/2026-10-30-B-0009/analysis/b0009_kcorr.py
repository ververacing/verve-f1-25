import csv, statistics as st, sys, math
from pathlib import Path
d = Path(sys.argv[1])
rows = list(csv.DictReader(open(d / "summary.csv")))
arms = {a["key"]: a for a in csv.DictReader(open(d / "arms.csv"))}
stock = {r["vehicle"]: r for r in csv.DictReader(open(d / "driver_rows_benchmark_austria.csv"))}
EX = {"8", "19"}
starts = sorted({int(r["start"]) for r in rows})
kb, kr = [], []
for s in starts:
    cars = [r for r in rows if int(r["start"]) == s and r["vehicle"] not in EX]
    m = lambda r: float(arms[r["vehicle"]]["level"]) if r["vehicle"] in arms else float(stock[r["vehicle"]]["mistakes"])
    rs = lambda r: float(stock[r["vehicle"]]["reaction_speed"])
    kb.append(sum((0.24 - (1 - float(r["race_start_performance"]) / 100)) * m(r) for r in cars) / (0.08 * sum(m(r) ** 2 for r in cars)))
    kr.append(sum((0.35 - float(r["reaction_time"])) * rs(r) for r in cars) / (0.21 * sum(rs(r) ** 2 for r in cars)))
c = st.correlation(kb, kr)
print(f"per-start k: bad mean {st.mean(kb):.3f} sd {st.stdev(kb):.3f}; reaction mean {st.mean(kr):.3f} sd {st.stdev(kr):.3f}; corr {c:.3f} (n={len(starts)})")
# expected corr if both share the reaction k exactly: sd_true(k) ~ sd(kr) (kr noise is small), so corr ~ sd(kr)/sd(kb)
print(f"corr expected under one shared k (upper bound, kr noise ignored): {st.stdev(kr)/st.stdev(kb):.3f}")
