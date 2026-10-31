"""Running order, gaps and lap times of a benchmark race from the game's own log channels (B-0013, #60).

Usage:
    python3 tools/race_order.py <loader.log> --out <dir> [--train-gap 1.0]

Needs the channels LAPTIMES*:info and (optionally) RESULTS*:info and OVERTAKES:info in SWOFTY_GAME_LOG_CHANNELS.

- Car names come from LAPTIMES `onVehicleNewSector() - v(<id>, <name>)`.
- Sector-line crossings come from LAPTIMES `Added sector S, on lap L, to vehicle V, and session time was T`. At each
  (lap, sector) line the cars are ordered by T; the gap is T minus the car ahead's T at that line.
- Lap times come from LAPTIMES/V `Reporting NEW LAP TIME (n) for vehicle Ix V (time +x s)`.
- RESULTS/V `Position - P, Vehicle Id - V, ...` blocks are sampled at most once per second of wall time.

Writes <out>/crossings.csv (lap, sector, rank, vehicle, name, session_time, gap_ahead_s), <out>/lap_times.csv
(vehicle, name, lap, lap_time_s, leader_lap_time_s) and <out>/position_changes.csv (where the order at a line differs
from the previous line), and prints a summary.
"""
from __future__ import annotations

import argparse
import csv
import re
from collections import defaultdict
from pathlib import Path

NAME = re.compile(r"onVehicleNewSector\(\) - v\((\d+), ([^)]+)\)")
SECTOR = re.compile(r"Added sector (\d+), on lap (\d+), to vehicle (\d+), and session time was ([\d.]+)")
LAP = re.compile(r"NEW LAP TIME \((\d+)\) for vehicle Ix (\d+) \(time \+([\d.]+)s\)")
RESULT = re.compile(r"^\S+ (\d\d:\d\d:\d\d)\.\d+ .*RESULTS/V: Position - (\d+), Vehicle Id - (\d+)")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("log", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--train-gap", type=float, default=1.0)
    a = ap.parse_args()
    names: dict[int, str] = {}
    cross: dict[tuple[int, int], dict[int, float]] = defaultdict(dict)
    laps: dict[int, dict[int, float]] = defaultdict(dict)
    res_orders: list[tuple[str, tuple[int, ...]]] = []
    block: dict[int, int] = {}
    block_sec = last_sec = None
    overtakes = 0
    with a.log.open(encoding="utf-8", errors="replace") as f:
        for line in f:
            if "LAPTIMES" in line:
                if m := NAME.search(line):
                    names[int(m.group(1))] = m.group(2)
                elif m := SECTOR.search(line):
                    s, lap, v, t = int(m.group(1)), int(m.group(2)), int(m.group(3)), float(m.group(4))
                    cross[(lap, s)][v] = t
                elif m := LAP.search(line):
                    laps[int(m.group(1))][int(m.group(2))] = float(m.group(3))
            elif "RESULTS/V: Position" in line:
                m = RESULT.match(line)
                if not m:
                    continue
                sec, pos, v = m.group(1), int(m.group(2)), int(m.group(3))
                if pos == 0:
                    if block and block_sec != last_sec:
                        res_orders.append((block_sec, tuple(block[p] for p in sorted(block))))
                        last_sec = block_sec
                    block, block_sec = {}, sec
                block[pos] = v
            elif "OVERTAKES:" in line:
                overtakes += 1
    a.out.mkdir(parents=True, exist_ok=True)

    lines = sorted(cross)
    gaps, changes, prev = [], [], None
    with (a.out / "crossings.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["lap", "sector", "rank", "vehicle", "name", "session_time", "gap_ahead_s"])
        for key in lines:
            order = sorted(cross[key], key=cross[key].get)
            for r, v in enumerate(order):
                gap = round(cross[key][v] - cross[key][order[r - 1]], 3) if r else ""
                if r:
                    gaps.append(gap)
                w.writerow([key[0], key[1], r + 1, v, names.get(v, ""), cross[key][v], gap])
            common = [v for v in order if prev is None or v in prev[1]]
            if prev is not None and common != [v for v in prev[1] if v in common]:
                changes.append((prev[0], key, prev[1], order))
            prev = (key, order)
    with (a.out / "position_changes.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["from_lap", "from_sector", "to_lap", "to_sector", "order_before", "order_after"])
        for k0, k1, o0, o1 in changes:
            w.writerow([k0[0], k0[1], k1[0], k1[1], " ".join(map(str, o0)), " ".join(map(str, o1))])
    with (a.out / "lap_times.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["vehicle", "name", "lap", "lap_time_s", "leader_lap_time_s"])
        for lap in sorted(laps):
            first_line = cross.get((lap, 2)) or {}
            leader = min(first_line, key=first_line.get) if first_line else None
            for v in sorted(laps[lap]):
                w.writerow([v, names.get(v, ""), lap, laps[lap][v], laps[lap].get(leader, "")])

    res_changes = sum(1 for x, y in zip(res_orders, res_orders[1:]) if x[1] != y[1])
    print(f"cars named {len(names)}; sector lines {len(lines)}; laps timed {len(laps)}")
    print(f"order changes between consecutive sector lines: {len(changes)}")
    print(f"RESULTS/V: {len(res_orders)} one-per-second blocks, order changes {res_changes}; OVERTAKES lines {overtakes}")
    if gaps:
        under = sum(g < a.train_gap for g in gaps)
        print(f"gaps to car ahead at sector lines: n {len(gaps)}, median {sorted(gaps)[len(gaps) // 2]:.3f} s, "
              f"max {max(gaps):.3f} s, under {a.train_gap} s: {under} ({100 * under / len(gaps):.0f}%)")
    for lap in sorted(laps):
        d = laps[lap]
        print(f"lap {lap}: lap times {min(d.values()):.2f}-{max(d.values()):.2f} s, fastest v{min(d, key=d.get)} "
              f"{names.get(min(d, key=d.get), '')}")


if __name__ == "__main__":
    main()
