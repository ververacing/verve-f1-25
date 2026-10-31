import csv, random, statistics as st, sys
sp = sys.argv[1]
t = {r["label"]: r for r in csv.DictReader(open(f"{sp}/v02_table.csv"))}
vm = list(csv.DictReader(open(f"{sp}/vmap.csv")))
print("vehicle map columns:", list(vm[0].keys()))
lab = [r.get("driver") or r.get("label") for r in vm]
drivers = [l for l in lab if l in t and l not in ("charles_leclerc", "lewis_hamilton")]
print("analysed drivers:", len(drivers))
rs = {d: float(t[d]["reaction_speed_verve"]) for d in drivers}; m = {d: float(t[d]["mistakes_verve"]) for d in drivers}
pr = {d: float(t[d]["pred_reaction_verve"]) for d in drivers}; pb = {d: float(t[d]["pred_bad_start_verve"]) for d in drivers}
print(f"predicted spread (sd over drivers): reaction {st.pstdev(pr.values()):.4f} s, b {st.pstdev(pb.values()):.4f}")
def sim(n_starts, rng):
    R = {d: [] for d in drivers}; B = {d: [] for d in drivers}; outR = {d: 0 for d in drivers}; outB = {d: 0 for d in drivers}
    for _ in range(n_starts):
        kr = rng.gauss(0.51, 0.08); kb = rng.gauss(0.56, 0.10); kfit = kr + rng.gauss(0, 0.015)
        for d in drivers:
            r = rng.uniform(0.28 - 0.24 * kr * rs[d], 0.42 - 0.18 * kr * rs[d]); b = rng.uniform(0.06 - 0.02 * kb * m[d], 0.42 - 0.14 * kb * m[d])
            R[d].append(r); B[d].append(b)
            k = kfit
            if not (0.28 - 0.24 * k * rs[d] - 0.005 <= r <= 0.42 - 0.18 * k * rs[d] + 0.005): outR[d] += 1
            if not (0.06 - 0.02 * m[d] <= b <= 0.42): outB[d] += 1
    cr = st.correlation([st.median(R[d]) for d in drivers], [pr[d] for d in drivers])
    cb = st.correlation([st.median(B[d]) for d in drivers], [pb[d] for d in drivers])
    envR = all(v <= 1 for v in outR.values()); envB = all(v <= 1 for v in outB.values())
    return cr, cb, envR, envB
rng = random.Random(11)
for n in (10, 20, 30):
    res = [sim(n, rng) for _ in range(2000)]
    print(f"{n} starts: P(r_reaction>=0.6) {sum(r[0] >= 0.6 for r in res)/len(res):.2f}, median r {st.median(r[0] for r in res):.2f}; "
          f"P(r_b>=0.6) {sum(r[1] >= 0.6 for r in res)/len(res):.2f}, median r {st.median(r[1] for r in res):.2f}; "
          f"P(envelope ok: reaction at per-start k +-0.005 s, b over k in [0,1]) reaction {sum(r[2] for r in res)/len(res):.2f}, b {sum(r[3] for r in res)/len(res):.2f}")

