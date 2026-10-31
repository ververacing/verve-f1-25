"""B-0010 readout (#51): crossed reaction_speed x mistakes, pre-registered criterion.

Usage:
    python3 tools/b0010_readout.py <folder with summary.csv and arms.csv> [--n 2000] [--seed 1]

Each armed car's sample is its draw minus that start's stock-field median (stock field = cars not armed and not
Ferrari, vehicles 8 and 19). For reaction_rel and b_rel (b = 1 - race_start_performance/100, F-38):
    mistakes main effect    = mean(m 0.90 cells) - mean(m 0.10 cells)
    rs main effect          = mean(rs 0.90 cells) - mean(rs 0.10 cells)
    interaction             = (rs.9/m.9 - rs.9/m.1) - (rs.1/m.9 - rs.1/m.1)
SE = sd over bootstrap resamples of whole starts.

Criterion (#51, fixed before the run):
    batch valid only if the rs main effect on reaction_rel is <= -2 SE (positive control);
    F-40 CONFIRMED if the mistakes main effect on reaction_rel is <= -2 SE;
    REJECTED if its 2-SE interval excludes -0.015 s; else inconclusive.
"""
from __future__ import annotations

import argparse
import csv
import random
import statistics as st
from pathlib import Path

EXCLUDE = {"8", "19"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("folder", type=Path)
    ap.add_argument("--n", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args()
    rows = list(csv.DictReader((a.folder / "summary.csv").open()))
    arms = {r["key"]: r for r in csv.DictReader((a.folder / "arms.csv").open())}
    starts = sorted({int(r["start"]) for r in rows})
    samples = {}
    for s in starts:
        cars = [r for r in rows if int(r["start"]) == s]
        field = [r for r in cars if r["vehicle"] not in arms and r["vehicle"] not in EXCLUDE]
        f_rt = st.median(float(r["reaction_time"]) for r in field)
        f_b = st.median(1 - float(r["race_start_performance"]) / 100 for r in field)
        samples[s] = [(float(arms[r["vehicle"]]["rs"]), float(arms[r["vehicle"]]["m"]),
                       float(r["reaction_time"]) - f_rt, 1 - float(r["race_start_performance"]) / 100 - f_b)
                      for r in cars if r["vehicle"] in arms]

    def stats(pick):
        cell = {}
        for s in pick:
            for rs, m, rt, b in samples[s]:
                cell.setdefault((rs > 0.5, m > 0.5), []).append((rt, b))
        mean = {k: (st.mean(v[0] for v in vs), st.mean(v[1] for v in vs)) for k, vs in cell.items()}
        out = {}
        for i, metric in enumerate(("reaction", "b")):
            g = lambda rs, m: mean[(rs, m)][i]
            out[f"{metric}_mistakes_main"] = (g(False, True) + g(True, True) - g(False, False) - g(True, False)) / 2
            out[f"{metric}_rs_main"] = (g(True, False) + g(True, True) - g(False, False) - g(False, True)) / 2
            out[f"{metric}_interaction"] = (g(True, True) - g(True, False)) - (g(False, True) - g(False, False))
            for (rs, m) in sorted(mean):
                out[f"{metric}_cell_rs{'0.9' if rs else '0.1'}_m{'0.9' if m else '0.1'}"] = g(rs, m)
        return out

    point = stats(starts)
    rng = random.Random(a.seed)
    boot = {k: [] for k in point}
    for _ in range(a.n):
        res = stats([rng.choice(starts) for _ in starts])
        for k, v in res.items():
            boot[k].append(v)
    print(f"starts {len(starts)}, armed samples per start {len(samples[starts[0]])}, resamples {a.n}, seed {a.seed}")
    print("statistic,estimate,boot_se,z")
    se = {}
    for k, v in point.items():
        se[k] = st.stdev(boot[k])
        print(f"{k},{v:.4f},{se[k]:.4f},{v / se[k]:.2f}")

    rs_ok = point["reaction_rs_main"] <= -2 * se["reaction_rs_main"]
    e, s = point["reaction_mistakes_main"], se["reaction_mistakes_main"]
    if not rs_ok:
        verdict = "INVALID (positive control failed: rs main effect not <= -2 SE)"
    elif e <= -2 * s:
        verdict = "F-40 CONFIRMED (mistakes main effect <= -2 SE)"
    elif not (e - 2 * s <= -0.015 <= e + 2 * s):
        verdict = "F-40 REJECTED (2-SE interval excludes -0.015 s)"
    else:
        verdict = "INCONCLUSIVE"
    print(f"positive control: {'pass' if rs_ok else 'FAIL'}; mistakes on reaction: {e:+.4f} s, "
          f"2-SE interval [{e - 2 * s:+.4f}, {e + 2 * s:+.4f}]")
    print(f"verdict: {verdict}")


if __name__ == "__main__":
    main()
