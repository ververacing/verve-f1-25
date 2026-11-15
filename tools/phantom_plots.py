#!/usr/bin/env python3
"""By-eye validation of the phantom-brake detector (docs/race_feel_plan.md): for one race, plot 5 onsets the detector
flags as phantom and 5 it scores as normal, each as that car's speed and brake against lap distance around the onset,
with the onset and its corner reference marked.

Usage:
    python -I tools/phantom_plots.py udp.bin --name <label> --out docs/race_feel/   # writes <label>.png and .csv

The selection is seeded (seed 1), so a rerun picks the same onsets. Read-only: it only reads the capture.
"""
from __future__ import annotations

import argparse
import bisect
import csv
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import udp_parse as u  # noqa: E402
import race_feel as rf  # noqa: E402

import matplotlib  # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("capture", type=Path)
    ap.add_argument("--name", required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--per-group", type=int, default=5)
    a = ap.parse_args()

    rows, summary = rf.analyse(a.capture)
    names = {r["car"]: r["name"] for r in rows}
    onsets = list(rf.ONSET_LOG)
    flagged = [o for o in onsets if o["phantom"]]
    normal = [o for o in onsets if not o["phantom"]]
    rng = random.Random(1)
    pick = rng.sample(flagged, min(a.per_group, len(flagged))) + rng.sample(normal, min(a.per_group, len(normal)))

    s = u.parse(a.capture, [])
    uid = summary["session_uid"]
    sess = s[uid]
    ftimes = [t for t, _ in sess["lap_frames"]]
    ttimes = [t for t, _ in sess["tel_frames"]]
    btimes = [t for t, _ in sess["brake_frames"]]

    def trace(car: int, t0: float, window_s: float = 14.0):
        """(lap distance, speed, brake) samples of one car from t0 - window_s to t0 + 4 s."""
        out = []
        i = bisect.bisect_left(ttimes, t0 - window_s)
        while i < len(ttimes) and ttimes[i] <= t0 + 4.0:
            t = ttimes[i]
            fi = max(bisect.bisect_right(ftimes, t) - 1, 0)
            bi = max(bisect.bisect_right(btimes, t) - 1, 0)
            out.append((sess["lap_frames"][fi][1][car][u.L_LAPDIST], sess["tel_frames"][i][1][car],
                        sess["brake_frames"][bi][1][car]))
            i += 1
        return out

    a.out.mkdir(parents=True, exist_ok=True)
    n = len(pick)
    fig, axes = plt.subplots(n, 1, figsize=(11, 2.3 * max(n, 1)), squeeze=False)
    for ax, o in zip(axes[:, 0], pick):
        tr = [p for p in trace(o["car"], o["t"]) if o["d"] - 450 <= p[0] <= o["d"] + 250]
        if tr:
            ax.plot([p[0] for p in tr], [p[1] for p in tr], color="#1f6feb", lw=1.4, label="speed km/h")
            ax2 = ax.twinx()
            ax2.fill_between([p[0] for p in tr], [p[2] for p in tr], color="#d1242f", alpha=0.35, step="mid", label="brake")
            ax2.set_ylim(0, 1.05)
            ax2.set_yticks([0, 0.3, 1])
        ax.axvline(o["d"], color="#d1242f", ls="--", lw=1)
        ax.axvline(o.get("ref", o["d"]), color="#1a7f37", ls="-", lw=1)
        ax.set_title(f"{'PHANTOM' if o['phantom'] else 'normal'} | {names.get(o['car'], o['car'])} lap {o['lap']} | onset {o['d']:.0f} m, "
                     f"ref ({o['kind']}) {o.get('ref', float('nan')):.0f} m, {o.get('early_m', 0):.0f} m early | follower {o['follower_gap_s']:.2f} s, ahead {'-' if o.get('ahead_gap_s') is None else format(o['ahead_gap_s'], '.2f')} s",
                     fontsize=8, loc="left")
        ax.tick_params(labelsize=7)
    axes[-1, 0].set_xlabel("lap distance (m); red dashed = onset, green = corner reference", fontsize=8)
    fig.tight_layout()
    png = a.out / f"{a.name}.png"
    fig.savefig(png, dpi=90)
    with (a.out / f"{a.name}.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["car", "name", "lap", "onset_m", "ref_kind", "ref_m", "early_m", "phantom", "follower_gap_s", "ahead_gap_s"])
        for o in pick:
            w.writerow([o["car"], names.get(o["car"]), o["lap"], round(o["d"], 1), o["kind"], round(o.get("ref", 0), 1),
                        round(o.get("early_m", 0), 1), int(o["phantom"]), round(o["follower_gap_s"], 3), '' if o.get('ahead_gap_s') is None else round(o['ahead_gap_s'], 3)])
    print(f"{png}: {len(flagged)} flagged, {len(normal)} scored normal; plotted {n}. "
          f"cars scored {summary['phantom_cars_scored']}, onsets scored share {summary['phantom_onsets_scored_share']}, "
          f"refs {summary['phantom_ref_counts']}, corners {summary['corners']}")


if __name__ == "__main__":
    main()
