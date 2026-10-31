"""B-0011 readout (#53, criterion as fixed in edit 2 before the run): the generator's addon vs the F-39 predictions.

Usage:
    python3 tools/b0011_readout.py <run folder with summary.csv> <table.csv> <vehicle map csv> [--n 2000] [--seed 1]

The vehicle map (docs/stock/driver_rows_benchmark_austria.csv) gives each vehicle id's driver label; table.csv gives
that driver's written values (reaction_speed_verve, mistakes_verve) and F-39 predictions (pred_*_verve, k = 0.52).
Ferrari (vehicles 8, 19) is excluded throughout. b = 1 - race_start_performance / 100 (F-38).

F-39: reaction ~ U(0.28 - 0.24 k rs, 0.42 - 0.18 k rs), mean 0.35 - 0.21 k rs;
      b ~ U(0.06 - 0.02 k m, 0.42 - 0.14 k m), mean 0.24 - 0.08 k m.

Criterion:
    reaction:  Pearson r(per-driver median reaction, pred_reaction_verve) >= 0.6 over the 18 drivers;
    envelopes: reaction within [0.28 - 0.24 k rs, 0.42 - 0.18 k rs] +- 0.005 s at that start's k (fixed-intercept fit
               from the 18 cars); b within [0.06 - 0.02 m, 0.42]; no driver outside in more than 1 start, per draw;
    bad start: pooled fixed-intercept k from all cars' b on written m within 2 SE of the stock-field k 0.56 +- 0.08,
               i.e. in [0.40, 0.72]. The estimate's own SE is a bootstrap over whole starts.
    descriptive: per-driver r for b.
"""
from __future__ import annotations

import argparse
import csv
import random
import statistics as st
from pathlib import Path

EXCLUDE = {"8", "19"}
KB_STOCK, KB_SE = 0.56, 0.08


def k_fit(rows, x, y, a, s):
    """Fixed-intercept least squares for y = a - s k x."""
    return sum((a - r[y]) * s * r[x] for r in rows) / sum((s * r[x]) ** 2 for r in rows)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("run", type=Path)
    ap.add_argument("table", type=Path)
    ap.add_argument("vmap", type=Path)
    ap.add_argument("--n", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args()
    table = {r["label"]: r for r in csv.DictReader(a.table.open())}
    driver = {r["vehicle"]: r["driver"] for r in csv.DictReader(a.vmap.open())}
    rows = []
    for r in csv.DictReader((a.run / "summary.csv").open()):
        if r["vehicle"] in EXCLUDE:
            continue
        t = table[driver[r["vehicle"]]]
        rows.append({"start": int(r["start"]), "driver": driver[r["vehicle"]],
                     "rs": float(t["reaction_speed_verve"]), "m": float(t["mistakes_verve"]),
                     "pr": float(t["pred_reaction_verve"]), "pb": float(t["pred_bad_start_verve"]),
                     "rt": float(r["reaction_time"]), "b": 1 - float(r["race_start_performance"]) / 100})
    starts = sorted({r["start"] for r in rows})
    drivers = sorted({r["driver"] for r in rows})
    by_start = {s: [r for r in rows if r["start"] == s] for s in starts}
    print(f"starts {len(starts)}, drivers {len(drivers)}, samples {len(rows)}")

    # reaction correlation
    med = {d: st.median(r["rt"] for r in rows if r["driver"] == d) for d in drivers}
    pred = {d: next(r["pr"] for r in rows if r["driver"] == d) for d in drivers}
    r_rt = st.correlation([med[d] for d in drivers], [pred[d] for d in drivers])
    medb = {d: st.median(r["b"] for r in rows if r["driver"] == d) for d in drivers}
    predb = {d: next(r["pb"] for r in rows if r["driver"] == d) for d in drivers}
    r_b = st.correlation([medb[d] for d in drivers], [predb[d] for d in drivers])

    # envelopes
    out_r = {d: [] for d in drivers}; out_b = {d: [] for d in drivers}; ks = {}
    for s in starts:
        k = ks[s] = k_fit(by_start[s], "rs", "rt", 0.35, 0.21)
        for r in by_start[s]:
            if not (0.28 - 0.24 * k * r["rs"] - 0.005 <= r["rt"] <= 0.42 - 0.18 * k * r["rs"] + 0.005):
                out_r[r["driver"]].append(s)
            if not (0.06 - 0.02 * r["m"] <= r["b"] <= 0.42):
                out_b[r["driver"]].append(s)
    env_r = all(len(v) <= 1 for v in out_r.values()); env_b = all(len(v) <= 1 for v in out_b.values())

    # pooled bad-start k
    kb = k_fit(rows, "m", "b", 0.24, 0.08)
    rng = random.Random(a.seed)
    boot = [k_fit([r for s in (rng.choice(starts) for _ in starts) for r in by_start[s]], "m", "b", 0.24, 0.08)
            for _ in range(a.n)]
    kb_se = st.stdev(boot)
    kb_ok = abs(kb - KB_STOCK) <= 2 * KB_SE

    print("driver,rs,m,pred_reaction,median_reaction,pred_b,median_b,reaction_misses,b_misses")
    for d in sorted(drivers, key=lambda d: pred[d]):
        r0 = next(r for r in rows if r["driver"] == d)
        print(f"{d},{r0['rs']:.4f},{r0['m']:.4f},{pred[d]:.4f},{med[d]:.4f},{predb[d]:.4f},{medb[d]:.4f},"
              f"{len(out_r[d])}{' ' + '/'.join(map(str, out_r[d])) if out_r[d] else ''},"
              f"{len(out_b[d])}{' ' + '/'.join(map(str, out_b[d])) if out_b[d] else ''}")
    kv = list(ks.values())
    print(f"per-start reaction k: mean {st.mean(kv):.3f}, sd {st.stdev(kv):.3f}, range {min(kv):.3f}-{max(kv):.3f}")
    print(f"reaction: r = {r_rt:.3f} (need >= 0.6): {'pass' if r_rt >= 0.6 else 'FAIL'}")
    print(f"envelopes: reaction worst {max(len(v) for v in out_r.values())} miss(es), "
          f"b worst {max(len(v) for v in out_b.values())} (allowed 1 per driver): "
          f"reaction {'pass' if env_r else 'FAIL'}, b {'pass' if env_b else 'FAIL'}")
    print(f"bad start: pooled k = {kb:.3f} (boot SE {kb_se:.3f}); need within 2 SE of {KB_STOCK} +- {KB_SE} "
          f"= [{KB_STOCK - 2 * KB_SE:.2f}, {KB_STOCK + 2 * KB_SE:.2f}]: {'pass' if kb_ok else 'FAIL'}")
    print(f"descriptive: per-driver r for b = {r_b:.3f}")
    ok = r_rt >= 0.6 and env_r and env_b and kb_ok
    print(f"verdict: {'PASS' if ok else 'FAIL'}")


if __name__ == "__main__":
    main()
