"""Validity and the descriptive summary for B-0018 (#120): the stock race-feel baseline at Hungary, weather locked dry.

Usage:
    python -I tools/b0018_check.py --validity runs/<batch>/race_<n>   # one race's validity, no metrics
    python -I tools/b0018_check.py runs/<batch>                       # the summary, after the last race only
    python -I tools/b0018_check.py --selftest

No hypothesis and no verdict: per metric, the mean, the between-race SD and a 95% bootstrap CI of the mean over races
(2000, seed 1). Validity (#120): UDP track_id 9 (Hungaroring); difficulty 100; player car 19; chequered flag; gamedb 52;
addons.json empty (stock); weather.txt LOCKED (#118); no PAUSE cut. Exit 0 summary written, 3 not enough valid races
(or one race INVALID with --validity).
"""
from __future__ import annotations

import csv
import json
import random
import re
import statistics
import sys
from pathlib import Path

TRACK_HUNGARY = "9"
PLAYER_CAR = 19
EXPECT_OVERWRITTEN = 52
GAMEDB = re.compile(r"gamedb: (\d+) overwritten")
BOOTSTRAPS, BOOT_SEED = 2000, 1
METRICS = ("train_time_share", "longest_train_median", "longest_train_max", "held_passes_net_2plus",
           "lap1_held_changes", "lap1_loss_median_s", "lap1_spread_s", "lap1_costly_contacts", "lap1_collisions",
           "early_brakes_total", "early_brakes_in_traffic", "phantom_brakes", "rear_end_contacts",
           "costly_contact_cars", "front_wing_increments", "median_green_lap_s")
PER_DRIVER = ("train_s_behind_net", "held_suffered_net_2plus")


def read_csv(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_race(run: Path) -> tuple[dict, list[str]]:
    invalid: list[str] = []
    try:
        sessions = [s for s in read_csv(run / "udp" / "sessions.csv") if s["session_type"] == "race"]
        events = read_csv(run / "udp" / "events.csv")
        log = (run / "raw" / "loader.log").read_text(encoding="utf-8", errors="replace").splitlines()
        summary = json.loads((run / "race_feel" / "race_feel_summary.json").read_text(encoding="utf-8"))
        feel = read_csv(run / "race_feel" / "race_feel.csv")
    except (OSError, ValueError) as e:
        return {}, [f"missing data: {e}"]
    if len(sessions) != 1:
        return {}, [f"{len(sessions)} race sessions in UDP"]
    s = sessions[0]
    if s.get("track_id") != TRACK_HUNGARY:
        invalid.append(f"track: track_id {s.get('track_id')}, expected {TRACK_HUNGARY} (Hungaroring)")
    if s.get("ai_difficulty", "") != "100":
        invalid.append(f"AI difficulty reads {s.get('ai_difficulty') or 'nothing'}, expected 100")
    if int(s["player_car"]) != PLAYER_CAR:
        invalid.append(f"player is car {s['player_car']}, not {PLAYER_CAR}")
    if not any(e["code"] == "CHQF" and e["session_uid"] == s["session_uid"] for e in events):
        invalid.append("no chequered flag")
    db = next((m for m in map(GAMEDB.search, log) if m), None)
    if not db or int(db[1]) != EXPECT_OVERWRITTEN:
        invalid.append(f"gamedb {db[1] if db else 'none'} overwritten, expected {EXPECT_OVERWRITTEN}")
    try:
        addons = json.loads((run / "addons.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        addons = None
    if addons != {}:
        invalid.append(f"addons {addons}, expected none (stock)")
    wx = run / "weather.txt"
    if not wx.exists() or not wx.read_text(encoding="utf-8").startswith("weather: LOCKED"):
        invalid.append("weather: " + (wx.read_text(encoding="utf-8").splitlines()[0] if wx.exists() else "no weather.txt"))
    if (run / "pause_cut.txt").exists():
        invalid.append("PAUSE cut")
    vals = {k: summary.get(k) for k in METRICS}
    vals["guards_dnfs"] = (summary.get("guards") or {}).get("dnfs")
    for k in PER_DRIVER:
        xs = [float(r[k]) for r in feel if r.get(k) not in (None, "", "NA")]
        vals[k + "_mean"] = statistics.mean(xs) if xs else None
    return vals | {"race": run.name}, invalid


def describe(xs: list[float]) -> tuple[float, float, float, float]:
    rng = random.Random(BOOT_SEED)
    m = statistics.mean(xs)
    sd = statistics.stdev(xs) if len(xs) > 1 else float("nan")
    boots = sorted(statistics.mean(rng.choice(xs) for _ in xs) for _ in range(BOOTSTRAPS))
    return m, sd, boots[int(0.025 * BOOTSTRAPS)], boots[int(0.975 * BOOTSTRAPS) - 1]


def selftest() -> int:
    m, sd, lo, hi = describe([1.0, 2.0, 3.0, 4.0, 5.0])
    ok = abs(m - 3.0) < 1e-9 and abs(sd - statistics.stdev([1, 2, 3, 4, 5])) < 1e-9 and lo < m < hi
    print("selftest", "ok" if ok else "FAILED", m, round(sd, 3), lo, hi)
    return 0 if ok else 1


def main() -> int:
    args = sys.argv[1:]
    if "--selftest" in args:
        return selftest()
    validity = "--validity" in args
    args = [a for a in args if a != "--validity"]
    if len(args) != 1 or args[0].startswith("--"):
        print(__doc__)
        return 3
    if validity:
        run = Path(args[0])
        _, invalid = load_race(run)
        for why in invalid:
            print(f"  INVALID: {why}")
        print("  RESULT: INVALID, discard and rerun" if invalid else "  RESULT: VALID")
        return 3 if invalid else 0
    runs = sorted((p for p in Path(args[0]).glob("race_*") if p.is_dir()), key=lambda p: int(p.name.split("_")[1]))
    races = []
    for run in runs:
        vals, invalid = load_race(run)
        print(f"{run.name}: {'VALID' if not invalid else 'INVALID: ' + '; '.join(invalid)}")
        if not invalid:
            races.append(vals)
    print(f"\n{len(races)} valid of {len(runs)} races")
    if len(races) < 2:
        return 3
    print("\nmetric: mean, between-race SD, 95% bootstrap CI of the mean (descriptive, no verdict)")
    for k in (*METRICS, "guards_dnfs", *(p + "_mean" for p in PER_DRIVER)):
        xs = [float(r[k]) for r in races if r.get(k) is not None]
        if len(xs) < 2:
            print(f"  {k}: n/a")
            continue
        m, sd, lo, hi = describe(xs)
        print(f"  {k}: {m:.3f}, SD {sd:.3f}, CI [{lo:.3f}, {hi:.3f}] (n {len(xs)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
